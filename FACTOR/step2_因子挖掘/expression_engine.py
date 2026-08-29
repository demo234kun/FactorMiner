# -*- coding: utf-8 -*-
"""
expression.py —— 因子公式 DSL 解析与求值

语法（论文示例: Neg(CsRank(Div(Sub($close,$vwap),$vwap)))）：
  - 叶子: $field   (field ∈ open,high,low,close,volume,amt,vwap,returns)
  - 字面量: 整数 / 浮点数（窗口大小、阈值等）
  - 函数调用: Name(Arg, Arg, ...) —— Name 必须是 OPERATORS 中的算子名
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Union
import numpy as np
from FACTOR.step2_因子挖掘.operators import OPERATORS, get_operator
from FACTOR.step1_数据接入.spec import MarketData, Signal


class ExpressionError(Exception):
    pass


# 常见同义算子映射，提升对 LLM 输出的容错
_ALIASES = {
    "Rank": "CsRank",
    "StdDev": "Std",
    "MeanDev": "Mean",
    "AbsVal": "Abs",
}


# --------------------------------------------------------------------------- #
# 语法树节点
# --------------------------------------------------------------------------- #
@dataclass
class Leaf:
    field: str


@dataclass
class Literal:
    value: float


@dataclass
class Call:
    name: str
    args: List[Union["Leaf", "Literal", "Call"]]


# --------------------------------------------------------------------------- #
# 词法 + 递归下降解析
# --------------------------------------------------------------------------- #
class _Tokenizer:
    def __init__(self, s: str):
        self.s = s.replace(" ", "")
        self.i = 0

    def peek(self):
        return self.s[self.i] if self.i < len(self.s) else ""

    def next(self):
        c = self.s[self.i]
        self.i += 1
        return c

    def read_name(self):
        start = self.i
        while self.i < len(self.s) and (self.s[self.i].isalnum() or self.s[self.i] == "_"):
            self.i += 1
        return self.s[start:self.i]

    def read_number(self):
        start = self.i
        while self.i < len(self.s) and (self.s[self.i].isdigit() or self.s[self.i] == "."):
            self.i += 1
        return self.s[start:self.i]


def _parse_formula(text: str) -> Call:
    tok = _Tokenizer(text)

    def parse_expr():
        c = tok.peek()
        if c == "$":
            tok.next()
            name = tok.read_name()
            return Leaf(name)
        if c.isdigit() or c == ".":
            num = tok.read_number()
            return Literal(float(num))
        # function call
        name = tok.read_name()
        if not name:
            raise ExpressionError(f"无法解析公式片段: '{text[tok.i:]}'")
        if tok.peek() != "(":
            raise ExpressionError(f"算子 '{name}' 后缺少 '('")
        tok.next()  # (
        args: List[Union[Leaf, Literal, Call]] = []
        if tok.peek() == ")":
            tok.next()
            return Call(name, [])
        while True:
            args.append(parse_expr())
            nxt = tok.peek()
            if nxt == ",":
                tok.next()
                continue
            elif nxt == ")":
                tok.next()
                break
            else:
                raise ExpressionError(f"公式 '{text}' 中期望 ',' 或 ')'，得到 '{nxt}'")
        return Call(name, args)

    return parse_expr()


# --------------------------------------------------------------------------- #
# 求值引擎
# --------------------------------------------------------------------------- #
class ExpressionEngine:
    def __init__(self):
        self.ops = OPERATORS

    def _eval(self, node, data: MarketData) -> np.ndarray:
        if isinstance(node, Leaf):
            if not hasattr(data, node.field):
                raise ExpressionError(
                    f"未知行情字段 '${node.field}'。可用: open,high,low,close,volume,amt,vwap,returns")
            arr = getattr(data, node.field)
            if not isinstance(arr, np.ndarray) or arr.ndim != 2:
                raise ExpressionError(f"字段 '${node.field}' 不是 (T,M) 数组")
            return arr.astype(float)
        if isinstance(node, Literal):
            return np.full((data.T, data.M), float(node.value))
        if isinstance(node, Call):
            name = _ALIASES.get(node.name, node.name)
            try:
                spec = get_operator(name)
            except KeyError as e:
                raise ExpressionError(str(e))
            # 将参数拆分为数据操作数与字面量，按 spec.params 顺序
            data_args: List[np.ndarray] = []
            lit_args: List[float] = []
            pi = 0
            for p in spec.params:
                if p == "expr":
                    arg = self._eval(node.args[pi], data)
                    data_args.append(arg)
                    pi += 1
                elif p in ("int", "float"):
                    lit = node.args[pi]
                    if not isinstance(lit, Literal):
                        raise ExpressionError(
                            f"算子 '{node.name}' 的第 {pi+1} 个参数应为字面量，得到 {node.args[pi]}")
                    lit_args.append(lit.value)
                    pi += 1
            if len(data_args) != spec.arity:
                raise ExpressionError(
                    f"算子 '{node.name}' 数据操作数数量不符：期望 {spec.arity}，得到 {len(data_args)}")
            return spec.fn(*data_args, *lit_args)
        raise ExpressionError(f"未知节点类型: {type(node)}")

    def evaluate(self, formula: str, data: MarketData) -> Signal:
        try:
            ast = _parse_formula(formula)
        except ExpressionError:
            raise
        except Exception as e:
            raise ExpressionError(f"公式解析失败: {formula} -> {e}")
        values = self._eval(ast, data)
        if not isinstance(values, np.ndarray) or values.ndim != 2:
            raise ExpressionError(f"公式 '{formula}' 求值结果不是 (T,M) 数组")
        return Signal(formula=formula, values=values.astype(float))
