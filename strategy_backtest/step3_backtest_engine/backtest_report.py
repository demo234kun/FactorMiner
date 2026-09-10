# -*- coding: utf-8 -*-
"""
backtest_report.py —— 标准量化回测报告（证明策略价值）

输入：signal (T,M)、target (T,M)、times、direction
输出：dict 报告，含：
  - 核心指标：Sharpe / 年化 / 总收益 / 最大回撤 / 胜率 / rank IC
  - 净值曲线与回撤曲线（用于网页绘图）
  - 分年表现、分段(每50期)表现
  - 多空/纯多月度收益概览

依赖：strategy_backtest/step3_回测引擎/engine.backtest（真实权重+组合收益计算）
"""
from __future__ import annotations
from typing import Optional
import numpy as np
from strategy_backtest.step3_backtest_engine.engine import backtest


def _annualized(total_ret: float, n_periods: int, periods_per_year: int = 252) -> float:
    if n_periods <= 0:
        return 0.0
    return float((1.0 + total_ret) ** (periods_per_year / n_periods) - 1.0)


def _max_drawdown_series(cum: np.ndarray) -> tuple:
    peak = np.maximum.accumulate(cum)
    dd = cum / peak - 1.0
    return dd, float(dd.min())


def build_backtest_report(
    signal: np.ndarray,
    target: np.ndarray,
    times,
    direction: str = "long_short",
    periods_per_year: int = 252,
    label: str = "",
) -> dict:
    signal = np.asarray(signal, dtype=float)
    target = np.asarray(target, dtype=float)
    # 防御：全 NaN 列/行会导致指标为 nan，统一归零，保证报告始终可序列化
    signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
    target = np.nan_to_num(target, nan=0.0, posinf=0.0, neginf=0.0)
    res = backtest(signal, target, direction)

    port = res.port_ret
    port = np.nan_to_num(port, nan=0.0, posinf=0.0, neginf=0.0)
    T = len(port)
    cum = np.cumprod(1.0 + port)
    dd_series, max_dd = _max_drawdown_series(cum)
    cum = np.nan_to_num(cum, nan=1.0, posinf=1.0, neginf=1.0)
    dd_series = np.nan_to_num(dd_series, nan=0.0, posinf=0.0, neginf=0.0)

    # 分年表现
    yearly = {}
    if times is not None and len(times) == T:
        import pandas as pd
        s = pd.Series(port)
        try:
            idx = pd.to_datetime(list(times))
        except Exception:
            idx = None
        if idx is not None:
            s.index = idx
            yr_ret = (1.0 + s).groupby(s.index.year).prod() - 1.0
            yearly = {int(k): round(float(v), 4) for k, v in yr_ret.items()}

    # 分段（每 50 期）表现
    seg = []
    step = 50
    for i in range(0, T, step):
        seg_port = port[i:i + step]
        if len(seg_port) == 0:
            continue
        seg_cum = np.cumprod(1.0 + seg_port)
        seg_ret = float(seg_cum[-1] - 1.0)
        seg_dd = float((seg_cum / np.maximum.accumulate(seg_cum) - 1.0).min())
        seg.append({"start": i, "end": i + len(seg_port) - 1,
                    "return": round(seg_ret, 4), "max_dd": round(seg_dd, 4)})

    # 月度收益概览（最后 12 个非空月）
    monthly = []
    if times is not None and len(times) == T:
        import pandas as pd
        try:
            idx = pd.to_datetime(list(times))
            s = pd.Series(port)
            s.index = idx
            mo = (1.0 + s).resample("ME").prod() - 1.0
            monthly = [{"period": str(k.date())[:7], "return": round(float(v), 4)}
                       for k, v in mo.dropna().tail(12).items()]
        except Exception:
            monthly = []

    return {
        "label": label,
        "direction": direction,
        "n_periods": T,
        "metrics": {
            "sharpe": round(res.sharpe, 3),
            "annualized": round(_annualized(res.total_return, T, periods_per_year), 4),
            "total_return": round(res.total_return, 4),
            "max_drawdown": round(max_dd, 4),
            "win_rate": round(res.win_rate, 4),
            "rank_ic": round(res.ic, 4),
        },
        "equity_curve": [round(float(x), 6) for x in cum],
        "drawdown_curve": [round(float(x), 6) for x in dd_series],
        "yearly": yearly,
        "segments": seg,
        "monthly": monthly,
    }


def backtest_template(
    template,
    md,
    direction: Optional[str] = None,
    periods_per_year: int = 252,
) -> dict:
    """直接对 StrategyTemplate 在 MarketData 上回测，返回完整报告。"""
    from FACTOR.step2_factor_mining.expression_engine import ExpressionEngine
    sig = ExpressionEngine().evaluate(template.signal, md)
    return build_backtest_report(
        sig.values, md.target, md.times,
        direction=direction or template.direction,
        periods_per_year=periods_per_year,
        label=template.name,
    )
