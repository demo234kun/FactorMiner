# -*- coding: utf-8 -*-
"""
run_strategy.py —— 策略自动进化智能体演示

默认：合成数据 → 2024 训练建记忆 → 2025 滚动测试（含监控/减仓/失灵进化）。
  --no-llm       关闭 LLM，进化退化为参数变体兜底
  --use-factors  先挖掘因子库（run_demo 主循环），再「基于这些因子」构建策略模板
  --mine-llm     挖掘因子时使用真实 DeepSeek（否则用模板兜底，离线可跑）

数据划分：1600 期，前 800 期作为 2024 训练，后 800 期作为 2025 测试。
"""
from __future__ import annotations
import sys as _s, os as _o
_s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
import argparse
import tempfile
from 策略回测.step4_策略进化.agent import run_pipeline
from 策略回测.step2_模板与情境.templates import build_templates, build_factor_templates


def _mine_factor_library(use_llm: bool):
    """跑一轮因子挖掘，返回 Factor 列表（供策略层复用）。"""
    from FACTOR.step1_数据接入.spec import DataConfig, MiningConfig, LLMConfig
    from FACTOR.step2_因子挖掘.ralph_loop import run

    data_cfg = DataConfig(source="synthetic", market="csi500", freq="10min",
                          start="2024-01-01", end="2024-12-31",
                          n_instruments=12, n_periods=400, seed=0)
    mining_cfg = MiningConfig(tau_ic=0.03, theta=0.5, k_lib=10, batch_size=16,
                              replace_min_ic=0.08, replace_ic_ratio=1.3,
                              seed=0, max_iterations=8)
    llm_cfg = LLMConfig(backend="deepseek", model="deepseek-chat",
                        api_key_env="DEEPSEEK_API_KEY", base_url="https://api.deepseek.com",
                        temperature=0.8, max_tokens=2048,
                        fallback="template", seed=0)
    if not use_llm:
        llm_cfg.fallback = "template"
    res = run(data_cfg, mining_cfg, llm_cfg, memory_path="memory_state.json")
    return res.library


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true", help="关闭 LLM，进化使用参数变体兜底")
    ap.add_argument("--use-factors", action="store_true", help="先挖掘因子库，再基于因子构建策略")
    ap.add_argument("--mine-llm", action="store_true", help="挖掘因子时使用真实 DeepSeek")
    args = ap.parse_args()

    strategies = None
    if args.use_factors:
        print("== 先挖掘因子库（供策略层直接使用）==")
        factors = _mine_factor_library(use_llm=args.mine_llm)
        strategies = build_factor_templates(factors)
        print(f"   因子数={len(factors)} → 构建策略模板={len(strategies)}")

    tmp = tempfile.mktemp(suffix=".json")
    print("\n== 运行策略进化流水线（2024 训练 → 2025 监控/减仓/失灵进化）==")
    out = run_pipeline(use_llm=not args.no_llm, strategies=strategies, memory_path=tmp)

    log = out["log"]
    mem = out["memory"]
    n_warn = sum(1 for s in log if s.action == "risk_warn")
    n_evol = sum(1 for s in log if s.action == "evolve")
    st = mem.stats()
    print(f"   资产数={out['n_assets']} 策略模板={out['n_templates']} 2025窗口={len(log)}")
    print(f"   风险提示(减仓)={n_warn}  失灵进化={n_evol}  记忆: 成功={st['success']} 失败={st['fail']}")

    print("\n-- 进化轨迹（前 8 条）--")
    for s in log[:8]:
        print(f"  [{s.t0:04d},{s.t1:04d}] {s.regime:<7} {s.action:<9} "
              f"Sharpe={s.live_sharpe:+.2f} | {s.note}")

    print("\n-- 记忆样例（成功/失败各 2 条）--")
    for e in mem.successes[:2]:
        print(f"  [成功] {e.strategy_name} | regime={e.regime} "
              f"Sharpe={e.metrics.get('sharpe',0):.2f} | {e.reason}")
    for e in mem.failures[:2]:
        print(f"  [失败] {e.strategy_name} | regime={e.regime} "
              f"Sharpe={e.metrics.get('sharpe',0):.2f} | {e.reason}")


if __name__ == "__main__":
    main()
