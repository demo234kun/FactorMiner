# -*- coding: utf-8 -*-
"""
engine.py —— 策略回测与指标

给定 signal (T,M) 与目标 target (T,M)，每日截面排序形成多空/纯多权重，
计算组合收益与风险指标。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict
import numpy as np


@dataclass
class BacktestResult:
    port_ret: np.ndarray          # (T,) 组合日收益
    sharpe: float
    total_return: float
    max_drawdown: float
    win_rate: float
    ic: float                     # 截面 rank IC 均值
    metrics: Dict[str, float] = field(default_factory=dict)


def _rank_weights(signal: np.ndarray, direction: str) -> np.ndarray:
    T, M = signal.shape
    w = np.zeros((T, M))
    for t in range(T):
        s = signal[t]
        order = np.argsort(s)
        # 排序打分 0..M-1
        rank = np.empty(M); rank[order] = np.arange(M)
        score = rank - (M - 1) / 2.0
        if direction == "long_only":
            score = np.clip(score, 0, None)
        w[t] = score
    # 归一化（多空则多空市值中性）
    if direction == "long_short":
        w = w / (np.abs(w).sum(axis=1, keepdims=True) + 1e-12)
    else:
        w = w / (w.sum(axis=1, keepdims=True) + 1e-12)
    return w


def backtest(signal: np.ndarray, target: np.ndarray, direction: str = "long_short") -> BacktestResult:
    signal = np.asarray(signal, dtype=float)
    target = np.asarray(target, dtype=float)
    w = _rank_weights(signal, direction)
    port = (w * target).sum(axis=1)              # (T,)
    # 指标
    mu, sd = port.mean(), port.std() + 1e-12
    sharpe = float(mu / sd * np.sqrt(252))
    cum = np.cumprod(1.0 + port)
    total_return = float(cum[-1] - 1.0)
    peak = np.maximum.accumulate(cum)
    max_dd = float(np.min(cum / peak - 1.0))
    win_rate = float(np.mean(port > 0))
    # 截面 rank IC
    ics = []
    for t in range(len(port)):
        s = signal[t]; tg = target[t]
        if np.std(s) < 1e-12 or np.std(tg) < 1e-12:
            continue
        ics.append(np.corrcoef(s, tg)[0, 1])
    ic = float(np.nanmean(ics)) if ics else 0.0
    return BacktestResult(
        port_ret=port, sharpe=sharpe, total_return=total_return,
        max_drawdown=max_dd, win_rate=win_rate, ic=ic,
        metrics={"sharpe": sharpe, "total_return": total_return,
                 "max_drawdown": max_dd, "win_rate": win_rate, "ic": ic},
    )
