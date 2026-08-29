# -*- coding: utf-8 -*-
"""
context.py —— 情境特征抽取

把一段回测窗口转成「时间段特征（市场 regime）+ 股票特征（资产类型分布）」，
供经验记忆与相似度检索使用。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
import numpy as np
from 策略回测.step1_数据适配.strategy_data import StrategyDataset


@dataclass
class WindowContext:
    t0: int
    t1: int
    regime: str                      # 主导 regime
    market_return: float             # 窗口内市场累计收益
    market_vol: float                # 市场收益波动
    breadth: float                   # 上涨资产占比
    asset_mix: Dict[str, int]        # 资产类型计数
    regime_mix: Dict[str, float]     # regime 占比


def _classify_regime(mkt_ret: float, mkt_vol: float) -> str:
    if mkt_vol > 0.012:
        return "volatile"
    if mkt_ret > 0.004:
        return "bull"
    if mkt_ret < -0.004:
        return "bear"
    return "calm"


def extract_context(ds: StrategyDataset, t0: int, t1: int) -> WindowContext:
    md = ds.md
    target = md.target[t0:t1]                 # (w, M)
    close = md.close[t0:t1]
    mkt_ret = float(np.mean(target)) * (t1 - t0)
    mkt_vol = float(np.std(target))
    breadth = float(np.mean(target > 0))
    # regime 多数投票
    labels = ds.regime_labels[t0:t1]
    rc = {}
    for l in labels:
        rc[l] = rc.get(l, 0) + 1
    regime = max(rc, key=rc.get) if rc else "calm"
    regime_mix = {k: v / len(labels) for k, v in rc.items()}
    # 资产类型分布（全市场固定）
    am = {}
    for tp in ds.asset_types:
        am[tp] = am.get(tp, 0) + 1
    return WindowContext(
        t0=t0, t1=t1, regime=regime, market_return=mkt_ret,
        market_vol=mkt_vol, breadth=breadth, asset_mix=am, regime_mix=regime_mix,
    )


def context_similarity(a: WindowContext, b: WindowContext) -> float:
    """0~1 相似度：regime 一致 + 资产分布接近 给高分。"""
    score = 0.6 if a.regime == b.regime else 0.0
    keys = set(a.asset_mix) | set(b.asset_mix)
    tot = max(1, sum(a.asset_mix.values()))
    dist = 0.0
    for k in keys:
        dist += abs(a.asset_mix.get(k, 0) - b.asset_mix.get(k, 0))
    score += 0.4 * (1.0 - dist / tot)
    return score
