# -*- coding: utf-8 -*-
"""
llm.py —— 符号因子生成器（LLMProposer）

优先用 DeepSeek（OpenAI 兼容接口）生成公式化 alpha 因子；
任何失败（无 key / 网络 / 解析失败）自动回退到确定性模板生成器，
保证系统始终能产出 n 个语法合法候选。
"""
from __future__ import annotations
import os
import re
from typing import List
import random
from FACTOR.step1_data_ingestion.spec import LLMConfig
from FACTOR.step2_factor_mining.operators import OPERATORS, list_operators
from FACTOR.step2_factor_mining.expression_engine import _ALIASES

FIELDS = ["$open", "$high", "$low", "$close", "$volume", "$amt", "$vwap", "$returns"]
WINDOWS = [3, 5, 10, 20, 30, 48]
THRESH = [0.01, 0.02, 0.03, 0.05]


class LLMProposer:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)

    def propose(self, prior_text: str, n: int, ctx: str = "") -> List[str]:
        formulas = self._try_deepseek(prior_text, n, ctx)
        if len(formulas) >= 1:
            # 补齐到 n 个
            while len(formulas) < n:
                formulas.append(self._gen(depth=3))
            return formulas[:n]
        # 完全失败 -> 模板兜底
        return [self._gen(depth=3) for _ in range(n)]

    # ---- DeepSeek ------------------------------------------------------- #
    def _try_deepseek(self, prior_text: str, n: int, ctx: str) -> List[str]:
        api_key = os.environ.get(self.cfg.api_key_env)
        if not api_key:
            return []
        try:
            from openai import OpenAI
        except Exception:
            return []
        try:
            client = OpenAI(api_key=api_key, base_url=self.cfg.base_url)
            system = (
                "你是量化因子研究员。请用 FactorMiner 算子词汇生成公式化 alpha 因子。"
                f"可用算子: {', '.join(list_operators())}。"
                f"可用字段: {', '.join(FIELDS)}。"
                "语法示例: Neg(CsRank(Div(Sub($close,$vwap),$vwap)))。"
                "每行一个公式，不要额外解释。"
            )
            user = f"{prior_text}\n请生成 {n} 个候选因子公式。"
            if ctx:
                user += f"\n约束上下文: {ctx}"
            resp = client.chat.completions.create(
                model=self.cfg.model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=self.cfg.temperature,
                max_tokens=self.cfg.max_tokens,
            )
            text = resp.choices[0].message.content or ""
            return self._parse_formulas(text, n)
        except Exception as e:
            import sys
            print(f"[LLMProposer] DeepSeek 调用失败，回退模板: {e}", file=sys.stderr)
            return []

    @staticmethod
    def _normalize_fields(text: str) -> str:
        """把裸字段名（open/high/...）补成 $field，避免 LLM 漏写 $ 前缀。"""
        fields = ["open", "high", "low", "close", "volume", "amt", "vwap", "returns"]
        pat = re.compile(r"(?<![\w$])(" + "|".join(fields) + r")(?![\w])")
        return pat.sub(lambda m: "$" + m.group(1), text)

    @staticmethod
    def _parse_formulas(text: str, n: int) -> List[str]:
        text = LLMProposer._normalize_fields(text)
        out: List[str] = []
        # 提取平衡括号的表达式
        for line in text.splitlines():
            line = line.strip().strip("`").strip()
            m = re.search(r"([A-Za-z][A-Za-z]*\()", line)
            if not m:
                continue
            start = m.start()
            depth = 0
            end = -1
            for i in range(start, len(line)):
                if line[i] == "(":
                    depth += 1
                elif line[i] == ")":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end == -1:
                continue
            expr = line[start:end + 1]
            # 基础合法性：以已知算子开头
            name = re.match(r"([A-Za-z][A-Za-z]*)", expr).group(1)
            if name in OPERATORS or name in _ALIASES:
                out.append(expr)
            if len(out) >= n:
                break
        return out

    # ---- 模板生成器（兜底） -------------------------------------------- #
    def _gen(self, depth: int) -> str:
        if depth <= 0 or self.rng.random() < 0.35:
            return self.rng.choice(FIELDS)
        name = self.rng.choice(list(OPERATORS.keys()))
        spec = OPERATORS[name]
        args = []
        for p in spec.params:
            if p == "expr":
                args.append(self._gen(depth - 1))
            elif p == "int":
                args.append(str(self.rng.choice(WINDOWS)))
            else:
                args.append(str(self.rng.choice(THRESH)))
        return f"{name}({','.join(args)})"
