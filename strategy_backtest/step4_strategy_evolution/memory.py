# -*- coding: utf-8 -*-
"""
memory.py —— 策略经验记忆

经验条目包含：情境（regime + 资产分布 + 市场统计）、策略、绩效、成败、原因。
支持按情境相似度检索「相似成功/失败经验」，供 LLM 进化时作为先验。
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List
import json
from strategy_backtest.step2_template_context.context import WindowContext, context_similarity


@dataclass
class StrategyExperience:
    id: str
    strategy_id: str
    strategy_name: str
    category: str
    outcome: str                       # 'success' | 'fail'
    reason: str
    metrics: Dict[str, float]
    regime: str
    market_return: float
    market_vol: float
    breadth: float
    asset_mix: Dict[str, int] = field(default_factory=dict)
    signal: str = ""


class StrategyMemory:
    def __init__(self, path: str = "strategy_memory.json"):
        self.path = path
        self.successes: List[StrategyExperience] = []
        self.failures: List[StrategyExperience] = []
        self._load()

    def add(self, exp: StrategyExperience):
        if exp.outcome == "success":
            self.successes.append(exp)
        else:
            self.failures.append(exp)
        self._save()

    def retrieve_similar(self, ctx: WindowContext, k: int = 5) -> List[StrategyExperience]:
        """检索与当前情境最相似的成功经验（含少量失败作负例）。"""
        pool = list(self.successes) + list(self.failures)
        scored = []
        for e in pool:
            sc = 0.6 if e.regime == ctx.regime else 0.0
            keys = set(e.asset_mix) | set(ctx.asset_mix)
            tot = max(1, sum(e.asset_mix.values()))
            dist = sum(abs(e.asset_mix.get(kk, 0) - ctx.asset_mix.get(kk, 0)) for kk in keys)
            sc += 0.4 * (1.0 - dist / tot)
            scored.append((sc, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:k]]

    def format_prior(self, ctx: WindowContext, k: int = 5) -> str:
        sim = self.retrieve_similar(ctx, k)
        if not sim:
            return "（记忆库为空，暂无历史经验）"
        lines = [f"当前情境: regime={ctx.regime}, 资产分布={ctx.asset_mix}, "
                 f"市场收益={ctx.market_return:.4f}, 波动={ctx.market_vol:.4f}"]
        for e in sim:
            tag = "成功" if e.outcome == "success" else "失败"
            lines.append(
                f"- [{tag}] {e.strategy_name}({e.category}) "
                f"regime={e.regime} 资产={e.asset_mix} "
                f"Sharpe={e.metrics.get('sharpe',0):.2f} "
                f"原因: {e.reason} | 信号: {e.signal}")
        return "\n".join(lines)

    def stats(self) -> Dict:
        return {"success": len(self.successes), "fail": len(self.failures)}

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"successes": [asdict(e) for e in self.successes],
                           "failures": [asdict(e) for e in self.failures]}, f,
                          ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            for e in d.get("successes", []):
                self.successes.append(StrategyExperience(**e))
            for e in d.get("failures", []):
                self.failures.append(StrategyExperience(**e))
        except Exception:
            pass
