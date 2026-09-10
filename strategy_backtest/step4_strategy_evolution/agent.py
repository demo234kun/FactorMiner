# -*- coding: utf-8 -*-
"""
agent.py —— 策略自动进化智能体

流程（对应你的设计）：
  A. train_2024：在 2024 数据上滚动窗口跑全部策略模板 → 评估 → 按阈值标记
     成功/失败 → 抽取情境（regime + 资产分布）→ 存入策略经验记忆。
  B. evolve_2025：滚动窗口测试：
      1) 监控：若当前情境匹配「失败经验」，发风险提示并减仓规避；
      2) 失灵判定：当前策略滚动 Sharpe 低于阈值 → 暂停；
      3) 进化：检索相似成功经验 → 调用 LLM 推荐 3-5 个策略迭代 →
         近期窗口回测验证 → 成功/失败经验都存档 → 切换到最优新策略。
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np
from strategy_backtest.step1_data_adapter.strategy_data import StrategyDataset, generate_strategy_data
from strategy_backtest.step2_template_context.templates import build_templates, StrategyTemplate
from strategy_backtest.step2_template_context.context import extract_context, WindowContext
from strategy_backtest.step3_backtest_engine.engine import backtest, BacktestResult
from strategy_backtest.step4_strategy_evolution.memory import StrategyMemory, StrategyExperience
from FACTOR.step2_factor_mining import expression_engine as E
from FACTOR.step2_factor_mining.llm_proposer import LLMProposer


# ---------------- 2024 训练：建立记忆 ---------------- #
def train_2024(
    ds: StrategyDataset, memory: StrategyMemory,
    win: int = 120, step: int = 60, sharpe_thresh: float = 0.4,
    templates: Optional[List[StrategyTemplate]] = None,
) -> List[StrategyExperience]:
    """滚动窗口回测全部模板，成功/失败经验入库。返回新增经验。"""
    md = ds.md
    T = len(md.times)
    templates = templates or build_templates()
    eng = E.ExpressionEngine()
    added: List[StrategyExperience] = []
    for t0 in range(0, T - win, step):
        t1 = t0 + win
        ctx = extract_context(ds, t0, t1)
        for tp in templates:
            try:
                sig = eng.evaluate(tp.signal, md.clipped(t0, t1))
            except Exception:
                continue
            res = backtest(sig.values, md.target[t0:t1], tp.direction)
            outcome = "success" if res.sharpe >= sharpe_thresh else "fail"
            reason = ("情境契合，信号稳定产生超额" if outcome == "success"
                      else "情境不适或信号失效，Sharpe 不达标")
            exp = StrategyExperience(
                id=f"S_{tp.id}_{t0}", strategy_id=tp.id, strategy_name=tp.name,
                category=tp.category, outcome=outcome, reason=reason,
                metrics=res.metrics, regime=ctx.regime,
                market_return=ctx.market_return, market_vol=ctx.market_vol,
                breadth=ctx.breadth, asset_mix=ctx.asset_mix, signal=tp.signal)
            memory.add(exp)
            added.append(exp)
    return added


# ---------------- 2025 进化 ---------------- #
@dataclass
class EvolveStep:
    t0: int
    t1: int
    regime: str
    action: str                       # 'normal' | 'risk_warn' | 'evolve'
    note: str
    live_sharpe: float = 0.0
    new_strategy: Optional[str] = None


def _rolling_sharpe(md, sig, t0, t1, direction) -> float:
    res = backtest(sig[t0:t1], md.target[t0:t1], direction)
    return res.sharpe


def evolve_2025(
    ds: StrategyDataset, memory: StrategyMemory,
    llm=None, win: int = 90, step: int = 30,
    sharpe_thresh: float = 0.4, fail_thresh: float = 0.1,
    use_memory: bool = True, verbose: bool = True,
    templates: Optional[List[StrategyTemplate]] = None,
) -> List[EvolveStep]:
    md = ds.md
    T = len(md.times)
    templates = templates or build_templates()
    eng = E.ExpressionEngine()

    # 当前激活策略：2024 记忆里表现最好的成功策略
    best = None
    if memory.successes:
        best = max(memory.successes, key=lambda e: e.metrics.get("sharpe", -9))
    base_tp: Optional[StrategyTemplate] = None
    if best:
        base_tp = next((t for t in templates if t.id == best.strategy_id), None)
    if base_tp is None:
        base_tp = templates[0]

    log: List[EvolveStep] = []
    paused = False
    reduce_factor = 1.0

    for t0 in range(0, T - win, step):
        t1 = t0 + win
        ctx = extract_context(ds, t0, t1)

        # --- 1) 风险监控：当前情境在历史中失败率偏高 → 风险提示 + 减仓 ---
        action = "normal"
        note = ""
        reduce_factor = 1.0
        risk_active = False
        if use_memory and (memory.successes or memory.failures):
            same_succ = [e for e in memory.successes if e.regime == ctx.regime]
            same_fail = [e for e in memory.failures if e.regime == ctx.regime]
            if (same_succ or same_fail) and len(same_fail) > len(same_succ):
                risk_active = True
                reduce_factor = 0.4
                note = (f"监控到 regime={ctx.regime} 历史失败 {len(same_fail)} 条 > 成功 "
                        f"{len(same_succ)} 条，触发风险提示并减仓至 {reduce_factor:.0%}")

        # --- 2) 计算当前策略本窗口 live Sharpe ---
        try:
            sig = eng.evaluate(base_tp.signal, md.clipped(t0, t1))
            w = _apply_reduce(sig.values, reduce_factor)
            res = backtest(w, md.target[t0:t1], base_tp.direction)
            live_sharpe = res.sharpe
        except Exception:
            live_sharpe = -9.0

        # --- 3) 失灵判定 → 进化（仅当策略真正失灵时）---
        if live_sharpe < fail_thresh:
            action = "evolve"
            note = (note + (" | " if note else "") +
                    f"策略失灵(Sharpe={live_sharpe:.2f}<{fail_thresh})，启动进化")
            # 检索相似成功经验作为先验
            prior = memory.format_prior(ctx, k=5)
            new_sigs = _propose_iterations(llm, base_tp, prior, ctx) if llm else \
                _propose_template_variants(base_tp)
            if verbose:
                print(f"    [进化] regime={ctx.regime} 候选: " +
                      "; ".join(n for _, n in new_sigs))
            # 验证 3-5 个候选
            best_new = None
            best_new_sharpe = live_sharpe
            for nsig, nname in new_sigs:
                try:
                    s = eng.evaluate(nsig, md.clipped(t0, t1))
                    r = backtest(s.values, md.target[t0:t1], base_tp.direction)
                except Exception:
                    # 失败经验存档
                    _save_iter_exp(memory, base_tp, nsig, nname, ctx, -9.0, "公式无法求值/回测")
                    continue
                outcome = "success" if r.sharpe >= sharpe_thresh else "fail"
                _save_iter_exp(memory, base_tp, nsig, nname, ctx, r.sharpe,
                               "进化候选回测" + ("达标" if outcome == "success" else "未达标"))
                if r.sharpe > best_new_sharpe:
                    best_new_sharpe = r.sharpe
                    best_new = (nsig, nname)
            if best_new:
                # 切换到最优新策略
                new_tp = StrategyTemplate(
                    id=f"EVOL_{base_tp.id}_{t0}", name=f"进化-{base_tp.name}",
                    category=base_tp.category, signal=best_new[0],
                    direction=base_tp.direction,
                    suitable_stock_types=base_tp.suitable_stock_types,
                    suitable_regimes=base_tp.suitable_regimes,
                    description=best_new[1])
                templates.append(new_tp)
                base_tp = new_tp
                paused = False
                if verbose:
                    print(f"    [进化] 切换至 {new_tp.name} Sharpe={best_new_sharpe:.2f}")
                note += f" | 切换至新策略 {new_tp.name}(Sharpe={best_new_sharpe:.2f})"
        elif risk_active:
            action = "risk_warn"

        if verbose:
            print(f"[2025] win[{t0:04d},{t1:04d}] regime={ctx.regime:<7} "
                  f"act={action:<9} liveSharpe={live_sharpe:+.2f} | {note}")
        log.append(EvolveStep(t0=t0, t1=t1, regime=ctx.regime, action=action,
                              note=note, live_sharpe=live_sharpe,
                              new_strategy=base_tp.id))
    return log


def _apply_reduce(sig: np.ndarray, factor: float) -> np.ndarray:
    if factor >= 1.0:
        return sig
    # 减仓：将极端信号向 0 收缩
    return sig * factor


def _save_iter_exp(memory, base_tp, nsig, nname, ctx, sharpe, reason):
    memory.add(StrategyExperience(
        id=f"EV_{base_tp.id}_{abs(hash(nsig))%100000}",
        strategy_id=base_tp.id, strategy_name=nname,
        category=base_tp.category,
        outcome="success" if sharpe >= 0.4 else "fail",
        reason=reason, metrics={"sharpe": sharpe},
        regime=ctx.regime, market_return=ctx.market_return,
        market_vol=ctx.market_vol, breadth=ctx.breadth,
        asset_mix=ctx.asset_mix, signal=nsig))


def _propose_template_variants(base_tp: StrategyTemplate):
    """无 LLM 时的兜底：对基准策略做参数变体（窗口扫描）。"""
    out = []
    for w in [10, 20, 30, 40, 60]:
        sig = base_tp.signal.replace("20", str(w))
        out.append((sig, f"{base_tp.name}-w{w}"))
    return out[:5]


def _propose_iterations(llm, base_tp, prior: str, ctx: WindowContext):
    """调用 LLM 推荐 3-5 个策略迭代信号公式。"""
    prompt_ctx = (f"当前情境: regime={ctx.regime}, 资产分布={ctx.asset_mix}, "
                  f"市场收益={ctx.market_return:.4f}。\n{prior}\n"
                  f"请基于上述成功经验，推荐 3-5 个新的策略信号公式"
                  f"（使用算子如 CsRank/SMA/Delay/Std/Sub/Add/Neg 与 $close/$returns/"
                  f"$volume/$vwap 等字段），每个一行，格式 `Name(表达式)`。")
    try:
        formulas = llm.propose(prompt_ctx, n=5,
                               ctx="策略层：生成组合成交易策略的信号公式")
        # propose() 已返回解析好的公式列表
        out = []
        for f in formulas[:5]:
            out.append((f, f"LLM-{f[:30]}"))
        if out:
            return out
    except Exception:
        pass
    return _propose_template_variants(base_tp)


# ---------------- 统一入口 ---------------- #
def run_pipeline(
    use_llm: bool = True, seed: int = 0, n_assets: int = 20, n_periods: int = 1600,
    win_train: int = 120, step_train: int = 60,
    win_evol: int = 90, step_evol: int = 30,
    sharpe_thresh: float = 0.4, fail_thresh: float = 0.1,
    strategies: Optional[List[StrategyTemplate]] = None,
    memory_path: str = "strategy_memory.json",
    ds: Optional[StrategyDataset] = None,
) -> dict:
    """端到端跑一遍：2024 训练建记忆 → 2025 监控/减仓/失灵进化。

    返回 {log, memory, templates, n_assets, n_templates, ds}。
    strategies 为 None 时用内置模板库；Step2 可传入基于已挖掘因子的策略。
    ds 为 None 时自动生成合成数据；Step3 可传入真实 Qlib 数据集（StrategyDataset）。
    """
    from strategy_backtest.step1_data_adapter.strategy_data import generate_strategy_data, slice_dataset

    if ds is None:
        ds = generate_strategy_data(n_assets=n_assets, n_periods=n_periods, seed=seed)
    n_total = len(ds.md.times)
    half = n_total // 2
    ds24 = slice_dataset(ds, 0, half)
    ds25 = slice_dataset(ds, half, n_total)

    mem = StrategyMemory(path=memory_path)
    train_2024(ds24, mem, win=win_train, step=step_train,
               sharpe_thresh=sharpe_thresh, templates=strategies)

    llm = None
    if use_llm:
        try:
            from FACTOR.step2_factor_mining.llm_proposer import LLMProposer
            from FACTOR.step1_data_ingestion.spec import LLMConfig
            llm = LLMProposer(LLMConfig())
        except Exception:
            llm = None

    log = evolve_2025(ds25, mem, llm=llm, win=win_evol, step=step_evol,
                      sharpe_thresh=sharpe_thresh, fail_thresh=fail_thresh,
                      use_memory=True, verbose=False, templates=strategies)
    return {
        "log": log, "memory": mem, "templates": strategies or build_templates(),
        "n_assets": n_assets, "n_templates": len(strategies) if strategies else len(build_templates()),
        "ds": ds,
    }
