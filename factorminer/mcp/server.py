# -*- coding: utf-8 -*-
"""
mcp/server.py —— 面向智能体（Agent）的 FactorMiner 服务（MCP stdio 协议）

使用标准 MCP stdio JSON-RPC 协议（initialize / tools/list / tools/call），
不依赖特定版本的 mcp 库，可直接被任何 MCP 客户端以 stdio 方式接入。

启动: python -m factorminer.mcp.server
工具:
  - mine_factors(k_lib, n_iterations): 运行一轮因子挖掘，返回摘要
  - list_library(): 列出当前因子库
  - get_memory(): 读取经验记忆
  - evaluate_formula(formula): 评估单因子公式的 IC/ICIR
"""
from __future__ import annotations
import os
import re
import sys
import json
from typing import Any, Dict

from FACTOR.step1_数据接入.spec import DataConfig, MiningConfig, LLMConfig, SqlConfig
from FACTOR.step2_因子挖掘.ralph_loop import run, summarize
from FACTOR.step2_因子挖掘.expression_engine import ExpressionEngine, ExpressionError
from FACTOR.step2_因子挖掘.evaluation import ic, icir
from FACTOR.step1_数据接入.data_sources import SyntheticSource, SqlSource
from 策略回测.step4_策略进化.agent import train_2024, evolve_2025
from 策略回测.step1_数据适配.strategy_data import generate_strategy_data, slice_dataset, derive_strategy_dataset
from 策略回测.step4_策略进化.memory import StrategyMemory

CACHE: Dict[str, Any] = {"result": None}
STRAT_CACHE: Dict[str, Any] = {"ds": None, "ds25": None, "memory": None}


def _cfgs(k_lib: int, n_iter: int):
    data_cfg = DataConfig(source="synthetic", market="csi500", freq="10min",
                          start="2024-01-01", end="2026-12-31",
                          n_instruments=15, n_periods=500, seed=0)
    mining_cfg = MiningConfig(tau_ic=0.03, theta=0.5, k_lib=k_lib, batch_size=20,
                              replace_min_ic=0.08, replace_ic_ratio=1.3,
                              seed=0, max_iterations=n_iter)
    llm_cfg = LLMConfig(fallback="template", seed=0)
    return data_cfg, mining_cfg, llm_cfg


def _load_real_md(start: str, end: str):
    """若设置了 FACTORMINER_SQL_URI / QLIB_SQL_URI，则直连 Postgres 取真实行情；
    否则返回 None，上层回退到合成数据。docker 内的 db:5432 自动改写为 localhost:5432。"""
    uri = os.environ.get("FACTORMINER_SQL_URI") or os.environ.get("QLIB_SQL_URI")
    if not uri:
        return None
    uri = uri.replace("db:5432", "localhost:5432")
    table = os.environ.get("FACTORMINER_SQL_TABLE", "bars_d")
    raw = os.environ.get("FACTORMINER_INSTRUMENTS", "")
    insts = [re.sub(r"\.(SH|SZ|BJ|XSHG|XSHE)$", "", x.strip())
             for x in raw.split(",") if x.strip()] or None
    cfg = SqlConfig(uri=uri, table=table, instruments=insts)
    return SqlSource().load(cfg, start, end, instruments=insts)


# --------------------------------------------------------------------------- #
# 工具实现
# --------------------------------------------------------------------------- #
def mine_factors(k_lib: int = 12, n_iterations: int = 15) -> str:
    data_cfg, mining_cfg, llm_cfg = _cfgs(k_lib, n_iterations)
    md = _load_real_md(data_cfg.start, data_cfg.end)
    if md is not None:
        result = run(data_cfg, mining_cfg, llm_cfg,
                     memory_path="memory_state_real.json", md=md)
        CACHE["source"] = "sql"
    else:
        result = run(data_cfg, mining_cfg, llm_cfg, memory_path="memory_state.json")
        CACHE["source"] = "synthetic"
    CACHE["result"] = result
    return summarize(result)


def list_library() -> list:
    res = CACHE["result"]
    if not res:
        return []
    return [{"id": f.id, "formula": f.formula, "ic": round(float(f.ic), 4),
            "icir": round(float(f.icir), 3), "max_corr": round(float(f.max_corr), 2)}
           for f in res.library]


def get_memory() -> dict:
    res = CACHE["result"]
    if not res:
        return {"patterns": [], "forbidden": [], "insights": []}
    return {"patterns": res.memory.patterns, "forbidden": res.memory.forbidden,
            "insights": res.memory.insights}


def evaluate_formula(formula: str) -> dict:
    data_cfg = DataConfig(source="synthetic", start="2024-01-01", end="2026-12-31")
    md = _load_real_md(data_cfg.start, data_cfg.end)
    if md is not None:
        data, src = md, "sql"
    else:
        data = SyntheticSource().load(DataConfig(source="synthetic", n_instruments=15,
                                                 n_periods=500, seed=0))
        src = "synthetic"
    try:
        sig = ExpressionEngine().evaluate(formula, data)
    except ExpressionError as e:
        return {"ic": None, "icir": None, "error": str(e), "source": src}
    return {"ic": round(float(ic(sig, data.target)), 4),
            "icir": round(float(icir(sig, data.target)), 3), "error": None, "source": src}


def mine_strategy(n_assets: int = 20, n_periods: int = 1600, seed: int = 0) -> dict:
    """在 2024 数据上训练策略经验记忆（成功/失败 + 情境），返回记忆规模。
    若设置了 FACTORMINER_SQL_URI，则改用真实行情（derive_strategy_dataset 推断情境）。"""
    md = _load_real_md("2024-01-01", "2026-12-31")
    if md is not None:
        ds = derive_strategy_dataset(md)
        T = len(ds.md.times)
        half = T // 2
        ds24 = slice_dataset(ds, 0, half)
        ds25 = slice_dataset(ds, half, T)
        mem = StrategyMemory(path="strategy_memory_mcp_real.json")
        train_2024(ds24, mem, win=120, step=60, sharpe_thresh=0.4)
        STRAT_CACHE["ds"] = ds
        STRAT_CACHE["ds25"] = ds25
        STRAT_CACHE["memory"] = mem
        st = mem.stats()
        return {"success": st["success"], "fail": st["fail"],
                "n_assets": ds.md.M, "trained_on": "real-sql"}
    ds = generate_strategy_data(n_assets=n_assets, n_periods=n_periods, seed=seed)
    half = n_periods // 2
    ds24 = slice_dataset(ds, 0, half)
    mem = StrategyMemory(path="strategy_memory_mcp.json")
    train_2024(ds24, mem, win=120, step=60, sharpe_thresh=0.4)
    STRAT_CACHE["ds"] = ds
    STRAT_CACHE["ds25"] = slice_dataset(ds, half, n_periods)
    STRAT_CACHE["memory"] = mem
    st = mem.stats()
    return {"success": st["success"], "fail": st["fail"],
            "n_assets": n_assets, "trained_on": "2024"}


def evolve_strategy(use_llm: bool = True) -> dict:
    """在 2025 数据上滚动测试：监控减仓 + 失灵自动进化。需先 mine_strategy。"""
    mem = STRAT_CACHE.get("memory")
    ds25 = STRAT_CACHE.get("ds25")
    if mem is None or ds25 is None:
        return {"error": "请先调用 mine_strategy 建立经验记忆"}
    llm = None
    if use_llm:
        try:
            from FACTOR.step2_因子挖掘.llm_proposer import LLMProposer
            from FACTOR.step1_数据接入.spec import LLMConfig
            llm = LLMProposer(LLMConfig())
        except Exception:
            llm = None
    log = evolve_2025(ds25, mem, llm=llm, win=90, step=30, verbose=False)
    n_warn = sum(1 for x in log if x.action == "risk_warn")
    n_evol = sum(1 for x in log if x.action == "evolve")
    return {"windows": len(log), "risk_warn": n_warn, "evolve": n_evol,
            "memory": mem.stats()}


TOOL_IMPL = {
    "mine_factors": mine_factors,
    "list_library": list_library,
    "get_memory": get_memory,
    "evaluate_formula": evaluate_formula,
    "mine_strategy": mine_strategy,
    "evolve_strategy": evolve_strategy,
}

TOOL_DEFS = [
    {
        "name": "mine_factors",
        "description": "运行一轮 FactorMiner 因子挖掘，返回因子库摘要文本。",
        "inputSchema": {"type": "object", "properties": {
            "k_lib": {"type": "integer", "description": "目标因子库规模 K", "default": 12},
            "n_iterations": {"type": "integer", "description": "最大迭代轮数", "default": 15},
        }, "required": []},
    },
    {
        "name": "list_library",
        "description": "列出当前因子库中的因子（id, 公式, |IC|, ICIR, maxCorr）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_memory",
        "description": "读取经验记忆：推荐方向（成功模式）与禁区（高相关方向）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "evaluate_formula",
        "description": "评估给定因子公式（配置了 FACTORMINER_SQL_URI 则基于真实行情，否则合成数据），返回 {ic, icir, error, source}。",
        "inputSchema": {"type": "object", "properties": {
            "formula": {"type": "string", "description": "如 Neg(CsRank($close))"},
        }, "required": ["formula"]},
    },
    {
        "name": "mine_strategy",
        "description": "在 2024 数据上训练策略经验记忆（成功/失败经验 + 情境特征），返回记忆规模。",
        "inputSchema": {"type": "object", "properties": {
            "n_assets": {"type": "integer", "description": "资产数", "default": 20},
            "n_periods": {"type": "integer", "description": "总期数（前一半作2024训练）", "default": 1600},
            "seed": {"type": "integer", "description": "随机种子", "default": 0},
        }, "required": []},
    },
    {
        "name": "evolve_strategy",
        "description": "在 2025 数据上滚动测试：监控到失败情境则风险提示+减仓；策略失灵则检索记忆、LLM推荐3-5迭代并回测验证。需先调用 mine_strategy。",
        "inputSchema": {"type": "object", "properties": {
            "use_llm": {"type": "boolean", "description": "是否用 DeepSeek 生成策略迭代（否则用参数变体兜底）", "default": True},
        }, "required": []},
    },
]


# --------------------------------------------------------------------------- #
# JSON-RPC 调度
# --------------------------------------------------------------------------- #
def _dispatch(method: str, params: dict):
    if method == "initialize":
        return {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "FactorMiner", "version": "0.1.0"}}
    if method == "tools/list":
        return {"tools": TOOL_DEFS}
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        fn = TOOL_IMPL.get(name)
        if fn is None:
            return {"content": [{"type": "text", "text": f"未知工具: {name}"}],
                    "isError": True}
        try:
            out = fn(**args)
        except Exception as e:  # noqa: BLE001
            return {"content": [{"type": "text", "text": f"工具执行错误: {e}"}],
                    "isError": True}
        return {"content": [{"type": "text",
                             "text": json.dumps(out, ensure_ascii=False)}],
                "isError": False}
    # 未知方法 / 通知
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method", "")
        if method.startswith("notifications/") or msg.get("id") is None:
            continue  # 通知无需回复
        result = _dispatch(method, msg.get("params", {}) or {})
        if result is None:
            result = {}
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg.get("id"),
                                    "result": result}, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
