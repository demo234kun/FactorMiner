# -*- coding: utf-8 -*-
"""
seed_libraries.py —— 批量入库：因子库 / 因子经验 / 策略库 / 策略经验

数据源：
  1. memory_state_real.json      —— 挖掘的因子（patterns 公式）
  2. strategy_memory_real.json   —— 策略经验（success/fail）
  3. 内置策略模板 build_templates() —— 30+ 条策略，全部回测后入库
  4. 真实 30min CSI 数据回测计算 IC/ICIR/Sharpe
"""
from __future__ import annotations
import json
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from factorminer.web._store import _store
from FACTOR.step1_数据接入.spec import DataConfig, SqlConfig, LLMConfig, Signal
from FACTOR.step1_数据接入.data_sources import SyntheticSource, SqlSource
from FACTOR.step2_因子挖掘.expression_engine import ExpressionEngine
from FACTOR.step2_因子挖掘.evaluation import factor_diagnostics
from 策略回测.step2_模板与情境.templates import build_templates
from 策略回测.step3_回测引擎.backtest_report import build_backtest_report

URI = os.environ.get("FACTORMINER_SQL_URI",
                     "postgresql+psycopg2://quant:quant@localhost:5432/quant")
URI = URI.replace("db:5432", "localhost:5432")
TABLE = os.environ.get("FACTORMINER_SQL_TABLE", "bars_30m")
INSTS = [x.strip() for x in os.environ.get("FACTORMINER_INSTRUMENTS", "").split(",") if x.strip()] or None


def load_md():
    cfg = SqlConfig(uri=URI, table=TABLE, instruments=INSTS)
    return SqlSource().load(cfg, "2024-01-01", "2026-08-28", instruments=INSTS)


def explain_factor(formula: str, ic: float, icir: float, ave_p: float) -> str:
    """用 DeepSeek 生成因子解释（含义 + 逻辑）。失败返回空串。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是量化因子研究员。用 2-3 句中文解释这个因子公式的含义、交易逻辑和适用场景。"},
                {"role": "user", "content": f"公式: {formula}\nIC={ic:.4f} ICIR={icir:.3f} ave|p|={ave_p:.4f}\n请解释这个因子在说什么、什么逻辑。"},
            ],
            temperature=0.5, max_tokens=300,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return ""


def main():
    md = load_md()
    print(f"数据: {md.M} 标的 x {md.T} 期")
    eng = ExpressionEngine()

    # ---- 1) 因子入库（从 memory_state_real.json 的 patterns）----
    print("\n== 1) 因子入库（含 IC/ICIR/ave|p|/冗余检测/LLM解释）==")
    n_factor = 0
    n_redundant = 0
    try:
        with open("memory_state_real.json", encoding="utf-8") as f:
            mem = json.load(f)
        formulas = []
        for p in mem.get("patterns", []):
            d = p.get("desc", "")
            if d and d not in formulas:
                formulas.append(d)
        # 已入库因子公式（用于冗余检测）
        lib_formulas = [f["formula"] for f in _store.list_factors(limit=500)]
        for i, formula in enumerate(formulas):
            try:
                sig = eng.evaluate(formula, md)
                _sig = Signal(formula, sig.values)
                diag = factor_diagnostics(_sig, md.target,
                                          library_formulas=lib_formulas,
                                          engine=eng, md=md, corr_threshold=0.8)
                if diag["is_redundant"]:
                    print(f"  跳过(与库内因子相关 {diag['max_corr']:.2f}): {formula[:45]}")
                    n_redundant += 1
                    continue
                lib_formulas.append(formula)
            except Exception:
                continue
            fid = f"MINED{i:04d}"
            expl = explain_factor(formula, diag["ic"], diag["icir"], diag["ave_p"])
            _store.add_factor(fid, formula, ic=diag["ic"], icir=diag["icir"],
                              max_corr=diag["max_corr"], ave_p=diag["ave_p"],
                              source="mining", name=f"挖掘因子-{i}",
                              note="来自 Ralph Loop 挖掘",
                              explanation=expl)
            n_factor += 1
            print(f"  {fid} |IC|={abs(diag['ic']):.4f} ICIR={diag['icir']:.3f} "
                  f"ave|p|={diag['ave_p']:.4f} maxCorr={diag['max_corr']:.2f}  {formula[:40]}")
    except FileNotFoundError:
        print("  未找到 memory_state_real.json，跳过")
    print(f"  入库 {n_factor} 个因子（跳过冗余 {n_redundant} 个）")

    # ---- 2) 因子经验入库 ----
    print("\n== 2) 因子经验入库 ==")
    n_exp = 0
    try:
        with open("memory_state_real.json", encoding="utf-8") as f:
            mem = json.load(f)
        for p in mem.get("patterns", []):
            _store.add_factor_experience("pattern", p.get("pattern", ""),
                                         detail=p.get("desc", ""))
            n_exp += 1
        for f in mem.get("forbidden", []):
            _store.add_factor_experience("forbidden", f.get("pattern", ""),
                                         detail=f"corr={f.get('corr')} factors={f.get('factors')}")
            n_exp += 1
        for i in mem.get("insights", []):
            _store.add_factor_experience("insight", i)
            n_exp += 1
    except FileNotFoundError:
        print("  未找到 memory_state_real.json，跳过")
    print(f"  入库 {n_exp} 条因子经验")

    # ---- 3) 策略入库（内置模板全部回测）----
    print("\n== 3) 策略库入库（内置模板回测）==")
    n_strat = 0
    templates = build_templates()
    for tp in templates:
        try:
            r = build_backtest_report(
                eng.evaluate(tp.signal, md).values, md.target, md.times,
                direction=tp.direction, periods_per_year=252, label=tp.name)
            m = r["metrics"]
        except Exception:
            continue
        _store.add_strategy(tp.id, tp.name, tp.signal, category=tp.category,
                            direction=tp.direction,
                            description=tp.description or f"内置模板: {tp.name}",
                            metrics=m, report=r, n_periods=r["n_periods"])
        n_strat += 1
        print(f"  {tp.id} {tp.name} Sharpe={m['sharpe']:.2f} 总收益={m['total_return']*100:.1f}%")
    print(f"  入库 {n_strat} 条策略")

    # ---- 4) 策略经验入库 ----
    print("\n== 4) 策略经验入库 ==")
    n_se = 0
    try:
        with open("strategy_memory_real.json", encoding="utf-8") as f:
            sm = json.load(f)
        for e in sm.get("successes", []):
            _store.add_strategy_experience(
                e.get("id", f"SE{n_se}"), e.get("strategy_id", ""),
                e.get("strategy_name", ""), "success", reason=e.get("reason", ""),
                regime=e.get("regime", ""), sharpe=e.get("metrics", {}).get("sharpe", 0),
                category=e.get("category", ""), signal=e.get("signal", ""))
            n_se += 1
        for e in sm.get("failures", []):
            _store.add_strategy_experience(
                e.get("id", f"SE{n_se}"), e.get("strategy_id", ""),
                e.get("strategy_name", ""), "fail", reason=e.get("reason", ""),
                regime=e.get("regime", ""), sharpe=e.get("metrics", {}).get("sharpe", 0),
                category=e.get("category", ""), signal=e.get("signal", ""))
            n_se += 1
    except FileNotFoundError:
        print("  未找到 strategy_memory_real.json，跳过")
    print(f"  入库 {n_se} 条策略经验")

    print("\n== 汇总 ==")
    print(f"因子库: {len(_store.list_factors())} 条")
    print(f"因子经验: {len(_store.list_factor_experience())} 条")
    print(f"策略库: {len(_store.list_strategies())} 条")
    print(f"策略经验: {len(_store.list_strategy_experience())} 条")


if __name__ == "__main__":
    main()
