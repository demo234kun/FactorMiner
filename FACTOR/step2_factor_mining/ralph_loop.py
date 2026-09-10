# -*- coding: utf-8 -*-
"""
ralph_loop.py —— FactorMiner 主循环（Ralph Loop）

流程：检索经验记忆(R) -> LLM 生成候选(G) -> 表达式求值+评估(E) -> 蒸馏更新记忆(D)
直到因子库规模达到 K 或达到最大迭代次数。
"""
from __future__ import annotations
import sys
from typing import List, Optional
from FACTOR.step1_data_ingestion.spec import (
    DataConfig, MiningConfig, LLMConfig, LibraryResult, Trajectory, Factor, MarketData,
)
from FACTOR.step1_data_ingestion.data_sources import get_data_source
from FACTOR.step2_factor_mining.expression_engine import ExpressionEngine, ExpressionError
from FACTOR.step2_factor_mining.evaluation import validate_batch
from FACTOR.step3_factor_library_memory.memory import Memory
from FACTOR.step2_factor_mining.llm_proposer import LLMProposer


def run(
    data_cfg: DataConfig,
    mining_cfg: MiningConfig,
    llm_cfg: LLMConfig,
    memory_path: Optional[str] = None,
    use_memory: bool = True,
    md: Optional[MarketData] = None,
) -> LibraryResult:
    data = md if md is not None else get_data_source(data_cfg).load(data_cfg)
    engine = ExpressionEngine()
    proposer = LLMProposer(llm_cfg)
    memory = Memory(memory_path)

    library: List[Factor] = []
    trajectories: List[Trajectory] = []
    n_iter = 0

    for it in range(mining_cfg.max_iterations):
        n_iter = it + 1
        prior = memory.retrieval(library) if use_memory else ""
        formulas = proposer.propose(prior, mining_cfg.batch_size)

        candidates = []
        for f in formulas:
            try:
                sig = engine.evaluate(f, data)
            except ExpressionError as e:
                print(f"[ralph] 跳过无法求值的公式 {f}: {e}", file=sys.stderr)
                continue
            candidates.append((f, sig))

        results, library = validate_batch(candidates, library, data, mining_cfg)
        traj = Trajectory(iteration=it, candidates=results)
        trajectories.append(traj)

        form = memory.formation(traj)
        n_high_corr = sum(1 for r in results if r.rejected_reason in ("high_corr", "corr_replace"))
        saturation = (n_high_corr / len(results)) if results else 0.0
        memory.evolution(form, library_size=len(library), saturation=saturation)
        memory.save()

        print(f"[ralph] iter={it} 候选={len(results)} 库规模={len(library)} 饱和={saturation:.2f}", file=sys.stderr)
        if len(library) >= mining_cfg.k_lib:
            print(f"[ralph] 达到目标库规模 K={mining_cfg.k_lib}，停止。", file=sys.stderr)
            break

    return LibraryResult(library=library, memory=memory.state,
                         trajectories=trajectories, n_iterations=n_iter)


def summarize(result: LibraryResult) -> str:
    lib = result.library
    if not lib:
        return "因子库为空（未挖掘到满足阈值的因子）。"
    ics = [abs(f.ic) for f in lib]
    avg_ic = sum(ics) / len(ics)
    lines = [
        f"因子库规模: {len(lib)}（迭代 {result.n_iterations} 轮）",
        f"平均 |IC|: {avg_ic:.4f}",
        f"Top-5 因子（按 |IC|）:",
    ]
    top = sorted(lib, key=lambda f: abs(f.ic), reverse=True)[:5]
    for f in top:
        lines.append(f"  {f.id} |IC|={abs(f.ic):.4f} ICIR={f.icir:.3f} maxCorr={f.max_corr:.2f}  {f.formula}")
    return "\n".join(lines)
