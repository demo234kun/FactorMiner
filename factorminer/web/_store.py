# -*- coding: utf-8 -*-
"""
_store.py —— 四记忆库持久化层（Postgres）

因子库 / 因子经验 / 策略库 / 策略经验 四张表的读写封装。
供 web 主页对话框、回测验证、经验入库使用。
"""
from __future__ import annotations
import os
import json
from typing import List, Optional

from sqlalchemy import create_engine, text

DEFAULT_URI = os.environ.get(
    "FACTORMINER_SQL_URI",
    "postgresql+psycopg2://quant:quant@localhost:5432/quant",
).replace("db:5432", "localhost:5432")


class MemoryStore:
    def __init__(self, uri: str = DEFAULT_URI):
        self.engine = create_engine(uri, pool_pre_ping=True)

    # ---------------- 因子库 ---------------- #
    def add_factor(self, fid: str, formula: str, ic: float = 0.0, icir: float = 0.0,
                   max_corr: float = 0.0, name: str = "", source: str = "manual",
                   note: str = "", ave_p: float = 1.0, explanation: str = "") -> None:
        with self.engine.begin() as c:
            c.execute(text("""
                INSERT INTO factor_library(id,name,formula,ic,icir,max_corr,source,note,ave_p,explanation)
                VALUES(:id,:name,:formula,:ic,:icir,:max_corr,:source,:note,:ave_p,:explanation)
                ON CONFLICT(id) DO UPDATE SET ic=EXCLUDED.ic, icir=EXCLUDED.icir,
                  max_corr=EXCLUDED.max_corr, name=EXCLUDED.name, source=EXCLUDED.source,
                  note=EXCLUDED.note, ave_p=EXCLUDED.ave_p, explanation=EXCLUDED.explanation
            """), {"id": fid, "name": name, "formula": formula, "ic": float(ic),
                   "icir": float(icir), "max_corr": float(max_corr),
                   "source": source, "note": note, "ave_p": float(ave_p),
                   "explanation": explanation})

    def list_factors(self, limit: int = 200) -> List[dict]:
        with self.engine.connect() as c:
            rows = c.execute(text("""
                SELECT id,name,formula,ic,icir,max_corr,source,note,ave_p,explanation,created_at
                FROM factor_library ORDER BY abs(ic) DESC NULLS LAST LIMIT :lim
            """), {"lim": limit}).mappings().all()
        return [dict(r) for r in rows]

    # ---------------- 因子经验 ---------------- #
    def add_factor_experience(self, kind: str, content: str, detail: str = "") -> None:
        with self.engine.begin() as c:
            c.execute(text("""
                INSERT INTO factor_experience(kind,content,detail)
                VALUES(:kind,:content,:detail)
            """), {"kind": kind, "content": content, "detail": detail})

    def list_factor_experience(self, limit: int = 100) -> List[dict]:
        with self.engine.connect() as c:
            rows = c.execute(text("""
                SELECT id,kind,content,detail,created_at FROM factor_experience
                ORDER BY id DESC LIMIT :lim
            """), {"lim": limit}).mappings().all()
        return [dict(r) for r in rows]

    # ---------------- 策略库 ---------------- #
    def add_strategy(self, sid: str, name: str, signal: str, category: str = "自定义",
                     direction: str = "long_short", description: str = "",
                     metrics: Optional[dict] = None, report: Optional[dict] = None,
                     n_periods: int = 0) -> None:
        m = metrics or {}
        with self.engine.begin() as c:
            c.execute(text("""
                INSERT INTO strategy_library(
                  id,name,category,signal,direction,description,
                  sharpe,annualized,total_return,max_drawdown,win_rate,rank_ic,
                  n_periods,report_json)
                VALUES(:id,:name,:category,:signal,:direction,:description,
                  :sharpe,:annualized,:total_return,:max_drawdown,:win_rate,:rank_ic,
                  :n_periods,:report_json)
                ON CONFLICT(id) DO UPDATE SET
                  sharpe=EXCLUDED.sharpe, annualized=EXCLUDED.annualized,
                  total_return=EXCLUDED.total_return, max_drawdown=EXCLUDED.max_drawdown,
                  win_rate=EXCLUDED.win_rate, rank_ic=EXCLUDED.rank_ic,
                  n_periods=EXCLUDED.n_periods, report_json=EXCLUDED.report_json
            """), {
                "id": sid, "name": name, "category": category, "signal": signal,
                "direction": direction, "description": description,
                "sharpe": float(m.get("sharpe", 0) or 0),
                "annualized": float(m.get("annualized", 0) or 0),
                "total_return": float(m.get("total_return", 0) or 0),
                "max_drawdown": float(m.get("max_drawdown", 0) or 0),
                "win_rate": float(m.get("win_rate", 0) or 0),
                "rank_ic": float(m.get("rank_ic", 0) or 0),
                "n_periods": int(n_periods or 0),
                "report_json": json.dumps(report or {}, ensure_ascii=False),
            })

    def list_strategies(self, limit: int = 200) -> List[dict]:
        with self.engine.connect() as c:
            rows = c.execute(text("""
                SELECT id,name,category,signal,direction,description,
                  sharpe,annualized,total_return,max_drawdown,win_rate,rank_ic,
                  n_periods,created_at
                FROM strategy_library ORDER BY sharpe DESC NULLS LAST LIMIT :lim
            """), {"lim": limit}).mappings().all()
        return [dict(r) for r in rows]

    # ---------------- 策略经验 ---------------- #
    def add_strategy_experience(self, sid: str, strategy_id: str, strategy_name: str,
                                outcome: str, reason: str = "", regime: str = "",
                                sharpe: float = 0.0, category: str = "",
                                market_return: float = 0.0, market_vol: float = 0.0,
                                signal: str = "") -> None:
        with self.engine.begin() as c:
            c.execute(text("""
                INSERT INTO strategy_experience(
                  id,strategy_id,strategy_name,category,outcome,reason,regime,
                  sharpe,market_return,market_vol,signal)
                VALUES(:id,:strategy_id,:strategy_name,:category,:outcome,:reason,:regime,
                  :sharpe,:market_return,:market_vol,:signal)
            """), {"id": sid, "strategy_id": strategy_id, "strategy_name": strategy_name,
                   "category": category, "outcome": outcome, "reason": reason,
                   "regime": regime, "sharpe": float(sharpe),
                   "market_return": float(market_return), "market_vol": float(market_vol),
                   "signal": signal})

    def list_strategy_experience(self, limit: int = 200) -> List[dict]:
        with self.engine.connect() as c:
            rows = c.execute(text("""
                SELECT id,strategy_id,strategy_name,category,outcome,reason,regime,
                  sharpe,market_return,market_vol,signal,created_at
                FROM strategy_experience ORDER BY id DESC LIMIT :lim
            """), {"lim": limit}).mappings().all()
        return [dict(r) for r in rows]


_store = MemoryStore()
