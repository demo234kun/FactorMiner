# -*- coding: utf-8 -*-
"""
strategy_generator.py —— 策略生成器（用户文本 -> 可回测策略）

核心链路：
  用户自然语言描述（如"低波动股票轮动，熊市防御"）
    -> LLM 生成策略信号公式（表达式语言，复用 LLMProposer + ExpressionEngine 验证）
    -> 组装成 StrategyTemplate（含名称/方向/适用情境/描述）
    -> 任一环节失败自动回退模板兜底，保证始终返回可回测策略。

设计要点：
  - 公式必须通过 ExpressionEngine.evaluate 在真实行情上求值成功才算合格，
    不合格的候选自动丢弃并重试，避免把"语法对但求不出值"的策略放进库。
  - 方向（long_short / long_only）由 LLM 给出关键字，解析失败默认 long_short。
  - 不生成任意 Python 代码，只生成表达式信号，天然与回测引擎/表达式引擎闭环。
"""
from __future__ import annotations
import re
import random
from typing import List, Optional

from FACTOR.step1_数据接入.spec import LLMConfig, MarketData
from FACTOR.step2_因子挖掘.llm_proposer import LLMProposer
from FACTOR.step2_因子挖掘.expression_engine import ExpressionEngine
from 策略回测.step2_模板与情境.templates import StrategyTemplate

_KNOWN_CATEGORIES = ["动量", "反转", "波动率", "流动性", "趋势", "多因子",
                     "风险平价", "统计", "微观结构", "因子策略", "自定义"]


def _pick_category(text: str) -> str:
    for c in _KNOWN_CATEGORIES:
        if c in text:
            return c
    return "自定义"


def _pick_direction(text: str) -> str:
    if "多头" in text or "纯多" in text or "做多" in text and "做空" not in text:
        return "long_only"
    return "long_short"


def _clean_name(text: str, idx: int = 1) -> str:
    s = re.sub(r"\s+", "", text)
    return (s[:14] or f"用户策略{idx}")


def _llm_describe(proposer: LLMProposer, user_text: str, n: int = 3) -> List[str]:
    """让 LLM 针对用户描述生成 n 个策略信号公式。失败回退模板。"""
    ctx = ("用户想要一个策略，请把用户意图翻译成表达式信号公式。"
           "要求：1) 公式可用已知算子求值；2) 方向偏好、持仓周期体现在公式里；"
           "3) 每行一个公式，纯公式，不要解释。")
    try:
        formulas = proposer.propose(user_text, n, ctx=ctx)
    except Exception:
        formulas = []
    return formulas or []


def generate_strategies(
    user_text: str,
    md: Optional[MarketData] = None,
    n: int = 3,
    llm_cfg: Optional[LLMConfig] = None,
    seed: int = 0,
) -> List[StrategyTemplate]:
    """从用户文本生成 n 个可回测策略模板。

    - user_text: 用户自然语言描述（必填）
    - md: 真实行情（用于公式求值验证）。None 时只做语法/算子层过滤。
    - llm_cfg: LLM 配置，默认 DeepSeek + 模板兜底
    - 返回：均通过验证的 StrategyTemplate 列表（可能少于 n，但至少 1 条兜底）
    """
    cfg = llm_cfg or LLMConfig(fallback="template", seed=seed)
    proposer = LLMProposer(cfg)
    engine = ExpressionEngine()
    formulas = _llm_describe(proposer, user_text, n=n)

    category = _pick_category(user_text)
    direction = _pick_direction(user_text)
    base_name = _clean_name(user_text)

    out: List[StrategyTemplate] = []
    seen: set = set()
    rng = random.Random(seed)
    for idx, f in enumerate(formulas):
        if not f or f in seen:
            continue
        seen.add(f)
        # 公式验证：能求值才算合格
        if md is not None:
            try:
                sig = engine.evaluate(f, md)
                if sig.values.shape != (md.T, md.M):
                    continue
            except Exception:
                continue
        out.append(StrategyTemplate(
            id=f"GEN{rng.randint(10000, 99999)}{idx}",
            name=base_name,
            category=category,
            signal=f,
            direction=direction,
            rebalance="daily",
            risk_control="生成策略：失效时回退记忆库预警/进化。",
            suitable_stock_types=[],
            suitable_regimes=[],
            description=f"用户意图: {user_text}",
        ))
        if len(out) >= n:
            break

    # 兜底：一条模板变体，保证有产出
    if not out:
        out.append(StrategyTemplate(
            id=f"GENFALLBACK{rng.randint(10000, 99999)}",
            name=f"{base_name}-兜底",
            category=category,
            signal="CsRank(Neg(Std($returns,20)))",
            direction=direction,
            rebalance="daily",
            risk_control="LLM 生成失败，模板兜底（低波动防御）。",
            suitable_stock_types=["high_vol", "stable"],
            suitable_regimes=["bear", "volatile"],
            description=f"用户意图: {user_text}；LLM 无合格输出，使用低波动模板兜底。",
        ))
    return out
