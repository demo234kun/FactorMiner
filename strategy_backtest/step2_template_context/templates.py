# -*- coding: utf-8 -*-
"""
templates.py —— 策略模式模板库（尽量全）

每个 StrategyTemplate 包含：
  - signal: 用算子词汇在 $字段 上构造的截面信号公式（可被 ExpressionEngine 求值）
  - direction: long_short / long_only
  - suitable_stock_types: 该策略倾向有效的股票特征
  - suitable_regimes: 该策略倾向有效的市场/时间段特征
  - description: 自然语言模式描述（中文）
  - risk_control: 风险控制说明

build_templates() 组合「手工精选 + 程序化变体」，覆盖动量/反转/波动/流动性/趋势/
多因子/突破/风险平价/统计 等大类，数量尽量多、尽量全。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class StrategyTemplate:
    id: str
    name: str
    category: str
    signal: str
    direction: str = "long_short"      # long_short | long_only
    rebalance: str = "daily"
    risk_control: str = ""
    suitable_stock_types: List[str] = field(default_factory=list)
    suitable_regimes: List[str] = field(default_factory=list)
    description: str = ""


# --------------------------------------------------------------------------- #
# 手工精选
# --------------------------------------------------------------------------- #
_CURATED: List[dict] = [
    # ---- 截面动量 ----
    dict(id="MOM20", name="截面动量(20)", category="动量",
         signal="CsRank(Div(Sub($close,Delay($close,20)),Delay($close,20)))",
         suitable_stock_types=["trending", "momentum"], suitable_regimes=["bull", "rally"],
         description="做多过去20期收益最高的资产、做空最低的，捕捉截面动量。",
         risk_control="单资产权重上限5%，跌破60期均线清仓。"),
    dict(id="MOM60", name="截面动量(60)", category="动量",
         signal="CsRank(Div(Sub($close,Delay($close,60)),Delay($close,60)))",
         suitable_stock_types=["trending", "momentum"], suitable_regimes=["bull", "trend"],
         description="更长窗口截面动量，过滤短期噪声。",
         risk_control="同 MOM20。"),
    dict(id="MOMTS", name="时序动量转截面", category="动量",
         signal="CsRank(TsRank($close,20))",
         suitable_stock_types=["trending"], suitable_regimes=["bull", "rally"],
         description="先算每只资产时序动量再截面排序。",
         risk_control="窗口内波动过大时降权。"),
    dict(id="MOMSHORT", name="短期动量", category="动量",
         signal="CsRank(Delay($returns,5))",
         suitable_stock_types=["momentum", "high_vol"], suitable_regimes=["rally"],
         description="捕捉5期短期动量。",
         risk_control="高换手，单边成本敏感。"),
    # ---- 反转 ----
    dict(id="REV1D", name="隔夜反转", category="反转",
         signal="Neg(CsRank($returns))",
         suitable_stock_types=["mean_reverting", "stable"], suitable_regimes=["volatile", "sideways"],
         description="做多昨日跌幅最大者、做空涨幅最大者，捕捉日内反转。",
         risk_control="趋势市失效，需结合regime开关。"),
    dict(id="REVMA", name="均线偏离反转", category="反转",
         signal="Neg(CsRank(Sub($close,SMA($close,20))))",
         suitable_stock_types=["mean_reverting"], suitable_regimes=["sideways", "volatile"],
         description="价格偏离20期均线越远越做多（均值回归）。",
         risk_control="趋势行情止损。"),
    dict(id="REVRSI", name="快慢均线反转", category="反转",
         signal="Neg(CsRank(Sub(SMA($close,5),SMA($close,20))))",
         suitable_stock_types=["mean_reverting"], suitable_regimes=["sideways"],
         description="短期均线与长期均线乖离的反转信号。",
         risk_control="双均线死叉停。"),
    dict(id="VWAPREV", name="VWAP偏离反转", category="反转",
         signal="Neg(CsRank(Sub($close,$vwap)))",
         suitable_stock_types=["mean_reverting", "large_liq"], suitable_regimes=["sideways"],
         description="价格低于VWAP则做多，回归VWAP。",
         risk_control="放量跌破VWAP止损。"),
    dict(id="GAPREV", name="跳空反转", category="反转",
         signal="Neg(CsRank(Sub($open,$close)))",
         suitable_stock_types=["mean_reverting"], suitable_regimes=["volatile"],
         description="开盘相对昨收跳空，反向博弈。",
         risk_control="重大消息日禁用。"),
    # ---- 波动率 ----
    dict(id="LOWVOL", name="低波动优选", category="波动率",
         signal="Neg(CsRank(Std($returns,20)))",
         suitable_stock_types=["high_vol", "stable"], suitable_regimes=["bear", "volatile"],
         description="做多波动最低的资产，防御属性。",
         risk_control="低波资产流动性差时慎配。"),
    dict(id="VOLBET", name="高波动博弈", category="波动率",
         signal="CsRank(Std($returns,20))",
         suitable_stock_types=["high_vol"], suitable_regimes=["rally", "volatile"],
         description="做多高波动资产，博取弹性。",
         risk_control="严格止损，仓位减半。"),
    dict(id="VOLTIMING", name="波动率择时", category="波动率",
         signal="Scale(Sub(Std($returns,5),Std($returns,20)))",
         suitable_stock_types=["high_vol"], suitable_regimes=["volatile"],
         description="短期波动相对长期抬升时做多。",
         risk_control="波动率骤降离场。"),
    # ---- 流动性 ----
    dict(id="LIQ", name="流动性因子", category="流动性",
         signal="CsRank(Log($volume))",
         suitable_stock_types=["large_liq", "small_liq"], suitable_regimes=["bull", "calm"],
         description="做多成交最活跃资产。",
         risk_control="流动性枯竭期禁用。"),
    dict(id="ILLIQ", name="非流动性溢价", category="流动性",
         signal="Neg(CsRank(Div(Abs(Delta($close,1)),$amt)))",
         suitable_stock_types=["small_liq"], suitable_regimes=["bear"],
         description="Amihud非流动性，做多低流动性高溢价资产。",
         risk_control="小市值流动性风险高。"),
    dict(id="TURNOVER", name="成交额排序", category="流动性",
         signal="CsRank($amt)",
         suitable_stock_types=["large_liq"], suitable_regimes=["bull"],
         description="按成交额排序，做多大成交。",
         risk_control="无。"),
    # ---- 趋势 ----
    dict(id="MACROSS", name="均线金叉", category="趋势",
         signal="CsRank(Sub(SMA($close,5),SMA($close,20)))",
         suitable_stock_types=["trending"], suitable_regimes=["bull", "trend"],
         description="短均线上穿长均线做多。",
         risk_control="均线缠绕期空仓。"),
    dict(id="MACROSS2", name="均线金叉(长)", category="趋势",
         signal="CsRank(Sub(SMA($close,10),SMA($close,60)))",
         suitable_stock_types=["trending"], suitable_regimes=["trend"],
         description="更长窗口均线交叉。",
         risk_control="同 MACROSS。"),
    dict(id="DONCH", name="唐奇安突破", category="趋势",
         signal="CsRank(Sub($close,TsMax($close,20)))",
         suitable_stock_types=["trending", "momentum"], suitable_regimes=["trend", "bull"],
         description="价格突破20期高点做多。",
         risk_control="假突破止损。"),
    dict(id="DONCHL", name="区间突破(低)", category="趋势",
         signal="CsRank(Sub($close,TsMin($close,20)))",
         suitable_stock_types=["trending"], suitable_regimes=["bull"],
         description="价格突破20期低点（强势）做多。",
         risk_control="假突破止损。"),
    # ---- 多因子组合 ----
    dict(id="MF3", name="三因子等权", category="多因子",
         signal="CsRank(Add(Add(Div(Sub($close,Delay($close,20)),Delay($close,20)),Neg($returns)),Neg(Std($returns,20))))",
         suitable_stock_types=["trending", "mean_reverting", "high_vol"], suitable_regimes=["bull", "sideways"],
         description="动量+反转+低波三因子等权合成。",
         risk_control="单因子极端时降权。"),
    dict(id="MF5", name="五因子排名平均", category="多因子",
         signal="CsRank(Add(Add(Add(Add(CsRank(Div(Sub($close,Delay($close,20)),Delay($close,20))),CsRank(Neg($returns))),CsRank(Neg(Std($returns,20)))),CsRank(Log($volume))),CsRank(Sub($close,$vwap))))",
         suitable_stock_types=["trending", "mean_reverting", "high_vol", "large_liq"], suitable_regimes=["bull", "sideways", "volatile"],
         description="动量/反转/低波/流动性/VWAP 五因子排名平均。",
         risk_control="分散化降低单一因子风险。"),
    dict(id="QUALPROXY", name="质量代理", category="多因子",
         signal="CsRank(Sub(Neg(Std($returns,20)),CsRank($returns)))",
         suitable_stock_types=["stable", "large_liq"], suitable_regimes=["bear", "calm"],
         description="低波动叠加反转，作为质量代理。",
         risk_control="无。"),
    # ---- 风险平价 / 波动择价 ----
    dict(id="VOLTARGET", name="风险调整动量", category="风险平价",
         signal="CsRank(Div(Sub($close,Delay($close,20)),Mul(Delay($close,20),Std($returns,20))))",
         suitable_stock_types=["trending", "high_vol"], suitable_regimes=["bull", "volatile"],
         description="动量除以波动率，风险加权。",
         risk_control="波动率突增自动降仓。"),
    dict(id="PAIRSXS", name="截面残差", category="统计",
         signal="CsRank(Resi($close,20))",
         suitable_stock_types=["mean_reverting", "stable"], suitable_regimes=["sideways"],
         description="价格对时间趋势回归的残差，做多偏离下沿。",
         risk_control="趋势行情止损。"),
    dict(id="RANKMOM", name="排名动量", category="统计",
         signal="CsRank(Sub(CsRank($close),Delay(CsRank($close),5)))",
         suitable_stock_types=["trending"], suitable_regimes=["bull", "trend"],
         description="截面排名本身的动量。",
         risk_control="排名切换期空仓。"),
    # ---- 其他微观结构 ----
    dict(id="CLLOC", name="收盘位置", category="微观结构",
         signal="CsRank(Div(Sub($close,$low),Sub($high,$low)))",
         suitable_stock_types=["trending", "momentum"], suitable_regimes=["bull", "rally"],
         description="收盘贴近高点=强势，做多。",
         risk_control="无。"),
    dict(id="RANGE", name="振幅扩张", category="微观结构",
         signal="CsRank(Sub($high,$low))",
         suitable_stock_types=["high_vol"], suitable_regimes=["volatile"],
         description="做多振幅扩张资产（波动事件）。",
         risk_control="事件消退离场。"),
    dict(id="VOLCONF", name="量价确认动量", category="微观结构",
         signal="CsRank(Mul(Div(Sub($close,Delay($close,20)),Delay($close,20)),Log($volume)))",
         suitable_stock_types=["trending", "large_liq"], suitable_regimes=["bull", "rally"],
         description="动量乘以成交量，量价确认。",
         risk_control="缩量背离止损。"),
]


# --------------------------------------------------------------------------- #
# 程序化变体（窗口扫描，扩充数量与覆盖）
# --------------------------------------------------------------------------- #
def _variants() -> List[dict]:
    out: List[dict] = []
    # 动量窗口扫描
    for w in [10, 30, 40, 80, 100]:
        out.append(dict(
            id=f"MOM{w}", name=f"截面动量({w})", category="动量",
            signal=f"CsRank(Div(Sub($close,Delay($close,{w})),Delay($close,{w})))",
            suitable_stock_types=["trending", "momentum"], suitable_regimes=["bull", "trend"],
            description=f"窗口={w} 的截面动量变体。", risk_control="同 MOM20。"))
    # 反转窗口扫描
    for w in [3, 10, 30]:
        out.append(dict(
            id=f"REVMA{w}", name=f"均线偏离反转({w})", category="反转",
            signal=f"Neg(CsRank(Sub($close,SMA($close,{w}))))",
            suitable_stock_types=["mean_reverting"], suitable_regimes=["sideways", "volatile"],
            description=f"窗口={w} 的均线偏离反转。", risk_control="趋势行情止损。"))
    # 低波窗口扫描
    for w in [5, 10, 40, 60]:
        out.append(dict(
            id=f"LOWVOL{w}", name=f"低波动优选({w})", category="波动率",
            signal=f"Neg(CsRank(Std($returns,{w})))",
            suitable_stock_types=["high_vol", "stable"], suitable_regimes=["bear", "volatile"],
            description=f"窗口={w} 的低波动防御。", risk_control="流动性风险。"))
    # 突破窗口扫描
    for w in [10, 30, 40, 60]:
        out.append(dict(
            id=f"DONCH{w}", name=f"唐奇安突破({w})", category="趋势",
            signal=f"CsRank(Sub($close,TsMax($close,{w})))",
            suitable_stock_types=["trending", "momentum"], suitable_regimes=["trend", "bull"],
            description=f"窗口={w} 的突破。", risk_control="假突破止损。"))
    # 均线交叉扫描
    for (s, l) in [(3, 15), (10, 30), (20, 50), (5, 40)]:
        out.append(dict(
            id=f"MAC{s}{l}", name=f"均线金叉({s},{l})", category="趋势",
            signal=f"CsRank(Sub(SMA($close,{s}),SMA($close,{l})))",
            suitable_stock_types=["trending"], suitable_regimes=["bull", "trend"],
            description=f"短{s}/长{l}均线交叉。", risk_control="缠绕期空仓。"))
    return out


def build_templates() -> List[StrategyTemplate]:
    out: List[StrategyTemplate] = []
    for d in _CURATED + _variants():
        out.append(StrategyTemplate(
            id=d["id"], name=d["name"], category=d["category"],
            signal=d["signal"], direction=d.get("direction", "long_short"),
            rebalance=d.get("rebalance", "daily"),
            risk_control=d.get("risk_control", ""),
            suitable_stock_types=d.get("suitable_stock_types", []),
            suitable_regimes=d.get("suitable_regimes", []),
            description=d.get("description", ""),
        ))
    return out


def build_factor_templates(factors, top_k: int = 4) -> List[StrategyTemplate]:
    """把已挖掘的因子库直接转换为策略模板（实现「基于这些因子」的策略层）。

    - 每个因子公式本身即一个截面信号 → 一条策略；
    - 额外生成 1 条「因子等权组合(top_k)」多因子策略，组合 |IC| 最高的 k 个因子。
    """
    out: List[StrategyTemplate] = []
    for f in factors:
        out.append(StrategyTemplate(
            id=f"F-{f.id}", name=f"因子策略-{f.name or f.id}", category="因子策略",
            signal=f.formula, direction="long_short",
            rebalance="daily",
            risk_control="基于已挖掘因子；失效时回退记忆进化。",
            suitable_stock_types=[], suitable_regimes=[],
            description=f"直接复用挖掘因子 {f.id}: {f.formula}（|IC|={getattr(f,'ic',0):.3f}）",
        ))
    # 多因子组合：取 |IC| 最高的 top_k 个因子等权
    ranked = sorted(factors, key=lambda x: abs(getattr(x, "ic", 0) or 0), reverse=True)[:top_k]
    if len(ranked) >= 2:
        inner = ranked[0].formula
        for f in ranked[1:]:
            inner = f"Add({inner},{f.formula})"
        ensemble = f"CsRank({inner})"
        out.append(StrategyTemplate(
            id="F-ENSEMBLE", name=f"因子等权组合(top{len(ranked)})", category="因子策略",
            signal=ensemble, direction="long_short", rebalance="daily",
            risk_control="多因子分散，降低单一因子失效风险。",
            suitable_stock_types=[], suitable_regimes=[],
            description=f"组合 {len(ranked)} 个高|IC|因子: " +
                        ", ".join(f.id for f in ranked),
        ))
    return out


# 类别汇总（供记忆与展示）
CATEGORIES = sorted({t.category for t in build_templates()})
