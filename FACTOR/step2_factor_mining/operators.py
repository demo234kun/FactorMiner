# -*- coding: utf-8 -*-
"""
operators.py —— FactorMiner 复刻版算子库（论文 Table 2）

全部算子对 (T, M) 的 numpy 数组做变换并返回 (T, M)。
- el : 逐元素算子
- ts : 时间序列算子（沿时间轴 axis=0）
- cs : 截面算子（沿资产轴 axis=1）
所有算子对 NaN / 常数 / 零除做了安全处理。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, List
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as _swv


# --------------------------------------------------------------------------- #
# 算子规格
# --------------------------------------------------------------------------- #
@dataclass
class OperatorSpec:
    name: str
    fn: Callable
    arity: int          # 数据操作数个数
    kind: str           # 'el' | 'ts' | 'cs'
    params: List[str]   # 参数类型序列：'expr' = 数据操作数, 'int' / 'float' = 字面量


# --------------------------------------------------------------------------- #
# 通用安全工具
# --------------------------------------------------------------------------- #
def _safe_div(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(np.abs(b) > 1e-12, a / b, 0.0)
    return out


def _roll(x: np.ndarray, w: int, red: Callable) -> np.ndarray:
    """沿时间轴滑窗，red 作用于滑窗 view (T-w+1, M, w) -> (T-w+1, M)。"""
    w = max(1, int(w))
    T = x.shape[0]
    out = np.full_like(x, np.nan, dtype=float)
    if w > T:
        w = T
    view = _swv(x, w, axis=0)
    out[w - 1:] = red(view)
    out = np.where(np.isnan(out), 0.0, out)
    return out


def _linreg_slope(x: np.ndarray, w: int) -> np.ndarray:
    w = max(2, int(w))
    T = x.shape[0]
    out = np.full_like(x, np.nan, dtype=float)
    if w > T:
        w = T
    view = _swv(x, w, axis=0)               # (Tw, M, w)
    t = np.arange(w, dtype=float)
    tmean = t.mean()
    denom = ((t - tmean) ** 2).sum()
    xs_mean = view.mean(axis=2)             # (Tw, M)
    cov = ((view - xs_mean[:, :, None]) * (t - tmean)[None, None, :]).sum(axis=2)
    slope = cov / denom
    out[w - 1:] = slope
    out = np.where(np.isnan(out), 0.0, out)
    return out


def _linreg_rsquare(x: np.ndarray, w: int) -> np.ndarray:
    w = max(2, int(w))
    T = x.shape[0]
    out = np.full_like(x, np.nan, dtype=float)
    if w > T:
        w = T
    view = _swv(x, w, axis=0)
    t = np.arange(w, dtype=float)
    tmean = t.mean()
    denom = ((t - tmean) ** 2).sum()
    xs_mean = view.mean(axis=2)
    cov = ((view - xs_mean[:, :, None]) * (t - tmean)[None, None, :]).sum(axis=2)
    slope = cov / denom
    intercept = xs_mean - slope * tmean
    pred = slope[:, :, None] * t[None, None, :] + intercept[:, :, None]
    ss_res = ((view - pred) ** 2).sum(axis=2)
    ss_tot = ((view - xs_mean[:, :, None]) ** 2).sum(axis=2)
    r2 = 1.0 - _safe_div(ss_res, ss_tot)
    out[w - 1:] = r2
    out = np.where(np.isnan(out), 0.0, out)
    return out


def _linreg_resi(x: np.ndarray, w: int) -> np.ndarray:
    w = max(2, int(w))
    T = x.shape[0]
    out = np.full_like(x, np.nan, dtype=float)
    if w > T:
        w = T
    view = _swv(x, w, axis=0)
    t = np.arange(w, dtype=float)
    tmean = t.mean()
    denom = ((t - tmean) ** 2).sum()
    xs_mean = view.mean(axis=2)
    cov = ((view - xs_mean[:, :, None]) * (t - tmean)[None, None, :]).sum(axis=2)
    slope = cov / denom
    intercept = xs_mean - slope * tmean
    last = view[:, :, -1]
    resi = last - (intercept + slope * (w - 1))
    out[w - 1:] = resi
    out = np.where(np.isnan(out), 0.0, out)
    return out


# --------------------------------------------------------------------------- #
# 算术算子 (el)
# --------------------------------------------------------------------------- #
def _add(a, b): return a + b
def _sub(a, b): return a - b
def _mul(a, b): return a * b
def _div(a, b): return _safe_div(a, b)
def _neg(a): return -a
def _abs(a): return np.abs(a)
def _log(a): return np.log(np.abs(a) + 1e-12) * np.sign(a)
def _signed_power(a, p): return np.sign(a) * (np.abs(a) ** p)
def _power(a, p): return np.abs(a) ** p
def _inv(a): return _safe_div(1.0, a)
def _sqrt(a): return np.sqrt(np.abs(a))
def _square(a): return a * a
def _exp(a): return np.exp(np.clip(a, -30.0, 30.0))
def _tanh(a): return np.tanh(a)
def _sign(a): return np.sign(a).astype(float)


# --------------------------------------------------------------------------- #
# 统计算子 (ts, 滑窗)
# --------------------------------------------------------------------------- #
def _mean(a, w): return _roll(a, w, lambda v: np.nanmean(v, axis=2))
def _std(a, w): return _roll(a, w, lambda v: np.nanstd(v, axis=2))
def _var(a, w): return _roll(a, w, lambda v: np.nanvar(v, axis=2))
def _sum(a, w): return _roll(a, w, lambda v: np.nansum(v, axis=2))
def _product(a, w): return _roll(a, w, lambda v: np.nanprod(np.clip(v, -1e6, 1e6), axis=2))
def _med(a, w): return _roll(a, w, lambda v: np.nanmedian(v, axis=2))


def _skew(a, w):
    def red(v):
        m = np.nanmean(v, axis=2, keepdims=True)
        s2 = np.nanmean((v - m) ** 2, axis=2)
        s3 = np.nanmean((v - m) ** 3, axis=2)
        return _safe_div(s3, s2 ** 1.5)
    return _roll(a, w, red)


def _kurt(a, w):
    def red(v):
        m = np.nanmean(v, axis=2, keepdims=True)
        s2 = np.nanmean((v - m) ** 2, axis=2)
        s4 = np.nanmean((v - m) ** 4, axis=2)
        return _safe_div(s4, s2 ** 2) - 3.0
    return _roll(a, w, red)


# --------------------------------------------------------------------------- #
# 时序算子 (ts)
# --------------------------------------------------------------------------- #
def _delay(a, d):
    d = max(0, int(d))
    if d == 0:
        return a.copy()
    T, M = a.shape
    out = np.zeros_like(a, dtype=float)
    out[d:] = a[:T - d]
    return out


def _delta(a, d):
    return a - _delay(a, d)


def _ts_rank(a, w):
    w = max(1, int(w))
    T = a.shape[0]
    out = np.full_like(a, np.nan, dtype=float)
    if w > T:
        w = T
    view = _swv(a, w, axis=0)          # (Tw, M, w)
    last = view[:, :, -1]               # (Tw, M)
    rank = (view <= last[:, :, None]).mean(axis=2)
    out[w - 1:] = rank
    out = np.where(np.isnan(out), 0.5, out)
    return out


def _ts_max(a, w): return _roll(a, w, lambda v: np.nanmax(v, axis=2))
def _ts_min(a, w): return _roll(a, w, lambda v: np.nanmin(v, axis=2))


def _ts_argmax(a, w):
    w = max(1, int(w))
    T = a.shape[0]
    out = np.full_like(a, np.nan, dtype=float)
    if w > T:
        w = T
    view = _swv(a, w, axis=0)
    out[w - 1:] = (np.argmax(view, axis=2) + 1).astype(float)
    out = np.where(np.isnan(out), float(w), out)
    return out


def _ts_argmin(a, w):
    w = max(1, int(w))
    T = a.shape[0]
    out = np.full_like(a, np.nan, dtype=float)
    if w > T:
        w = T
    view = _swv(a, w, axis=0)
    out[w - 1:] = (np.argmin(view, axis=2) + 1).astype(float)
    out = np.where(np.isnan(out), 1.0, out)
    return out


def _ts_decay(a, w):
    w = max(1, int(w))
    weights = np.arange(1, w + 1, dtype=float)
    def red(v):
        return (v * weights[None, None, :]).sum(axis=2) / weights.sum()
    return _roll(a, w, red)


# --------------------------------------------------------------------------- #
# 截面算子 (cs)
# --------------------------------------------------------------------------- #
def _cs_rank(a):
    T, M = a.shape
    out = np.empty_like(a, dtype=float)
    for t in range(T):
        row = a[t]
        order = np.argsort(row, kind="stable")
        ranks = np.empty(M, dtype=float)
        ranks[order] = np.arange(M, dtype=float)
        if M > 1:
            out[t] = ranks / (M - 1) * 2.0 - 1.0
        else:
            out[t] = 0.0
    return out


def _scale(a):
    T, M = a.shape
    out = np.empty_like(a, dtype=float)
    for t in range(T):
        row = a[t]
        mx = np.max(np.abs(row))
        out[t] = row / (mx + 1e-12)
    return out


# --------------------------------------------------------------------------- #
# 平滑算子
# --------------------------------------------------------------------------- #
def _sma(a, w): return _mean(a, w)


def _ema(a, w):
    w = max(1, int(w))
    T, M = a.shape
    alpha = 2.0 / (w + 1)
    out = np.empty_like(a, dtype=float)
    out[0] = a[0]
    for t in range(1, T):
        out[t] = alpha * a[t] + (1 - alpha) * out[t - 1]
    return out


def _wma(a, w):
    w = max(1, int(w))
    weights = np.arange(1, w + 1, dtype=float)
    def red(v):
        return (v * weights[None, None, :]).sum(axis=2) / weights.sum()
    return _roll(a, w, red)


def _ts_corr(a, b, w):
    """时序 Pearson 相关：沿时间轴滑窗计算 a 与 b 的相关。返回 (T,M)。"""
    w = max(2, int(w))
    T = a.shape[0]
    out = np.full_like(a, np.nan, dtype=float)
    if w > T:
        w = T
    va = _swv(a, w, axis=0)
    vb = _swv(b, w, axis=0)
    am = va.mean(axis=2, keepdims=True)
    bm = vb.mean(axis=2, keepdims=True)
    da = va - am
    db = vb - bm
    num = (da * db).sum(axis=2)
    da2 = (da * da).sum(axis=2)
    db2 = (db * db).sum(axis=2)
    den = np.sqrt(da2 * db2)
    corr = np.where(den > 1e-12, num / np.where(den > 1e-12, den, 1.0), 0.0)
    out[w - 1:] = corr
    out = np.where(np.isnan(out), 0.0, out)
    return out


def _ts_cov(a, b, w):
    """时序协方差：沿时间轴滑窗计算 a 与 b 的协方差。返回 (T,M)。"""
    w = max(2, int(w))
    T = a.shape[0]
    out = np.full_like(a, np.nan, dtype=float)
    if w > T:
        w = T
    va = _swv(a, w, axis=0)
    vb = _swv(b, w, axis=0)
    am = va.mean(axis=2, keepdims=True)
    bm = vb.mean(axis=2, keepdims=True)
    cov = ((va - am) * (vb - bm)).sum(axis=2) / max(w - 1, 1)
    out[w - 1:] = cov
    out = np.where(np.isnan(out), 0.0, out)
    return out


# --------------------------------------------------------------------------- #
# 回归算子
# --------------------------------------------------------------------------- #
def _slope(a, w): return _linreg_slope(a, w)
def _rsquare(a, w): return _linreg_rsquare(a, w)
def _resi(a, w): return _linreg_resi(a, w)


# --------------------------------------------------------------------------- #
# 逻辑算子 (el)
# --------------------------------------------------------------------------- #
def _if_else(c, a, b): return np.where(c > 0, a, b)
def _greater(a, b): return (a > b).astype(float)
def _less(a, b): return (a < b).astype(float)
def _greater_equal(a, b): return (a >= b).astype(float)
def _less_equal(a, b): return (a <= b).astype(float)
def _and(a, b): return ((a > 0) & (b > 0)).astype(float)
def _or(a, b): return ((a > 0) | (b > 0)).astype(float)
def _eq(a, b): return (a == b).astype(float)
def _ne(a, b): return (a != b).astype(float)


# --------------------------------------------------------------------------- #
# 注册表
# --------------------------------------------------------------------------- #
OPERATORS: dict[str, OperatorSpec] = {
    # Arithmetic
    "Add": OperatorSpec("Add", _add, 2, "el", ["expr", "expr"]),
    "Sub": OperatorSpec("Sub", _sub, 2, "el", ["expr", "expr"]),
    "Mul": OperatorSpec("Mul", _mul, 2, "el", ["expr", "expr"]),
    "Div": OperatorSpec("Div", _div, 2, "el", ["expr", "expr"]),
    "Neg": OperatorSpec("Neg", _neg, 1, "el", ["expr"]),
    "Abs": OperatorSpec("Abs", _abs, 1, "el", ["expr"]),
    "Log": OperatorSpec("Log", _log, 1, "el", ["expr"]),
    "SignedPower": OperatorSpec("SignedPower", _signed_power, 1, "el", ["expr", "float"]),
    "Power": OperatorSpec("Power", _power, 1, "el", ["expr", "float"]),
    "Inv": OperatorSpec("Inv", _inv, 1, "el", ["expr"]),
    "Sqrt": OperatorSpec("Sqrt", _sqrt, 1, "el", ["expr"]),
    "Square": OperatorSpec("Square", _square, 1, "el", ["expr"]),
    "Exp": OperatorSpec("Exp", _exp, 1, "el", ["expr"]),
    "Tanh": OperatorSpec("Tanh", _tanh, 1, "el", ["expr"]),
    "Sign": OperatorSpec("Sign", _sign, 1, "el", ["expr"]),
    # Statistical
    "Mean": OperatorSpec("Mean", _mean, 1, "ts", ["expr", "int"]),
    "Std": OperatorSpec("Std", _std, 1, "ts", ["expr", "int"]),
    "Var": OperatorSpec("Var", _var, 1, "ts", ["expr", "int"]),
    "Skew": OperatorSpec("Skew", _skew, 1, "ts", ["expr", "int"]),
    "Kurt": OperatorSpec("Kurt", _kurt, 1, "ts", ["expr", "int"]),
    "Med": OperatorSpec("Med", _med, 1, "ts", ["expr", "int"]),
    "Sum": OperatorSpec("Sum", _sum, 1, "ts", ["expr", "int"]),
    "Product": OperatorSpec("Product", _product, 1, "ts", ["expr", "int"]),
    # Time-series
    "Delay": OperatorSpec("Delay", _delay, 1, "ts", ["expr", "int"]),
    "Delta": OperatorSpec("Delta", _delta, 1, "ts", ["expr", "int"]),
    "TsRank": OperatorSpec("TsRank", _ts_rank, 1, "ts", ["expr", "int"]),
    "TsMax": OperatorSpec("TsMax", _ts_max, 1, "ts", ["expr", "int"]),
    "TsMin": OperatorSpec("TsMin", _ts_min, 1, "ts", ["expr", "int"]),
    "TsArgMax": OperatorSpec("TsArgMax", _ts_argmax, 1, "ts", ["expr", "int"]),
    "TsArgMin": OperatorSpec("TsArgMin", _ts_argmin, 1, "ts", ["expr", "int"]),
    "TsDecay": OperatorSpec("TsDecay", _ts_decay, 1, "ts", ["expr", "int"]),
    # Cross-sectional
    "CsRank": OperatorSpec("CsRank", _cs_rank, 1, "cs", ["expr"]),
    "Scale": OperatorSpec("Scale", _scale, 1, "cs", ["expr"]),
    # Smoothing
    "SMA": OperatorSpec("SMA", _sma, 1, "ts", ["expr", "int"]),
    "EMA": OperatorSpec("EMA", _ema, 1, "ts", ["expr", "int"]),
    "WMA": OperatorSpec("WMA", _wma, 1, "ts", ["expr", "int"]),
    # Regression
    "Slope": OperatorSpec("Slope", _slope, 1, "ts", ["expr", "int"]),
    "Rsquare": OperatorSpec("Rsquare", _rsquare, 1, "ts", ["expr", "int"]),
    "Resi": OperatorSpec("Resi", _resi, 1, "ts", ["expr", "int"]),
    # Pairwise time-series
    "TsCorr": OperatorSpec("TsCorr", _ts_corr, 2, "ts", ["expr", "expr", "int"]),
    "TsCov": OperatorSpec("TsCov", _ts_cov, 2, "ts", ["expr", "expr", "int"]),
    # Logical
    "IfElse": OperatorSpec("IfElse", _if_else, 3, "el", ["expr", "expr", "expr"]),
    "Greater": OperatorSpec("Greater", _greater, 2, "el", ["expr", "expr"]),
    "Less": OperatorSpec("Less", _less, 2, "el", ["expr", "expr"]),
    "GreaterEqual": OperatorSpec("GreaterEqual", _greater_equal, 2, "el", ["expr", "expr"]),
    "LessEqual": OperatorSpec("LessEqual", _less_equal, 2, "el", ["expr", "expr"]),
    "And": OperatorSpec("And", _and, 2, "el", ["expr", "expr"]),
    "Or": OperatorSpec("Or", _or, 2, "el", ["expr", "expr"]),
    "Eq": OperatorSpec("Eq", _eq, 2, "el", ["expr", "expr"]),
    "Ne": OperatorSpec("Ne", _ne, 2, "el", ["expr", "expr"]),
}


def get_operator(name: str) -> OperatorSpec:
    spec = OPERATORS.get(name)
    if spec is None:
        raise KeyError(f"未知算子 '{name}'。可用: {sorted(OPERATORS)}")
    return spec


def list_operators() -> List[str]:
    return sorted(OPERATORS.keys())
