# -*- coding: utf-8 -*-
"""
run_demo.py —— 端到端演示（无需网络/真实数据）

用合成行情 + 模板生成器跑通 FactorMiner 主循环，输出因子库摘要。
用法: python run_demo.py
"""
from __future__ import annotations
import sys as _s, os as _o
_s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
import os
import sys

from FACTOR.step1_数据接入.spec import DataConfig, MiningConfig, LLMConfig
from FACTOR.step2_因子挖掘.ralph_loop import run, summarize

data_cfg = DataConfig(
    source="synthetic", market="csi500", freq="10min",
    start="2024-01-01", end="2024-12-31",
    n_instruments=15, n_periods=500, instruments=None, seed=0,
)
mining_cfg = MiningConfig(
    tau_ic=0.03, theta=0.5, k_lib=12, batch_size=20,
    replace_min_ic=0.08, replace_ic_ratio=1.3, seed=0, max_iterations=15,
)
llm_cfg = LLMConfig(backend="deepseek", model="deepseek-chat",
                    api_key_env="DEEPSEEK_API_KEY", base_url="https://api.deepseek.com",
                    temperature=0.8, max_tokens=2048, fallback="template", seed=0)

if __name__ == "__main__":
    print("=== FactorMiner 复刻版 端到端演示 ===", flush=True)
    result = run(data_cfg, mining_cfg, llm_cfg, memory_path="memory_state.json")
    print("\n=== 因子库摘要 ===", flush=True)
    print(summarize(result))
    print(f"\n经验记忆: 推荐方向 {len(result.memory.patterns)} 条, 禁区 {len(result.memory.forbidden)} 条")
