# -*- coding: utf-8 -*-
"""
FactorMiner 复刻版 —— 核心数据契约与接口规范 (spec.py)

本文件是所有子模块的唯一契约来源。各模块实现者 MUST 严格遵循以下
数据结构与函数签名，禁止改动本文件的公开接口（仅可新增可选字段）。

数据形状约定
------------
- 市场行情以 ``MarketData`` 表示：每个字段（open/high/low/close/volume/amt/
  vwap/returns）均为 ``np.ndarray``，形状 ``(T, M)``，T=时间步数，M=资产数。
- 因子信号 ``Signal.values`` 形状 ``(T, M)``，语义与行情同维。
- 目标收益 ``target`` 形状 ``(T, M)``，为下一根 K 线的 open-to-close 收益。
- IC 定义为每个时间步的截面 Spearman 秩相关（信号 vs 目标），再取时序均值
  与其标准差之比得到 ICIR。相关度 ρ 为两信号时序平均的截面 Spearman。
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# --------------------------------------------------------------------------- #
# 行情与信号
# --------------------------------------------------------------------------- #
@dataclass
class MarketData:
    """统一行情容器。字段均为 (T, M) 的 ndarray。"""
    times: list
    instruments: list
    open: "np.ndarray"
    high: "np.ndarray"
    low: "np.ndarray"
    close: "np.ndarray"
    volume: "np.ndarray"
    amt: "np.ndarray"
    vwap: "np.ndarray"
    returns: "np.ndarray"  # 当期收益（用于算子、亦可作为 target 来源）
    target: "np.ndarray"   # 下一根 K 线 open-to-close 收益 (T, M)

    @property
    def T(self) -> int:
        return self.close.shape[0]

    @property
    def M(self) -> int:
        return self.close.shape[1]

    def field(self, name: str) -> "np.ndarray":
        """按名字取 (T, M) 字段，供表达式引擎叶子节点解析。"""
        return getattr(self, name)

    def clipped(self, t0: int, t1: int) -> "MarketData":
        """返回时间维 [t0, t1) 的子行情（字段按行切片）。"""
        return MarketData(
            times=self.times[t0:t1],
            instruments=list(self.instruments),
            open=self.open[t0:t1].copy(),
            high=self.high[t0:t1].copy(),
            low=self.low[t0:t1].copy(),
            close=self.close[t0:t1].copy(),
            volume=self.volume[t0:t1].copy(),
            amt=self.amt[t0:t1].copy(),
            vwap=self.vwap[t0:t1].copy(),
            returns=self.returns[t0:t1].copy(),
            target=self.target[t0:t1].copy(),
        )


@dataclass
class Signal:
    """一次候选评估产生的因子信号。"""
    formula: str
    values: "np.ndarray"  # (T, M)

    @property
    def T(self) -> int:
        return self.values.shape[0]

    @property
    def M(self) -> int:
        return self.values.shape[1]


# --------------------------------------------------------------------------- #
# 因子库与候选结果
# --------------------------------------------------------------------------- #
@dataclass
class Factor:
    """准入到因子库 L 的因子。"""
    id: str
    name: str
    formula: str
    ic: float = 0.0
    icir: float = 0.0
    max_corr: float = 0.0       # 与库内因子的最大 |ρ|
    rank: int = 0
    signal: Optional["np.ndarray"] = None  # 已计算的 (T,M) 信号值，用于相关性计算


@dataclass
class CandidateResult:
    """单候选因子经多阶段验证管线后的结果。"""
    formula: str
    ic: float
    icir: float
    max_corr: float
    passed_ic: bool
    passed_corr: bool
    admitted: bool
    rejected_reason: str = ""       # 'low_ic' | 'high_corr' | 'corr_replace' | '' 
    replaced_id: Optional[str] = None  # Stage 2.5 顶替的因子 id
    fitness: float = 0.0            # Φ(α)，默认取 |IC|


@dataclass
class Trajectory:
    """一轮挖掘轨迹 τ_t。"""
    iteration: int
    candidates: list


# --------------------------------------------------------------------------- #
# 经验记忆
# --------------------------------------------------------------------------- #
@dataclass
class MemoryState:
    """经验记忆 M：成功模式 / 禁区 / 战略洞察 / 库状态。"""
    patterns: list = field(default_factory=list)    # 推荐方向 P_succ
    forbidden: list = field(default_factory=list)   # 禁区 P_fail
    insights: list = field(default_factory=list)    # 战略洞察 I
    library_state: dict = field(default_factory=dict)  # S: size, logs, saturation

    def to_prior_text(self) -> str:
        """生成注入 LLM 提示词的先验文本（推荐方向 / 禁忌方向）。"""
        lines = ["[经验记忆先验]"]
        if self.patterns:
            lines.append("推荐方向(高成功):")
            for p in self.patterns[:8]:
                lines.append(f"  - {p.get('pattern')}: {p.get('desc','')} (成功率 {p.get('rate','?')})")
        if self.forbidden:
            lines.append("禁忌方向(高相关):")
            for f in self.forbidden[:8]:
                lines.append(f"  - {f.get('pattern')}: 与因子 {f.get('factors')} 相关 {f.get('corr')}")
        if self.insights:
            lines.append("战略洞察:")
            for i in self.insights[:6]:
                lines.append(f"  - {i}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
@dataclass
class MiningConfig:
    """挖掘超参（默认取论文附录 B/C）。"""
    tau_ic: float = 0.04           # 准入 IC 阈值
    theta: float = 0.5             # 相关性预算（默认 A 股）
    k_lib: int = 40                # 目标库规模 K
    batch_size: int = 40           # 每轮 LLM 生成候选数
    fast_asset_ratio: float = 0.3  # Stage 1 小资产子集比例
    replace_min_ic: float = 0.10   # Stage 2.5: IC≥0.10
    replace_ic_ratio: float = 1.3  # Stage 2.5: IC ≥ 1.3×被顶替因子
    seed: int = 0
    max_iterations: int = 30
    relax_ic: Optional[float] = None   # 消融用：覆盖 tau_ic（如 0.02）
    relax_theta: Optional[float] = None  # 消融用：覆盖 theta（如 0.85）


@dataclass
class DataConfig:
    source: str = "synthetic"      # 'qlib' | 'synthetic'
    market: str = "csi500"
    freq: str = "10min"
    start: str = "2024-01-01"
    end: str = "2024-12-31"
    n_instruments: int = 30        # synthetic 用：资产数
    n_periods: int = 2000          # synthetic 用：时间步（10min）
    instruments: Optional[list] = None  # qlib 用：指定成分股
    seed: int = 0                   # synthetic 用：随机种子


@dataclass
class SqlConfig:
    """线上 SQL 数据源配置：运行时按需查询，不落本地文件。

    程序在需要时（如 run_real 按窗口取数）直接连线上库，只拉取
    [start, end] × instruments 这一段行情，构造 MarketData 返回。
    uri 为 SQLAlchemy 连接串，可指向 MySQL/PostgreSQL/任意 SQLAlchemy 后端。
    """
    uri: str = ""                          # SQLAlchemy URI，如 mysql+pymysql://u:p@host:3306/db
    table: str = "bars"                   # 原始 K 线表名
    col_instrument: str = "instrument"
    col_time: str = "datetime"
    col_open: str = "open"
    col_high: str = "high"
    col_low: str = "low"
    col_close: str = "close"
    col_volume: str = "volume"
    col_amount: str = "amount"
    market: str = "csi500"
    instruments: Optional[list] = None     # None=取表内全部；否则限定成分股
    limit_per_query: int = 5_000_000      # 安全上限，防止误拉全量落地


@dataclass
class LLMConfig:
    backend: str = "deepseek"
    model: str = "deepseek-chat"
    api_key_env: str = "DEEPSEEK_API_KEY"
    base_url: str = "https://api.deepseek.com"
    temperature: float = 0.8
    max_tokens: int = 2048
    fallback: str = "template"     # 无 key/网络时回退到模板生成器
    seed: int = 0                  # 模板生成器随机种子


@dataclass
class LibraryResult:
    """Ralph Loop 产物。"""
    library: list                  # list[Factor]
    memory: MemoryState
    trajectories: list            # list[Trajectory]
    n_iterations: int = 0


# --------------------------------------------------------------------------- #
# 算子签名类型（供 operators/expression 模块校验）
# --------------------------------------------------------------------------- #
TS = "ts"   # 时序算子：逐资产沿时间维
CS = "cs"   # 截面算子：逐时间步跨资产维
EL = "el"   # 逐元素算子：单点变换


def _rank2(x: "np.ndarray") -> "np.ndarray":
    """沿 axis=1 的截面秩（用于 Spearman）。"""
    return np.argsort(np.argsort(x, axis=1, kind="stable"), axis=1).astype(float)


def spearman_per_t(sig_a: "np.ndarray", sig_b: "np.ndarray") -> "np.ndarray":
    """对每个时间步 t 计算 sig_a[t], sig_b[t] 的截面 Spearman 相关，返回 (T,)。向量化。"""
    import numpy as np
    ra = _rank2(np.where(np.isfinite(sig_a), sig_a, 0.0))
    rb = _rank2(np.where(np.isfinite(sig_b), sig_b, 0.0))
    da = ra - ra.mean(axis=1, keepdims=True)
    db = rb - rb.mean(axis=1, keepdims=True)
    num = (da * db).sum(axis=1)
    den = np.sqrt((da * da).sum(axis=1) * (db * db).sum(axis=1))
    out = np.where(den == 0, 0.0, num / np.where(den == 0, 1.0, den))
    return out.astype(float)
