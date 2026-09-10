# -*- coding: utf-8 -*-
"""
memory.py —— 经验记忆（论文 F/E/R 算子）

F (formation):   从本轮轨迹中提取成功模式 P_succ 与禁区 P_fail
E (evolution):   合并/去重/再分类，维护库状态与饱和指标
R (retrieval):   生成注入 LLM 的先验文本（推荐方向 / 禁忌方向）
"""
from __future__ import annotations
from typing import List, Optional
import json
import os
import re
from FACTOR.step1_data_ingestion.spec import MemoryState, Trajectory, CandidateResult, Factor, MiningConfig
from FACTOR.step2_factor_mining.operators import OPERATORS


def _template(formula: str) -> str:
    """从公式提取算子组合作为模式模板。"""
    ops = [m for m in re.findall(r"[A-Z][A-Za-z]+", formula) if m in OPERATORS]
    return "+".join(sorted(set(ops))) if ops else "raw"


class Memory:
    def __init__(self, path: Optional[str] = None):
        self.path = path
        self.state = MemoryState()
        if path and os.path.exists(path):
            self.load()

    # ---- F: formation --------------------------------------------------- #
    def formation(self, trajectory: Trajectory) -> MemoryState:
        patterns: List[dict] = []
        forbidden: List[dict] = []
        for c in trajectory.candidates:
            tpl = _template(c.formula)
            if c.admitted and c.replaced_id is None:
                patterns.append({
                    "pattern": tpl, "desc": c.formula,
                    "rate": "high", "examples": [c.formula],
                })
            elif c.rejected_reason in ("high_corr", "corr_replace"):
                forbidden.append({
                    "pattern": tpl, "factors": c.replaced_id or "lib",
                    "corr": round(float(c.max_corr), 2),
                })
        form = MemoryState(patterns=patterns, forbidden=forbidden, insights=[],
                           library_state={})
        return form

    # ---- E: evolution --------------------------------------------------- #
    def evolution(self, form: MemoryState, library_size: int = 0,
                  saturation: float = 0.0) -> None:
        # 合并 patterns
        by_key = {p["pattern"]: p for p in self.state.patterns}
        for p in form.patterns:
            if p["pattern"] in by_key:
                ex = by_key[p["pattern"]].setdefault("examples", [])
                if p["desc"] not in ex:
                    ex.append(p["desc"])
            else:
                by_key[p["pattern"]] = p
        # 合并 forbidden
        fk = {f["pattern"]: f for f in self.state.forbidden}
        for f in form.forbidden:
            fk[f["pattern"]] = f
        # 再分类：若某 pattern 与某个 forbidden pattern 高度重合（此处用 corr 阈值近似），移入 forbidden
        # 简化：若同一 pattern 既在 patterns 又在 forbidden（被证明高相关），优先 forbidden
        for k in list(by_key.keys()):
            if k in fk:
                by_key.pop(k)
        # 容量上限
        self.state.patterns = list(by_key.values())[:20]
        self.state.forbidden = list(fk.values())[:20]
        # 库状态
        self.state.library_state = {
            "size": library_size,
            "saturation": round(float(saturation), 3),
        }

    # ---- R: retrieval --------------------------------------------------- #
    def retrieval(self, library: List[Factor]) -> str:
        self.state.library_state["size"] = len(library)
        return self.state.to_prior_text()

    # ---- 洞察 & 持久化 --------------------------------------------------- #
    def add_insight(self, text: str) -> None:
        if text not in self.state.insights:
            self.state.insights.append(text)
        self.state.insights = self.state.insights[:10]

    def save(self) -> None:
        if not self.path:
            return
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({
                "patterns": self.state.patterns,
                "forbidden": self.state.forbidden,
                "insights": self.state.insights,
                "library_state": self.state.library_state,
            }, fh, ensure_ascii=False, indent=2)

    def load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        self.state = MemoryState(
            patterns=d.get("patterns", []),
            forbidden=d.get("forbidden", []),
            insights=d.get("insights", []),
            library_state=d.get("library_state", {}),
        )
