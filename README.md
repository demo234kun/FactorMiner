# FactorMiner — Quantitative Strategy Self-Evolution Platform

> **LLM-Driven Factor Mining → Statistical Gatekeeping → Backtest Validation → Memory Evolution**
>
> A practical implementation inspired by the *FactorMiner* paper (Wang et al., 2026), building a complete quantitative research loop from factor generation, diagnosis, backtesting to strategy self-evolution.
>
> 基于论文 *FactorMiner*（Wang et al., 2026）的 Ralph Loop 思想，构建从因子生成、诊断、回测到策略自进化的完整量化研究闭环。

---

## Research Background / 研究背景

### Problem Statement / 问题定义

Formulaic alpha factor mining is a critical yet challenging task in quantitative investment, characterized by a vast search space and the need for domain-informed, interpretable signals. However, finding novel signals becomes increasingly difficult as the library grows due to high redundancy — the so-called **"Correlation Red Sea"** problem.

公式化 alpha 因子挖掘是量化投资中一项关键而艰巨的任务，其特点是搜索空间巨大且需要具有领域知识的可解释信号。然而，随着因子库的增长，由于高冗余性，发现新的正交信号变得越来越困难——这就是所谓的 **"相关性红海"** 问题。

### The FactorMiner Paper / FactorMiner 论文

This project is inspired by and implements key ideas from:

> **[1]** Yanlong Wang, Jian Xu, Hongkang Zhang, Shao-Lun Huang, Danny Dongning Sun, and Xiao-Ping Zhang. "FactorMiner: A Self-Evolving Agent with Skills and Experience Memory for Financial Alpha Discovery." *arXiv preprint arXiv:2602.14670*, 2026.
> Presented at: **ICLR 2026 Workshop on Memory for LLM-Based Agentic Systems (MemAgents)**, April 27, 2026.
> [[Paper]](https://arxiv.org/abs/2602.14670) [[HTML]](https://arxiv.org/html/2602.14670)

The paper proposes **FactorMiner**, a lightweight and flexible self-evolving agent framework designed to navigate the factor discovery landscape through continuous knowledge accumulation. It combines:

- **Modular Skill Architecture**: Encapsulates systematic financial evaluation into executable tools (60+ operators, multi-stage validation pipeline).
- **Experience Memory**: Distills historical mining trials into actionable insights — successful patterns and failure constraints.
- **Ralph Loop Paradigm**: Retrieve → Generate → Evaluate → Distill — iteratively using memory priors to guide exploration.

### WorldQuant 101 Formulaic Alphas / WorldQuant 101 因子库

This project also integrates the classic alpha factor library from:

> **[2]** Zura Kakushadze. "101 Formulaic Alphas." *Wilmott Magazine*, 2016(84), pp. 72–80. arXiv:1601.00991.
> [[Paper]](https://arxiv.org/abs/1601.00991) [[SSRN]](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2701346)

The paper presents explicit formulas for 101 real-life quantitative trading alphas from WorldQuant LLC, with an average pairwise correlation of 15.9%. This project translates 60 of these alphas into the expression engine DSL and validates them against real A-share market data.

### Related Work / 相关工作

The expression engine operators and evaluation metrics draw from established quantitative finance practices:

> **[3]** Marcos López de Prado. *Advances in Financial Machine Learning*. Wiley, 2018. (IC/ICIR evaluation methodology, Purged K-Fold CV)

> **[4]** Thomas Starke, et al. "Alternative Data in Quantitative Finance." In *Machine Learning for Asset Management* (eds. Duc Nguyen, et al.), 2019. (Factor evaluation metrics)

> **[5]** Devry Wang, et al. "EvoAgent: Towards Automated LLM Agent Evolution." arXiv:2501.14637, 2025. (Agent evolution paradigm for multi-agent systems)

---

## 🎯 Overview / 概述

**English:**

Quantitative research suffers from two bottlenecks:

1. **Human-driven alpha factor discovery** is slow, experience-dependent, and fails to accumulate knowledge across mining sessions.
2. **Strategy failure diagnosis** is absent — when a strategy stops working, there is no systematic way to understand why or learn from it.

FactorMiner automates the full loop: an LLM generates candidate factor expressions, a custom expression engine evaluates them against real market data, a four-dimensional diagnostic gate filters for quality and diversity, validated factors feed into backtested strategies, and success/failure experiences are persisted into four memory libraries for future evolution.

Key design decisions inherited from the FactorMiner paper:

- **Memory-guided exploration**: Successful factor patterns (e.g., higher-moment regimes, trend-regression adaptivity) and failure regions (e.g., VWAP-deviation variants, standardized returns) are stored to guide future mining.
- **Global library perspective**: Each candidate is evaluated not in isolation, but by how it complements the existing library — enforced via the `maxCorr ≥ 0.8` redundancy gate.
- **Multi-stage evaluation**: IC screening → correlation check → batch dedup → full validation, balancing efficiency and accuracy.

**中文：**

量化研究存在两大瓶颈：(1) 人工驱动的 alpha 因子发现依赖经验、效率低下，且无法跨挖掘会话积累知识；(2) 策略失效后缺乏系统性归因与经验沉淀机制。

FactorMiner 自动化了完整闭环：LLM 生成候选因子表达式，自定义表达式引擎在真实行情上求值，四维诊断门禁过滤质量与冗余，验证通过的因子进入策略回测，成功/失败经验持久化至四个记忆库，驱动策略自进化。

从 FactorMiner 论文继承的核心设计思想：

- **记忆引导的探索**：成功的因子模式（如高阶矩体制、趋势回归适应性）和失败区域（如 VWAP 偏离变体、标准化收益）被存储以指导未来挖掘。
- **全局因子库视角**：每个候选因子不是孤立评估，而是评估其对现有因子库的补充性——通过 `maxCorr ≥ 0.8` 冗余门禁强制执行。
- **多阶段评估**：IC 筛选 → 相关性检查 → 批次去重 → 全量验证，平衡效率与准确性。

---

## 🏗 Architecture / 架构

```
┌─────────────────────────────────────────────────────────────────┐
│  User (Natural Language)                                        │
│  "做多低波动做空高波动" / "Find mean-reversion factors"          │
└──────────────┬──────────────────────────────────────────────────┘
               │  Intent Recognition (DeepSeek + keyword fallback)
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  LLM Proposal Layer                                            │
│  • Factor formula generation (expression engine DSL)           │
│  • Strategy text → signal template                              │
│  • Factor explanation generation (Chinese)                      │
└──────────────┬──────────────────────────────────────────────────┘
               │  Candidate expression
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Expression Engine (48 operators, AST whitelist)                │
│  TsRank / CsRank / TsCorr / Resi / Delta / ...                 │
│  • Vectorized sliding window (40s → 0.4s per factor, 100×)     │
│  • No arbitrary code execution — safe sandbox                  │
└──────────────┬──────────────────────────────────────────────────┘
               │  Raw signal matrix
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Four-Dimensional Diagnostic Gate                              │
│  • IC (predictive power)                                       │
│  • ICIR (stability)                                            │
│  • ave|p| (statistical significance)                           │
│  • maxCorr (redundancy vs existing library, ≥0.8 = reject)    │
└──────────────┬──────────────────────────────────────────────────┘
               │  Validated factors
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Backtest Engine                                               │
│  • Sharpe / Annualized Return / Max Drawdown / Win Rate / rankIC│
│  • Per-year and rolling window analysis                         │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Four Memory Libraries (PostgreSQL / TimescaleDB)              │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐ │
│  │ Factor Lib   │ Factor Exp   │ Strategy Lib │ Strategy Exp │ │
│  │ 50 factors   │ 21 records   │ 51 strategies│ 200 records  │ │
│  │ IC/ICIR/avep │ patterns     │ full reports  │ bull/bear/   │ │
│  │ maxCorr/expl │              │              │ volatile/calm│ │
│  └──────────────┴──────────────┴──────────────┴──────────────┘ │
└──────────────┬──────────────────────────────────────────────────┘
               │  Evolution loop (Ralph Loop paradigm)
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Strategy Evolution & Risk Alert                                │
│  • 2024: Rolling backtest → train success/failure memories     │
│  • 2025: Live monitoring → detect failure → retrieve similar   │
│    experiences → LLM generates new variant → backtest → switch │
│  • Risk alert: high historical failure rate → position reduce  │
└─────────────────────────────────────────────────────────────────┘
```

### How This Relates to the Paper / 与论文的对应关系

| Paper Concept (Section) | This Implementation |
|------------------------|---------------------|
| Ralph Loop (§3.4, Algorithm 1) | `FACTOR/step2_factor_mining/ralph_loop.py` — Retrieve → Generate → Evaluate → Distill |
| Experience Memory (§3.3) | `FACTOR/step3_factor_library_memory/memory.py` — Formation / Evolution / Retrieval operators |
| Modular Skill Architecture (§3.2) | `FACTOR/step2_factor_mining/` — operators.py (60+ operators), evaluation.py (multi-stage validation) |
| Multi-Stage Evaluation (§3.4) | `evaluation.py` — IC screening (Stage 1) → Correlation check (Stage 2) → Batch dedup (Stage 3) → Full validation (Stage 4) |
| Correlation Red Sea | `maxCorr ≥ 0.8` gate in `factor_diagnostics()` — 25/60 WorldQuant alphas filtered as redundant |
| Successful Patterns / Failure Regions | Factor experience library (21 records) + Strategy experience library (200 records) |
| Factor Library (§4) | PostgreSQL `factor_library` table — 50 factors (16 mined + 34 WorldQuant alphas) |

---

## ✨ Key Features / 核心功能

### 1. Ralph Loop Factor Mining / Ralph Loop 因子挖掘

Implements the paper's Algorithm 1: iterative Retrieve → Generate → Evaluate → Distill cycle with memory-guided exploration.

实现论文的 Algorithm 1：迭代式的 检索 → 生成 → 评估 → 蒸馏 循环，记忆引导探索方向。

### 2. Conversational Strategy Generation / 对话式策略生成

Natural language → intent recognition (strategy / factor / query) → automatic generation → backtest → library persistence. DeepSeek LLM with keyword-rule fallback for reliability.

自然语言 → 意图识别（策略/因子/查询）→ 自动生成 → 回测 → 入库。DeepSeek LLM + 关键词规则双层兜底。

### 3. Custom Quantitative Expression Engine / 自研量化表达式引擎

48 operators (time-series, cross-sectional, element-wise): `TsRank`, `CsRank`, `TsCorr`, `TsCov`, `Resi`, `Delta`, `WMA`, `Std`, `Max`, `Min`, etc. AST-based whitelist evaluation — LLM-generated formulas are parsed and executed in a sandbox, never arbitrary Python code.

Based on the paper's operator library (§3.1, "60+ financial operators"), implemented as a lightweight Python AST evaluator with vectorized sliding window operations.

48 个算子（时间序列/截面/逐元素）：`TsRank`、`CsRank`、`TsCorr`、`TsCov`、`Resi`、`Delta`、`WMA`、`Std`、`Max`、`Min` 等。基于 AST 的白名单求值——LLM 生成的公式经解析后在沙箱内执行，不执行任意 Python 代码。

基于论文的算子库（§3.1，"60+ financial operators"），以轻量级 Python AST 求值器实现，向量化滑窗操作。

### 4. Four-Dimensional Factor Diagnostics / 四维因子诊断

Inspired by the paper's multi-stage evaluation pipeline (§3.4):

| Metric | Meaning | Paper Reference |
|--------|---------|----------------|
| **IC** | Mean cross-sectional Spearman correlation between signal and next-period return | Stage 1: Fast IC screening |
| **ICIR** | IC mean / IC std — measures signal stability | Quality threshold Φ(α) |
| **ave\|p\|** | Mean absolute p-value from per-step t-tests — statistical significance | Extended metric |
| **maxCorr** | Maximum correlation with any existing factor — redundancy filter (≥0.8 → reject) | Stage 2: Correlation check against L |

受论文多阶段评估管线启发（§3.4）：

| 指标 | 含义 | 论文对应 |
|------|------|----------|
| **IC** | 信号与下期收益的截面 Spearman 相关均值 | Stage 1: Fast IC screening |
| **ICIR** | IC 均值 / IC 标准差——衡量信号稳定性 | 质量阈值 Φ(α) |
| **ave\|p\|** | 逐步 t 检验 p 值的时序均值——统计显著性 | 扩展指标 |
| **maxCorr** | 与库内所有因子的最大 Pearson 相关性——冗余过滤（≥0.8 → 拒绝） | Stage 2: Correlation check against L |

### 5. WorldQuant 101 Alpha Integration / WorldQuant 101 Alpha 因子库导入

60 classic alpha formulas from Kakushadze (2016) [2], translated to the expression engine DSL. Automated diagnostic validation filtered **25 redundant alphas** (correlation ≥0.8 with existing factors), keeping 34 high-quality, diverse alphas — demonstrating the "Correlation Red Sea" phenomenon described in the paper.

导入 Kakushadze (2016) [2] 的 60 个经典 alpha 公式，翻译为表达式引擎语法。自动诊断过滤 **25 个冗余 alpha**（与已有因子相关性 ≥0.8），保留 34 个高质量、多样化的 alpha——印证了论文中描述的"相关性红海"现象。

### 6. Memory-Driven Strategy Evolution / 记忆驱动的策略自进化

Extends the paper's experience memory (§3.3) to strategy-level evolution:

- **2024 Training Phase**: Rolling-window backtests tag each period as success/failure with market context labels (bull/bear/volatile/calm).
- **2025 Live Monitoring**: Current strategy's rolling Sharpe drops below threshold → failure detected → retrieve similar historical experiences → LLM generates new strategy variant → short-term backtest → switch to best performer.
- **Risk Alert**: When current market context has high historical failure rate, automatically trigger position reduction.

扩展论文的经验记忆（§3.3）至策略级进化：

- **2024 训练阶段**：滚动窗口回测，为每个时期标注成功/失败及市场情境标签（bull/bear/volatile/calm）。
- **2025 实时监控**：当前策略滚动 Sharpe 跌破阈值 → 判定失灵 → 检索相似历史经验 → LLM 生成新策略变体 → 短期回测 → 切换最优。
- **风险预警**：当前市场情境历史失败率偏高时，自动触发减仓。

### 7. Real Market Data Pipeline / 真实行情数据管线

- **9.15M rows** of 30-minute bars for CSI 300/500/1000 constituent stocks (1,800 tickers × 3 years: 2024–2026)
- Concurrent data collection with 3-shard × 2-worker architecture (63 tasks/min)
- Handles data deduplication (240× duplication in 2026 data), timezone offsets, yearly API chunking, and checkpoint resumption
- Stored in **TimescaleDB** (PostgreSQL extension for time-series)

- **915 万行** 30 分钟 K 线数据（CSI300/500/1000 成分股 1,800 只 × 3 年：2024–2026）
- 3 分片 × 2 worker 并发采集架构（63 任务/分钟）
- 处理数据重复（2026 年数据存在 240 倍重复）、时区偏移、分年 API 限块、断点续传
- 存储于 **TimescaleDB**（PostgreSQL 时序扩展）

### 8. Web Interface / Web 交互界面

FastAPI-based single-page application with LLM chat interface. Artifin.ai-inspired light SaaS aesthetic. Supports factor library browsing (with IC/ICIR/ave|p|/maxCorr diagnostics and LLM explanations), strategy library, conversation-based generation, and mobile-responsive design.

基于 FastAPI 的单页应用，LLM 对话交互界面，仿 Artifin.ai 轻量 SaaS 风格。支持因子库浏览（含 IC/ICIR/ave|p|/maxCorr 诊断和 LLM 解释）、策略库、对话生成、移动端响应式适配。

---

## 📁 Project Structure / 项目结构

```
FactorMiner/
├── FACTOR/                              # Factor mining engine (Paper §3)
│   ├── step1_data_ingestion/            # Data sources & specs
│   │   ├── data_sources.py              # SyntheticSource, SqlSource
│   │   └── spec.py                      # Data contracts
│   ├── step2_factor_mining/             # Core mining (Paper §3.1-3.4)
│   │   ├── operators.py                 # 48 quantitative operators (Paper §3.1)
│   │   ├── expression_engine.py         # AST parser & evaluator
│   │   ├── evaluation.py                # IC, ICIR, ave|p|, factor_diagnostics (Paper §3.4)
│   │   ├── llm_proposer.py              # LLM formula generation
│   │   └── ralph_loop.py               # Ralph Loop mining cycle (Paper Algorithm 1)
│   └── step3_factor_library_memory/     # Experience memory (Paper §3.3)
│       └── memory.py                    # Formation / Evolution / Retrieval operators
│
├── strategy_backtest/                   # Strategy engine (Extended beyond paper)
│   ├── step1_data_adapter/              # Strategy data prep
│   ├── step2_template_context/          # Templates & context
│   ├── step3_backtest_engine/           # Backtest core
│   └── step4_strategy_evolution/        # Self-evolution (Paper concept extended)
│       ├── agent.py                     # Train 2024 / Evolve 2025 pipeline
│       └── memory.py                    # Strategy memory & experiences
│
├── factorminer/                         # Application layer
│   ├── web/
│   │   ├── app.py                       # FastAPI routes + HTML templates
│   │   └── _store.py                    # PostgreSQL CRUD for 4 memory libs
│   └── mcp/
│       └── server.py                    # MCP protocol server
│
├── entry/                               # Run entry points
├── scripts/                             # Data collection & seeding
│   ├── collect_cmes.py                  # CEMS 30min data collector
│   ├── seed_alphas.py                   # WorldQuant 101 Alpha import
│   └── seed_libraries.py               # Seed factor/strategy libraries
│
├── DESIGN.md                            # UI design system
├── requirements.txt                     # Python dependencies
└── README.md
```

---

## 🚀 Quick Start / 快速开始

### Prerequisites / 前置条件

- **Python 3.10+**
- **Docker** (for PostgreSQL / TimescaleDB)
- **DeepSeek API key** (or compatible OpenAI-format API)

### 1. Start Database / 启动数据库

```bash
docker run -d --name qlib_local_sql \
  -e POSTGRES_USER=quant \
  -e POSTGRES_PASSWORD=quant \
  -e POSTGRES_DB=quant \
  -p 5432:5432 \
  -v F:/pgdata:/var/lib/postgresql/data \
  timescaledb:latest-pg16
```

### 2. Install Dependencies / 安装依赖

```bash
pip install -r requirements.txt
```

### 3. Setup Database Schema / 建表

```bash
# Factor & strategy tables
python scripts/sql_setup.py

# Four memory libraries
psql -h localhost -U quant -d quant -f scripts/sql_memory_lib.sql
```

### 4. Collect Data / 采集数据

```bash
# 30-minute bars for CSI 300/500/1000 (1,800 tickers × 3 years)
python scripts/collect_cmes.py --start 2024-01-01 --end 2026-12-31
```

### 5. Seed Libraries / 导入种子数据

```bash
# Mine 16 initial factors + seed 51 strategies + 200 experiences
python scripts/seed_libraries.py

# Import WorldQuant 101 Alphas (34 passed, 25 redundant filtered)
python scripts/seed_alphas.py
```

### 6. Launch Web UI / 启动 Web 界面

```bash
$env:DEEPSEEK_API_KEY = "sk-your-key-here"
python -m uvicorn factorminer.web.app:app --host 127.0.0.1 --port 8090
```

Open **http://127.0.0.1:8090** in your browser.

---

## 📊 Data & Results Overview / 数据与结果概览

### Data Pipeline / 数据管线

| Item | Value |
|------|-------|
| Market | CSI 300 / 500 / 1000 constituent stocks |
| Tickers | 1,800 |
| Frequency | 30-minute bars |
| Period | 2024-01-01 ~ 2026-12-31 |
| Rows | 9,153,196 |
| Storage | TimescaleDB (PostgreSQL) |
| Collection Speed | 63 tasks/min (3 shards × 2 workers) |

### Factor Library / 因子库

| Metric | Value |
|--------|-------|
| Total factors | 50 |
| — Mined (Ralph Loop) | 16 |
| — WorldQuant 101 Alphas | 34 |
| Alphas filtered (redundancy) | 25 / 60 |
| All factors have LLM explanations | ✅ |
| Expression engine operators | 48 |
| Per-factor evaluation time | 0.4s (vectorized) |

### Strategy Library / 策略库

| Metric | Value |
|--------|-------|
| Total strategies | 51 |
| Strategy experiences | 200 (success + failure) |
| Market context labels | bull / bear / volatile / calm |
| Strategy templates | 8 (momentum, mean-reversion, volatility, etc.) |

---

## 🧪 Technical Highlights / 技术亮点

### Expression Engine Safety / 表达式引擎安全性

LLM-generated formulas are **never** executed as raw Python. Instead:

1. Parse into AST nodes
2. Validate each node against the 48-operator whitelist
3. Evaluate in a sandboxed environment

This prevents code injection while allowing rich quantitative expression.

LLM 生成的公式**绝不会**作为原始 Python 代码执行。流程：
1. 解析为 AST 节点
2. 对每个节点验证是否在 48 个算子白名单内
3. 在沙箱环境中求值

### Performance Optimization / 性能优化

| Version | Per-factor time | Method |
|---------|----------------|--------|
| V1 (pandas iterrows) | 40s | Row-by-row datetime conversion |
| V2 (vectorized) | 0.4s | `pd.to_datetime().dt.to_pydatetime()` + numpy sliding window |
| **Speedup** | **100×** | |

### Redundancy Prevention (Correlation Red Sea) / 冗余因子预防（相关性红海）

Before any factor enters the library, `maxCorr` (maximum Pearson correlation with all existing factors) is computed. Factors with `maxCorr ≥ 0.8` are automatically rejected, preventing factor homogeneity. This directly implements the paper's "Correlation Red Sea" mitigation strategy.

每个因子入库前计算 `maxCorr`（与库内所有已有因子的最大 Pearson 相关性）。`maxCorr ≥ 0.8` 的因子自动拒绝，防止因子同质化。这直接实现了论文中的"相关性红海"缓解策略。

---

## 🛠 Tech Stack / 技术栈

| Layer | Technology |
|-------|-----------|
| LLM | DeepSeek (OpenAI-compatible API) |
| Language | Python 3.10+ |
| Web Framework | FastAPI |
| Database | PostgreSQL + TimescaleDB |
| Data Processing | NumPy, Pandas |
| Expression Engine | Custom AST parser (48 operators) |
| Data Collection | Concurrent workers, checkpoint resume |
| Testing | Playwright (browser automation) |
| Deployment | Docker, uvicorn |

---

## 📚 References / 参考文献

[1] Y. Wang, J. Xu, H. Zhang, S.-L. Huang, D. D. Sun, and X.-P. Zhang, "FactorMiner: A Self-Evolving Agent with Skills and Experience Memory for Financial Alpha Discovery," *arXiv preprint arXiv:2602.14670*, 2026. (ICLR 2026 Workshop on Memory for LLM-Based Agentic Systems)

[2] Z. Kakushadze, "101 Formulaic Alphas," *Wilmott Magazine*, 2016(84), pp. 72–80, 2016.

[3] M. López de Prado, *Advances in Financial Machine Learning*, Wiley, 2018.

[4] T. Starke et al., "Alternative Data in Quantitative Finance," in *Machine Learning for Asset Management*, 2019.

[5] D. Wang et al., "EvoAgent: Towards Automated LLM Agent Evolution," *arXiv preprint arXiv:2501.14637*, 2025.

---

## 📝 License

This project is for academic and research purposes.

---

## 🙏 Acknowledgments

- **FactorMiner** (Wang et al., 2026) — Ralph Loop architecture for LLM-driven factor mining
- **WorldQuant 101 Formulaic Alphas** (Kakushadze, 2016) — Classic alpha factor library
- **TimescaleDB** — Time-series extension for PostgreSQL
- **EvoAgent** (Wang et al., 2025) — Agent evolution paradigm
