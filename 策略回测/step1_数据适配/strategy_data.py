# -*- coding: utf-8 -*-
"""
data.py —— 策略层合成数据（带资产类型与市场 regime）

为了让「经验记忆 / 自动进化」有可区分的情境，数据在资产维度注入类型
（trending / mean_reverting / high_vol / stable / large_liq），
在时间维度注入 regime（bull / bear / volatile / calm）。
不同情境下不同策略有系统性优劣，从而形成可学习的成功/失败经验。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple
import numpy as np
import pandas as pd
from FACTOR.step1_数据接入.spec import MarketData


@dataclass
class StrategyDataset:
    md: MarketData
    regime_labels: List[str]          # 长度 T
    asset_types: List[str]            # 长度 M


def generate_strategy_data(
    n_assets: int = 20, n_periods: int = 1600,
    start: str = "2024-01-01", freq: str = "10min",
    seed: int = 0, regime_blocks: int = 8,
) -> StrategyDataset:
    rng = np.random.default_rng(seed)
    T, M = n_periods, n_assets

    # 资产类型分配（循环覆盖）
    types = ["trending", "mean_reverting", "high_vol", "stable", "large_liq"]
    asset_types = [types[i % len(types)] for i in range(M)]

    # regime 序列：把 T 切成 regime_blocks 段，交替不同 regime
    regimes = ["bull", "volatile", "bear", "calm", "bull", "volatile", "bear", "calm"]
    block = np.array_split(np.arange(T), min(regime_blocks, T))
    regime_labels = [""] * T
    for i, b in enumerate(block):
        rg = regimes[i % len(regimes)]
        for t in b:
            regime_labels[t] = rg

    # 参数
    base_vol = np.array([0.03 if asset_types[m] == "high_vol" else
                         0.006 if asset_types[m] == "stable" else 0.015
                         for m in range(M)])
    phi = np.array([0.30 if asset_types[m] == "trending" else
                    -0.30 if asset_types[m] == "mean_reverting" else 0.0
                    for m in range(M)])

    ret = np.zeros((T, M))
    for t in range(1, T):
        rg = regime_labels[t]
        drift = {"bull": 0.0010, "bear": -0.0010, "volatile": 0.0, "calm": 0.0}[rg]
        vol_mult = 2.0 if rg == "volatile" else (0.6 if rg == "calm" else 1.0)
        eps = rng.standard_normal(M) * base_vol * vol_mult
        ret[t] = drift + phi * ret[t - 1] + eps
    ret[0] = 0.0

    close = np.cumprod(1.0 + ret, axis=0) * 100.0
    open_ = close * (1.0 + rng.standard_normal((T, M)) * 0.001)
    high = np.maximum(open_, close) * (1.0 + np.abs(rng.standard_normal((T, M))) * 0.002)
    low = np.minimum(open_, close) * (1.0 - np.abs(rng.standard_normal((T, M))) * 0.002)
    liq_base = np.array([5.0 if asset_types[m] == "large_liq" else 2.0 for m in range(M)])
    volume = np.exp(rng.standard_normal((T, M)) * 0.4 + liq_base)
    amt = close * volume
    vwap = (high + low + close) / 3.0
    returns = close / np.roll(close, 1, axis=0) - 1.0
    returns[0] = 0.0
    # 目标：下一期 open-to-close 收益
    target = np.roll(ret, -1, axis=0)
    target[-1] = 0.0
    target = target - target.mean(axis=1, keepdims=True)

    times = pd.date_range(start, periods=T, freq=freq, tz="UTC")
    md = MarketData(
        times=list(times), instruments=[f"AST{i:03d}" for i in range(M)],
        open=open_.astype(float), high=high.astype(float), low=low.astype(float),
        close=close.astype(float), volume=volume.astype(float), amt=amt.astype(float),
        vwap=vwap.astype(float), returns=returns.astype(float), target=target.astype(float),
    )
    return StrategyDataset(md=md, regime_labels=regime_labels, asset_types=asset_types)


def slice_dataset(ds: StrategyDataset, t0: int, t1: int) -> StrategyDataset:
    """按时间维切片（资产类型与 universe 保持不变）。"""
    return StrategyDataset(
        md=ds.md.clipped(t0, t1),
        regime_labels=ds.regime_labels[t0:t1],
        asset_types=list(ds.asset_types),
    )


def derive_strategy_dataset(md) -> StrategyDataset:
    """从任意 MarketData（如真实 Qlib 行情）推断资产类型与 regime，包装成 StrategyDataset。

    资产类型按「流动性/自相关/波动」启发式归类；regime 按滚动窗口市场收益/波动归类。
    """
    import numpy as np
    T, M = md.T, md.M
    rets = np.nan_to_num(md.returns, 0.0)
    vol = rets.std(0)
    ac = np.array([
        np.corrcoef(rets[1:, m], rets[:-1, m])[0, 0] if vol[m] > 1e-12 else 0.0
        for m in range(M)
    ])
    amt = np.nan_to_num(md.amt, 0.0).mean(0)
    v_rank = vol.argsort().argsort() / max(M - 1, 1)
    a_rank = amt.argsort().argsort() / max(M - 1, 1)

    asset_types = []
    for m in range(M):
        if a_rank[m] > 0.8:
            asset_types.append("large_liq")
        elif ac[m] > 0.15:
            asset_types.append("trending")
        elif ac[m] < -0.15:
            asset_types.append("mean_reverting")
        elif v_rank[m] > 0.7:
            asset_types.append("high_vol")
        else:
            asset_types.append("stable")

    mkt = np.nan_to_num(md.target, 0.0).mean(1)
    mkt = np.convolve(mkt, np.ones(5) / 5, mode="same")
    roll_vol = np.array([mkt[max(0, t - 20):t + 1].std() for t in range(T)])
    regime_labels = []
    for t in range(T):
        v = roll_vol[t]
        r = mkt[t]
        if v > 0.012:
            regime_labels.append("volatile")
        elif r > 0.004:
            regime_labels.append("bull")
        elif r < -0.004:
            regime_labels.append("bear")
        else:
            regime_labels.append("calm")

    return StrategyDataset(md=md, regime_labels=regime_labels, asset_types=asset_types)
