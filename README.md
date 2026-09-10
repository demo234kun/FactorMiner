# FactorMiner — Quantitative Strategy Self-Evolution Platform

> **LLM-Driven Factor Mining → Statistical Gatekeeping → Backtest Validation → Memory Evolution**
>
> 复刻论文 *FactorMiner* 的 Ralph Loop 思想，构建从因子生成、诊断、回测到策略自进化的完整量化研究闭环。

---

## 🎯 Overview / 概述

**English:**
Quantitative research suffers from two bottlenecks: (1) human-driven alpha factor discovery is slow and experience-dependent; (2) once a strategy fails, there is no systematic way to diagnose why or learn from it. FactorMiner automates the full loop — an LLM generates candidate factor expressions, a custom expression engine evaluates them against real market data, a four-dimensional diagnostic gate filters for quality and diversity, validated factors feed into backtested strategies, and success/failure experiences are persisted into four memory libraries for future evolution.

**中文：**
量化研究存在两大瓶颈：(1) 人工驱动的 alpha 因子发现依赖经验、效率低下；(2) 策略失效后缺乏系统性归因与经验沉淀机制。FactorMiner 自动化了完整闭环——LLM 生成候选因子表达式，自定义表达式引擎在真实行情上求值，四维诊断门禁过滤质量与冗余，验证通过的因子进入策略回测，成功/失败经验持久化至四个记忆库，驱动策略自进化。

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
               │  Evolution loop
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Strategy Evolution & Risk Alert                                │
│  • 2024: Rolling backtest → train success/failure memories     │
│  • 2025: Live monitoring → detect failure → retrieve similar   │
│    experiences → LLM generates new variant → backtest → switch │
│  • Risk alert: high historical failure rate → position reduce  │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features / 核心功能

### 1. Conversational Strategy Generation / 对话式策略生成

Natural language → intent recognition (strategy / factor / query) → automatic generation → backtest → library persistence. DeepSeek LLM with keyword-rule fallback for reliability.

自然语言 → 意图识别（策略/因子/查询）→ 自动生成 → 回测 → 入库。DeepSeek LLM + 关键词规则双层兜底。

### 2. Custom Quantitative Expression Engine / 自研量化表达式引擎

48 operators (time-series, cross-sectional, element-wise): `TsRank`, `CsRank`, `TsCorr`, `TsCov`, `Resi`, `Delta`, `WMA`, `Std`, `Max`, `Min`, etc. AST-based whitelist evaluation — LLM-generated formulas are parsed and executed in a sandbox, never arbitrary Python code. Vectorized sliding window achieves **100× speedup** (40s → 0.4s per factor).

48 个算子（时间序列/截面/逐元素）：`TsRank`、`CsRank`、`TsCorr`、`TsCov`、`Resi`、`Delta`、`WMA`、`Std`、`Max`、`Min` 等。基于 AST 的白名单求值——LLM 生成的公式经解析后在沙箱内执行，不执行任意 Python 代码。向量化滑窗实现 **100 倍加速**（单因子求值 40s → 0.4s）。

### 3. Four-Dimensional Factor Diagnostics / 四维因子诊断

Every candidate is validated before library entry:

| Metric | Meaning |
|--------|---------|
| **IC** | Mean cross-sectional Spearman correlation between signal and next-period return |
| **ICIR** | IC mean / IC std — measures signal stability |
| **ave\|p\|** | Mean absolute p-value from per-step t-tests — statistical significance |
| **maxCorr** | Maximum correlation with any existing factor in library — redundancy filter (≥0.8 → reject) |

每个候选因子入库前独立通过四维审查：IC（预测力）、ICIR（稳定性）、ave|p|（统计显著性）、maxCorr（与库内因子冗余度，≥0.8 自动拒绝）。

### 4. WorldQuant 101 Alpha Integration / WorldQuant 101 Alpha 因子库导入

60 classic alpha formulas from the WorldQuant 101 Alphas paper, translated to the expression engine DSL. Automated diagnostic validation filtered **25 redundant alphas** (correlation ≥0.8 with existing factors), keeping 34 high-quality, diverse alphas.

导入 WorldQuant 101 Alphas 论文的 60 个经典 alpha 公式，翻译为表达式引擎语法。自动诊断过滤 **25 个冗余 alpha**（与已有因子相关性 ≥0.8），保留 34 个高质量、多样化的 alpha。

### 5. Memory-Driven Strategy Evolution / 记忆驱动的策略自进化

- **2024 Training Phase**: Rolling-window backtests tag each period as success/failure with market context labels (bull/bear/volatile/calm).
- **2025 Live Monitoring**: Current strategy's rolling Sharpe drops below threshold → failure detected → retrieve similar historical experiences → LLM generates new strategy variant → short-term backtest → switch to best performer.
- **Risk Alert**: When current market context has high historical failure rate, automatically trigger position reduction.

- **2024 训练阶段**：滚动窗口回测，为每个时期标注成功/失败及市场情境标签（bull/bear/volatile/calm）。
- **2025 实时监控**：当前策略滚动 Sharpe 跌破阈值 → 判定失灵 → 检索相似历史经验 → LLM 生成新策略变体 → 短期回测 → 切换最优。
- **风险预警**：当前市场情境历史失败率偏高时，自动触发减仓。

### 6. Real Market Data Pipeline / 真实行情数据管线

- **9.15M rows** of 30-minute bars for CSI 300/500/1000 constituent stocks (1,800 tickers × 3 years: 2024–2026)
- Concurrent data collection with 3-shard × 2-worker architecture (63 tasks/min)
- Handles data deduplication (240× duplication in 2026 data), timezone offsets, yearly API chunking, and checkpoint resumption
- Stored in **TimescaleDB** (PostgreSQL extension for time-series)

- **915 万行** 30 分钟 K 线数据（CSI300/500/1000 成分股 1,800 只 × 3 年：2024–2026）
- 3 分片 × 2 worker 并发采集架构（63 任务/分钟）
- 处理数据重复（2026 年数据存在 240 倍重复）、时区偏移、分年 API 限块、断点续传
- 存储于 **TimescaleDB**（PostgreSQL 时序扩展）

### 7. Web Interface / Web 交互界面

FastAPI-based single-page application with LLM chat interface. Artifin.ai-inspired light SaaS aesthetic. Supports factor library browsing (with IC/ICIR/ave|p|/maxCorr diagnostics and LLM explanations), strategy library, conversation-based generation, and mobile-responsive design.

基于 FastAPI 的单页应用，LLM 对话交互界面，仿 Artifin.ai 轻量 SaaS 风格。支持因子库浏览（含 IC/ICIR/ave|p|/maxCorr 诊断和 LLM 解释）、策略库、对话生成、移动端响应式适配。

---

## 📁 Project Structure / 项目结构

```
FactorMiner/
├── FACTOR/                              # Factor mining engine / 因子挖掘引擎
│   ├── step1_data_ingestion/            # Data sources & specs / 数据接入
│   │   ├── data_sources.py              # SyntheticSource, SqlSource
│   │   └── spec.py                      # Data contracts / 数据契约
│   ├── step2_factor_mining/             # Core mining / 核心挖掘
│   │   ├── operators.py                 # 48 quantitative operators / 48 个量化算子
│   │   ├── expression_engine.py         # AST parser & evaluator / 表达式求值引擎
│   │   ├── evaluation.py                # IC, ICIR, ave|p|, factor_diagnostics
│   │   ├── llm_proposer.py              # DeepSeek formula generation
│   │   └── ralph_loop.py               # Ralph Loop mining cycle / Ralph Loop 挖掘循环
│   └── step3_factor_library_memory/     # Factor memory / 因子记忆
│       └── memory.py                    # Formation / Evolution / Retrieval
│
├── strategy_backtest/                   # Strategy engine / 策略引擎
│   ├── step1_data_adapter/              # Strategy data prep / 策略数据适配
│   │   └── strategy_data.py
│   ├── step2_template_context/          # Templates & context / 模板与情境
│   │   ├── templates.py                 # 8 strategy templates / 8 个策略模板
│   │   ├── strategy_generator.py        # LLM text → strategy template
│   │   └── context.py                   # Market context extraction
│   ├── step3_backtest_engine/           # Backtest core / 回测引擎
│   │   ├── engine.py                    # Core backtest logic
│   │   └── backtest_report.py           # Full report generation
│   └── step4_strategy_evolution/        # Self-evolution / 策略进化
│       ├── agent.py                     # Train 2024 / Evolve 2025 pipeline
│       └── memory.py                    # Strategy memory & experiences
│
├── factorminer/                         # Application layer / 应用层
│   ├── web/
│   │   ├── app.py                       # FastAPI routes + HTML templates
│   │   └── _store.py                    # PostgreSQL CRUD for 4 memory libs
│   └── mcp/
│       └── server.py                    # MCP protocol server
│
├── entry/                               # Run entry points / 运行入口
│   ├── run_demo.py                      # Demo with synthetic data
│   ├── run_real.py                      # Real data mining + strategy
│   └── run_strategy.py                  # Strategy pipeline standalone
│
├── scripts/                             # Data collection & seeding / 数据采集与种子
│   ├── collect_cmes.py                  # CEMS 30min data collector
│   ├── seed_alphas.py                   # WorldQuant 101 Alpha import
│   ├── seed_libraries.py                # Seed factor/strategy libraries
│   └── sql_*.sql                        # Database schema scripts
│
├── assets/figures/                      # Paper figures / 论文配图
├── DESIGN.md                            # UI design system / UI 设计系统
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

# Four memory libraries (factor_library, factor_experience, strategy_library, strategy_experience)
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

## 📊 Data Overview / 数据概览

| Item | Value |
|------|-------|
| Market | CSI 300 / 500 / 1000 constituent stocks |
| Tickers | 1,800 |
| Frequency | 30-minute bars |
| Period | 2024-01-01 ~ 2026-12-31 |
| Rows | 9,153,196 |
| Storage | TimescaleDB (PostgreSQL) |
| Collection Speed | 63 tasks/min (3 shards × 2 workers) |

| Item | Value |
|------|-------|
| 标的 | CSI300/500/1000 成分股 |
| 数量 | 1,800 只 |
| 频率 | 30 分钟 K 线 |
| 区间 | 2024-01-01 ~ 2026-12-31 |
| 数据量 | 915 万行 |
| 存储 | TimescaleDB (PostgreSQL 时序扩展) |
| 采集速率 | 63 任务/分钟（3 分片 × 2 worker） |

---

## 📈 Factor Library Stats / 因子库统计

| Metric | Value |
|--------|-------|
| Total factors | 50 |
| — Mined (Ralph Loop) | 16 |
| — WorldQuant 101 Alphas | 34 |
| Alphas filtered (redundancy) | 25 / 60 |
| All factors have LLM explanations | ✅ |
| Expression engine operators | 48 |
| Per-factor evaluation time | 0.4s (vectorized) |

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

在防止代码注入的同时支持丰富的量化表达。

### Performance Optimization / 性能优化

| Version | Per-factor time | Method |
|---------|----------------|--------|
| V1 (pandas iterrows) | 40s | Row-by-row datetime conversion |
| V2 (vectorized) | 0.4s | `pd.to_datetime().dt.to_pydatetime()` + numpy sliding window |
| **Speedup** | **100×** | |

### Redundancy Prevention / 冗余因子预防

Before any factor enters the library, `maxCorr` (maximum Pearson correlation with all existing factors) is computed. Factors with `maxCorr ≥ 0.8` are automatically rejected, preventing factor homogeneity ("correlation red ocean").

每个因子入库前计算 `maxCorr`（与库内所有已有因子的最大 Pearson 相关性）。`maxCorr ≥ 0.8` 的因子自动拒绝，防止因子同质化（相关性红海）。

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

## 📝 License

This project is for academic and research purposes.

---

## 🙏 Acknowledgments

- **FactorMiner** paper — Ralph Loop architecture for LLM-driven factor mining
- **WorldQuant 101 Formulaic Alphas** — Classic alpha factor library
- **TimescaleDB** — Time-series extension for PostgreSQL
