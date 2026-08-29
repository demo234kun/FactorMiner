# -*- coding: utf-8 -*-
"""
run_real.py —— 真实数据端到端演示（因子挖掘 + 因子策略进化）

支持两种真实数据源：
  A) 本地 Qlib dump（默认）：需先 python scripts/setup_qlib.py 初始化数据。
  B) 线上 SQL（阿里云 RDS PostgreSQL 等，推荐）：运行时直连取数，不落本地文件。

用法:
  # 线上 SQL 模式（运行时直连，按窗口切片，零本地存储）
  python run_real.py --sql-uri "postgresql+psycopg2://u:p@rm-xxx.mysql.rds.aliyuncs.com:5432/quant" \
                     --sql-table bars --start 2024-01-01 --end 2025-12-31 --no-llm
  # 因子挖掘用 DeepSeek
  python run_real.py --sql-uri "..." --sql-table bars --mine-llm
  # 限定标的
  python run_real.py --sql-uri "..." --sql-table bars --instruments SH600000,SH600001

  # 本地 Qlib 模式
  python run_real.py --no-llm
  python run_real.py --mine-llm
"""
from __future__ import annotations
import sys as _s, os as _o
_s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
import argparse
from collections import Counter

from FACTOR.step1_数据接入.spec import DataConfig, MiningConfig, LLMConfig, SqlConfig
from FACTOR.step2_因子挖掘.ralph_loop import run
from FACTOR.step1_数据接入.data_sources import get_data_source, SqlSource
from 策略回测.step1_数据适配.strategy_data import derive_strategy_dataset
from 策略回测.step4_策略进化.agent import run_pipeline
from 策略回测.step2_模板与情境.templates import build_factor_templates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mine-llm", action="store_true", help="因子挖掘用真实 DeepSeek")
    ap.add_argument("--no-llm", action="store_true", help="全程模板兜底（离线）")
    ap.add_argument("--market", default="csi500")
    ap.add_argument("--freq", default="1min")
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--n", default=30, type=int, help="资产数（None 用整个指数成分）")
    # 线上 SQL 模式：运行时直连数据库取数，不落本地文件
    ap.add_argument("--sql-uri", default=None,
                    help="线上 SQL URI，如 postgresql+psycopg2://u:p@host:5432/db")
    ap.add_argument("--sql-table", default="bars", help="行情表名")
    ap.add_argument("--sql-cols", default=None,
                    help='列名映射 JSON，如 {"col_close":"close","col_time":"dt"}')
    ap.add_argument("--instruments", default=None,
                    help="限定标的，逗号分隔；省略则取表内全部")
    args = ap.parse_args()

    data_cfg = DataConfig(source="qlib", market=args.market, freq=args.freq,
                          start=args.start, end=args.end,
                          n_instruments=args.n, instruments=None, seed=0)
    # 1) 取行情并推断情境特征（SQL 直连 or 本地 qlib）
    sql_md = None
    if args.sql_uri:
        import json
        col_overrides = json.loads(args.sql_cols) if args.sql_cols else {}
        sql_cfg = SqlConfig(uri=args.sql_uri, table=args.sql_table, **col_overrides)
        insts = args.instruments.split(",") if args.instruments else None
        print("== 运行时直连线上 SQL 取数（不落本地）==")
        sql_md = SqlSource().load(sql_cfg, args.start, args.end, instruments=insts)
        strat_ds = derive_strategy_dataset(sql_md)
        print(f"   资产数={strat_ds.md.M} 期数={strat_ds.md.T} "
              f"示例标的={strat_ds.md.instruments[:3]}")
    else:
        print("== 加载真实 Qlib 行情 ==")
        md = get_data_source(data_cfg).load(data_cfg)   # 缺 qlib/数据会抛清晰 RuntimeError
        strat_ds = derive_strategy_dataset(md)
        dist = Counter(strat_ds.asset_types)
        print(f"   资产数={strat_ds.md.M} 期数={strat_ds.md.T} 资产类型分布={dict(dist)}")

    # 2) 在真实数据上挖掘因子库
    print("\n== 挖掘因子库（真实数据）==")
    mining_cfg = MiningConfig(tau_ic=0.03, theta=0.5, k_lib=12, batch_size=20,
                              replace_min_ic=0.08, replace_ic_ratio=1.3,
                              seed=0, max_iterations=15)
    llm_cfg = LLMConfig(backend="deepseek", model="deepseek-chat",
                        api_key_env="DEEPSEEK_API_KEY", base_url="https://api.deepseek.com",
                        temperature=0.8, max_tokens=2048, fallback="template", seed=0)
    if args.no_llm:
        llm_cfg.fallback = "template"
    res = run(data_cfg, mining_cfg, llm_cfg, memory_path="memory_state_real.json", md=sql_md)
    factors = res.library
    strategies = build_factor_templates(factors)
    print(f"   因子数={len(factors)} → 基于因子构建策略模板={len(strategies)}")

    # 3) 在真实数据上跑策略自动进化
    print("\n== 策略自动进化（真实数据）==")
    out = run_pipeline(use_llm=not args.no_llm, ds=strat_ds, strategies=strategies,
                       memory_path="strategy_memory_real.json")
    log, mem = out["log"], out["memory"]
    n_warn = sum(1 for s in log if s.action == "risk_warn")
    n_evol = sum(1 for s in log if s.action == "evolve")
    st = mem.stats()
    print(f"   2025窗口={len(log)} | 风险提示(减仓)={n_warn} 失灵进化={n_evol} "
          f"| 记忆: 成功={st['success']} 失败={st['fail']}")
    print("\n-- 进化轨迹（前 8 条）--")
    for s in log[:8]:
        print(f"  [{s.t0:04d},{s.t1:04d}] {s.regime:<7} {s.action:<9} "
              f"Sharpe={s.live_sharpe:+.2f} | {s.note}")


if __name__ == "__main__":
    main()
