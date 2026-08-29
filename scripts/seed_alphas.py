# -*- coding: utf-8 -*-
"""
seed_alphas.py —— WorldQuant 101 Alphas 因子库导入

将公开的 WorldQuant 101 Alphas 公式翻译为 FactorMiner 表达式引擎语法，
逐因子在真实 30min CSI 数据上做完整诊断（IC/ICIR/ave|p|/冗余检测），
通过者写入因子库（source='alpha101'），并为每个因子用 DeepSeek 生成解释。

字段映射：
  open  -> $open, high -> $high, low -> $low, close -> $close,
  volume -> $volume, amount -> $amt, returns -> $returns
算子映射：
  Rank/CsRank, Delay, Delta, SMA, Correlation->TsCorr, Covariance->TsCov,
  Scale, Sign, Abs, Log, Power, Ts_Rank->TsRank, Min->TsMin, Max->TsMax,
  StdDev->Std, Sum, Product, Regression intercept/slope/resi, Mean
"""
from __future__ import annotations
import os
import sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from factorminer.web._store import _store
from FACTOR.step1_数据接入.spec import SqlConfig, Signal
from FACTOR.step1_数据接入.data_sources import SqlSource
from FACTOR.step2_因子挖掘.expression_engine import ExpressionEngine
from FACTOR.step2_因子挖掘.evaluation import factor_diagnostics

URI = os.environ.get("FACTORMINER_SQL_URI",
                     "postgresql+psycopg2://quant:quant@localhost:5432/quant").replace("db:5432", "localhost:5432")
TABLE = os.environ.get("FACTORMINER_SQL_TABLE", "bars_30m")
INSTS = [x.strip() for x in os.environ.get("FACTORMINER_INSTRUMENTS", "").split(",") if x.strip()] or None

# --------------------------------------------------------------------------- #
# WorldQuant 101 Alphas（翻译为表达式语法）
# 格式: (alpha编号, 表达式, 简要含义)
# --------------------------------------------------------------------------- #
ALPHAS = [
    ("A01", "TsCorr(CsRank(Delay($close,1)), CsRank(Delay($volume,1)), 10)",
     "当日收盘价排名与成交量排名的10日时序相关"),
    ("A02", "Neg(TsCorr(CsRank($open), CsRank($volume), 10))",
     "开盘价与成交量排名的10日相关取负"),
    ("A03", "TsCorr(CsRank($high), CsRank($volume), 10)",
     "最高价与成交量排名的10日相关"),
    ("A04", "Neg(TsCorr(CsRank($low), CsRank($volume), 10))",
     "最低价与成交量排名的10日相关取负"),
    ("A05", "Mul(TsRank($open, 5), TsRank(Div($low, $high), 5))",
     "5日开盘价时序排名 × 最低/最高比的5日时序排名"),
    ("A06", "Neg(TsCorr($open, $volume, 10))",
     "开盘价与成交量的10日相关取负"),
    ("A07", "Add(Mul(Sign(Sub($close, Delay($close, 1))), Mul($volume, Div(Sub($high, $low), $high))), "
            "Mul(Neg(Sign(Sub(Delay($close, 1), Delay($close, 2)))), Mul(Delay($volume, 1), Div(Sub(Delay($high, 1), Delay($low, 1)), Delay($high, 1)))))",
     "成交量加权的日内振幅方向信号（次日动量）"),
    ("A08", "Neg(TsCorr($high, $volume, 10))",
     "最高价与成交量的10日相关取负"),
    ("A09", "IfElse(And(Eq(Sub($high, $low), 0), Eq(Sub(Delay($high, 1), Delay($low, 1)), 0)), "
            "Sub($close, $open), Div(Sub($close, $open), Mul(Max($high, Delay($high, 1)), 1)))",
     "日内开收差的振幅归一化信号"),
    ("A10", "Neg(TsCorr(CsRank($high), CsRank($volume), 5))",
     "最高价与成交量排名的5日相关取负"),
    ("A11", "Mul(TsRank(Sub($close, $open), 5), TsRank($volume, 5))",
     "5日开收差时序排名 × 5日成交量时序排名"),
    ("A12", "Sign(Div(Sub($close, Delay($close, 1)), Delay($close, 1)))",
     "当日涨跌符号"),
    ("A13", "Mul(Neg(CsRank(Sub($close, $open))), CsRank($volume))",
     "做空开收差排名 × 成交量排名（反转）"),
    ("A14", "Neg(TsCorr(CsRank($open), CsRank($volume), 5))",
     "开盘价与成交量排名的5日相关取负"),
    ("A15", "Div(Sub($high, $low), $close)",
     "日内振幅/收盘价（波动强度）"),
    ("A16", "Add(Mul(Sign(Sub($close, Delay($close, 1))), $volume), "
            "Mul(Sign(Sub(Delay($close, 1), Delay($close, 2))), Delay($volume, 1)))",
     "涨跌符号 × 成交量（量价确认）"),
    ("A17", "TsRank($close, 20)",
     "20日收盘价时序排名（动量）"),
    ("A18", "Div($close, TsMax($high, 20))",
     "收盘价 / 20日最高价（突破位置）"),
    ("A19", "Div($close, Delay($close, 20))",
     "20日价格比率"),
    ("A20", "Div(Sub($close, Delay($close, 20)), Delay($close, 20))",
     "20日动量（涨跌幅）"),
    ("A21", "Sub(SMA($close, 5), SMA($close, 20))",
     "5日与20日均线差（趋势）"),
    ("A22", "Div(Sub($high, TsMin($low, 20)), Sub(TsMax($high, 20), TsMin($low, 20)))",
     "收盘/最高在20日区间的相对位置"),
    ("A23", "Neg(Sub($close, SMA($close, 20)))",
     "收盘价相对20日均线偏离取负"),
    ("A24", "Sub($close, SMA($close, 20))",
     "收盘价相对20日均线偏离（正向）"),
    ("A25", "Div(Sub($close, Delay($close, 10)), Delay($close, 10))",
     "10日动量"),
    ("A26", "Div(Sub($close, Delay($close, 5)), Delay($close, 5))",
     "5日动量"),
    ("A27", "Sub(Div($close, Delay($close, 5)), 1)",
     "5日涨跌幅"),
    ("A28", "Div(Sub($close, SMA($close, 20)), SMA($close, 20))",
     "收盘价相对20日均线的百分比偏离"),
    ("A29", "Neg(CsRank(Div(Sub($close, $open), $high)))",
     "做空开收差/最高价排名（隔夜反转）"),
    ("A30", "Neg(CsRank(Sub($close, $vwap)))",
     "做空收盘价相对VWAP偏离排名"),
    ("A31", "Neg(CsRank(Std($returns, 20)))",
     "做空20日波动率排名（低波偏好）"),
    ("A32", "CsRank(Std($returns, 20))",
     "做多20日波动率排名（高波）"),
    ("A33", "CsRank(Log($volume))",
     "成交量对数排名（流动性）"),
    ("A34", "CsRank(Div($amt, $volume))",
     "每笔成交额排名（价格水平代理）"),
    ("A35", "CsRank(Div(Sub($close, $vwap), $vwap))",
     "收盘相对VWAP偏离排名"),
    ("A36", "TsRank(Div($close, $open), 20)",
     "20日开收比时序排名"),
    ("A37", "Div(TsMax($high, 5), TsMin($low, 5))",
     "5日最高/5日最低比"),
    ("A38", "TsRank(Sub($high, $low), 10)",
     "10日振幅时序排名"),
    ("A39", "Div(Sub($high, $low), SMA($close, 10))",
     "振幅/10日均价（波动率）"),
    ("A40", "Neg(TsCorr($close, $volume, 20))",
     "收盘价与成交量20日相关取负（量价背离）"),
    ("A41", "TsCorr($close, $volume, 20)",
     "收盘价与成交量20日相关（量价配合）"),
    ("A42", "TsCorr(CsRank($close), CsRank($volume), 20)",
     "收盘与成交量排名20日相关"),
    ("A43", "TsCorr($returns, $volume, 10)",
     "收益与成交量10日相关"),
    ("A44", "Neg(CsRank(Sub($vwap, Delay($vwap, 5))))",
     "做空VWAP 5日变化排名"),
    ("A45", "Neg(CsRank(Delta($close, 5)))",
     "做空5日收盘变化排名（反转）"),
    ("A46", "CsRank(Delta($close, 5))",
     "5日收盘变化排名（动量）"),
    ("A47", "Div(Sub($close, TsMin($low, 10)), Sub(TsMax($high, 10), TsMin($low, 10)))",
     "收盘价在10日区间位置"),
    ("A48", "Neg(TsCorr(CsRank($returns), CsRank($volume), 10))",
     "收益与成交量排名10日相关取负"),
    ("A49", "Div(Sub($close, $open), Add($high, 0.01))",
     "开收差/最高价（日内强度）"),
    ("A50", "Neg(CsRank(Sub($high, $low)))",
     "做空振幅排名（低波）"),
    ("A51", "CsRank(Sub($high, $low))",
     "做多振幅排名（高波博弈）"),
    ("A52", "Div(Sub($vwap, $close), $vwap)",
     "VWAP相对收盘偏离（尾盘强度）"),
    ("A53", "Sub(CsRank($close), CsRank(Delay($close, 5)))",
     "收盘价排名相对5日前变化（排名动量）"),
    ("A54", "TsRank(Div($volume, Delay($volume, 1)), 20)",
     "量比（当日/前日）20日时序排名"),
    ("A55", "Div(Div($volume, Delay($volume, 1)), Mean($volume, 20))",
     "量比 / 20日均量"),
    ("A56", "Neg(TsCorr($open, $volume, 10))",
     "开盘价与成交量10日相关取负"),
    ("A57", "Div(Sub($high, $low), Delay($close, 1))",
     "振幅/前收盘"),
    ("A58", "Neg(CsRank(Log($volume)))",
     "做空成交量对数排名"),
    ("A59", "Div($amt, SMA($amt, 10))",
     "成交额/10日均成交额（资金热度）"),
    ("A60", "TsRank($returns, 10)",
     "10日收益时序排名"),
]


def explain_alpha(aid: str, formula: str, ic: float, ave_p: float) -> str:
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
                {"role": "user", "content": f"WorldQuant Alpha 公式: {formula}\nIC={ic:.4f} ave|p|={ave_p:.4f}\n请解释这个因子在说什么、什么逻辑。"},
            ],
            temperature=0.5, max_tokens=300,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return ""


def main():
    md = SqlSource().load(SqlConfig(uri=URI, table=TABLE, instruments=INSTS),
                          "2024-01-01", "2026-08-28", instruments=INSTS)
    print(f"数据: {md.M} 标的 x {md.T} 期")
    eng = ExpressionEngine()
    lib_formulas = [f["formula"] for f in _store.list_factors(limit=500)]
    n_ok, n_red, n_err = 0, 0, 0

    for aid, formula, meaning in ALPHAS:
        try:
            sig = eng.evaluate(formula, md)
            _sig = Signal(f"alpha_{aid}", sig.values)
            diag = factor_diagnostics(_sig, md.target,
                                      library_formulas=lib_formulas,
                                      engine=eng, md=md, corr_threshold=0.8)
        except Exception as e:
            print(f"  {aid} 求值失败: {formula[:40]} ({type(e).__name__})")
            n_err += 1
            continue
        if diag["is_redundant"]:
            print(f"  {aid} 跳过(冗余 maxCorr={diag['max_corr']:.2f}) {formula[:40]}")
            n_red += 1
            continue
        lib_formulas.append(formula)
        expl = explain_alpha(aid, formula, diag["ic"], diag["ave_p"])
        _store.add_factor(f"ALPHA_{aid}", formula, ic=diag["ic"], icir=diag["icir"],
                          max_corr=diag["max_corr"], ave_p=diag["ave_p"],
                          source="alpha101", name=f"Alpha{aid}", note=meaning,
                          explanation=expl)
        n_ok += 1
        print(f"  {aid} 入库 |IC|={abs(diag['ic']):.4f} ICIR={diag['icir']:.3f} "
              f"ave|p|={diag['ave_p']:.4f} maxCorr={diag['max_corr']:.2f}  {formula[:40]}")

    print(f"\n== 汇总: 入库 {n_ok} / 冗余跳过 {n_red} / 失败 {n_err} ==")
    fs = _store.list_factors(limit=500)
    from collections import Counter
    print(f"因子库总量: {len(fs)} 条, 来源分布: {dict(Counter(f['source'] for f in fs))}")


if __name__ == "__main__":
    main()
