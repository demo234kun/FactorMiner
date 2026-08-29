# -*- coding: utf-8 -*-
"""
evaluation.py —— 评估引擎

- ic / icir：每个时间步截面 Spearman(信号, 目标) 的时序均值 / (均值/标准差)
- correlation：两信号时序平均截面 Spearman（ρ）
- validate_batch：实现论文 Algorithm 1 的多阶段验证管线
  Stage1 快速 IC 筛选 -> Stage2 相关性预算 -> Stage2.5 顶替 ->
  Stage3 批次内去重 -> Stage4 全量验证准入
"""
from __future__ import annotations
from typing import List, Optional, Tuple
import numpy as np
from FACTOR.step1_数据接入.spec import (
    MarketData, Signal, Factor, CandidateResult, MiningConfig,
    spearman_per_t,
)


def ic(sig: Signal, target: np.ndarray) -> float:
    """时序平均截面 Spearman（带符号）。阈值判定用 abs(ic)。"""
    per_t = spearman_per_t(sig.values, target)
    per_t = per_t[np.isfinite(per_t)]
    if per_t.size == 0:
        return 0.0
    return float(np.mean(per_t))


def icir(sig: Signal, target: np.ndarray) -> float:
    per_t = spearman_per_t(sig.values, target)
    per_t = per_t[np.isfinite(per_t)]
    if per_t.size < 2:
        return 0.0
    std = float(np.std(per_t))
    if std == 0:
        return 0.0
    return float(np.mean(per_t) / std)


def correlation(a: Signal, b: Signal) -> float:
    """时间平均截面 Spearman（ρ）。"""
    per_t = spearman_per_t(a.values, b.values)
    per_t = per_t[np.isfinite(per_t)]
    if per_t.size == 0:
        return 0.0
    return float(np.mean(per_t))


def ave_abs_p(sig: Signal, target: np.ndarray) -> float:
    """每个时间步 Spearman 相关的平均 |p-value|（t 近似），衡量信号与目标关联的显著性。

    p 越小越显著。ave(|p|) 为所有时间步 p 值的平均绝对值，
    用于评估因子整体预测力是否统计显著（越小越好，通常 <0.05 视为显著）。
    """
    from scipy import stats as _st
    per_t = spearman_per_t(sig.values, target)
    per_t = per_t[np.isfinite(per_t)]
    if per_t.size == 0:
        return 1.0
    n_assets = max(2, int(np.sum(np.isfinite(sig.values[0]))))
    # 每步 t 检验：t = rho * sqrt((n-2)/(1-rho^2))
    t_stat = per_t * np.sqrt((n_assets - 2) / np.maximum(1e-12, 1.0 - per_t ** 2))
    p = 2.0 * (1.0 - _st.t.cdf(np.abs(t_stat), df=n_assets - 2))
    p = np.nan_to_num(p, nan=1.0, posinf=1.0, neginf=1.0, copy=True)
    return float(np.mean(p))


def factor_diagnostics(sig: Signal, target: np.ndarray, library_formulas=None,
                       engine=None, md=None, corr_threshold: float = 0.8) -> dict:
    """完整因子诊断：IC / ICIR / ave(|p|) / 与现有因子的最大相关性。

    返回：
      ic, icir, ave_p, max_corr, is_redundant
    is_redundant=True 表示与库内某因子相关性 >= corr_threshold（相关性红海，建议不重复入库）。
    """
    icv = ic(sig, target)
    icirv = icir(sig, target)
    pv = ave_abs_p(sig, target)
    max_corr = 0.0
    if library_formulas and engine is not None and md is not None:
        for f in library_formulas:
            try:
                lsig = engine.evaluate(f, md)
                c = abs(correlation(sig, Signal(f, lsig.values)))
                max_corr = max(max_corr, c)
            except Exception:
                continue
    return {
        "ic": icv,
        "icir": icirv,
        "ave_p": pv,
        "max_corr": max_corr,
        "is_redundant": bool(max_corr >= corr_threshold),
    }


def _corr_with_library(sig: Signal, library: List[Factor]):
    """返回 (max|rho|, [(库索引, |rho|), ...])。"""
    max_c = 0.0
    pairs = []
    for i, f in enumerate(library):
        if f.signal is None:
            continue
        c = abs(correlation(sig, Signal(f.formula, f.signal)))
        max_c = max(max_c, c)
        pairs.append((i, c))
    return max_c, pairs


def validate_batch(
    candidates: List[Tuple[str, Signal]],
    library: List[Factor],
    data: MarketData,
    cfg: MiningConfig,
) -> Tuple[List[CandidateResult], List[Factor]]:
    target = data.target
    tau = cfg.relax_ic if cfg.relax_ic is not None else cfg.tau_ic
    theta = cfg.relax_theta if cfg.relax_theta is not None else cfg.theta

    results: List[CandidateResult] = []
    # 本轮将被顶替移除的库因子 id
    removed_ids = set()

    # 先计算每个候选的 ic/icir 与相关性
    class _C:
        pass

    prepared = []
    for formula, sig in candidates:
        c = _C()
        c.formula = formula
        c.sig = sig
        c.ic = ic(sig, target)
        c.icir = icir(sig, target)
        c.max_corr, c.corr_pairs = _corr_with_library(sig, library)
        c.passed_ic = abs(c.ic) >= tau
        c.passed_corr = c.max_corr < theta
        prepared.append(c)

    # Stage 1 + 2 + 2.5
    for c in prepared:
        res = CandidateResult(
            formula=c.formula, ic=c.ic, icir=c.icir, max_corr=c.max_corr,
            passed_ic=c.passed_ic, passed_corr=c.passed_corr,
            admitted=False, rejected_reason="", replaced_id=None,
            fitness=abs(c.ic),
        )
        if not c.passed_ic:
            res.rejected_reason = "low_ic"
        elif c.passed_corr:
            res.admitted = True
        else:
            # Stage 2.5 顶替检查
            above = [i for (i, cc) in c.corr_pairs
                     if cc >= theta and library[i].id not in removed_ids]
            if len(above) == 1:
                g = library[above[0]]
                if (abs(c.ic) >= cfg.replace_min_ic
                        and abs(c.ic) >= cfg.replace_ic_ratio * abs(g.ic)):
                    res.admitted = True
                    res.replaced_id = g.id
                    removed_ids.add(g.id)
                    res.rejected_reason = "corr_replace"
        results.append(res)

    # Stage 3 批次内去重：按提交顺序，保留首个；后续若与已准入候选 |ρ|>=theta 则丢弃
    admitted_signals: List[Signal] = []
    for res, c in zip(results, prepared):
        if not res.admitted:
            continue
        dup = False
        for s in admitted_signals:
            if abs(correlation(c.sig, s)) >= theta:
                dup = True
                break
        if dup:
            res.admitted = False
            res.rejected_reason = "dup"
            res.replaced_id = None
        else:
            admitted_signals.append(c.sig)

    # Stage 4 构造因子并写回库（处理顶替）
    new_lib = [f for f in library if f.id not in removed_ids]
    max_n = 0
    for f in new_lib:
        try:
            max_n = max(max_n, int(str(f.id).replace("F", "")))
        except Exception:
            pass
    counter = [max_n]

    def next_id():
        counter[0] += 1
        return f"F{counter[0]:03d}"

    for res, c in zip(results, prepared):
        if not res.admitted:
            continue
        # 若为顶替，沿用被顶替因子的 rank 序号更合理，这里简单用新 id
        fid = res.replaced_id if res.replaced_id else next_id()
        # 计算与该因子相关性最高的现有库因子，用于 max_corr
        mc = 0.0
        for f in new_lib:
            if f.signal is None:
                continue
            mc = max(mc, abs(correlation(c.sig, Signal(f.formula, f.signal))))
        fac = Factor(
            id=fid, name=f"factor_{fid}", formula=c.formula,
            ic=c.ic, icir=c.icir, max_corr=mc, rank=len(new_lib) + 1,
            signal=c.sig.values.copy(),
        )
        if res.replaced_id:
            # 替换：找到同 id 的位置覆盖
            for i, f in enumerate(new_lib):
                if f.id == res.replaced_id:
                    new_lib[i] = fac
                    break
            else:
                new_lib.append(fac)
        else:
            new_lib.append(fac)

    return results, new_lib
