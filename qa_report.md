# QA Report — FactorMiner 中文汇报 PPT

## 交付概况

- **PPTX**: `output/final_presentation_cn.pptx`（15 页，16:9，2026-08-19 重建）
- **演讲备注**: 15/15 页均有中文 speaker notes
- **嵌入媒体**: 1（fig1 架构图）
- **配套文档**: `output/factorMiner_精读报告.md`（12 节范式精读报告，含全部核验数字）、`output/asset_manifest.md`、`output/build_deck.py`（可复现构建脚本）、`output/factorMiner_paper.pdf` + `output/factorMiner_text.txt`（原文与全文文本，核验依据）

## 自审与修正记录

| 轮次 | 审计结果 | 处置 |
|---|---|---|
| 第 1 版 | high=1（S4 架构图越界）, low=17 | 修复 S4 图片按比例缩放至 4.7in 高并水平居中；补齐 15 页 speaker notes |
| 第 2 版 | high=0, medium=0, low=16, notes=15/15 | low 项全部为容器内文字偏移（3.6pt 内边距），属设计内行为，记录如下 |
| 第 3 版（全文核验后） | high=0, medium=0, low=16, notes=15/15 | 逐页对照 arXiv:2602.14670 PDF 原文修正全部数字（见下"数字核验修正"） |

## 数字核验修正（第 3 版，依据 PDF 原文）

1. **S10 表 1**：HS300 与 Crypto 两列基线数字此前错位，已按 Table 1 逐格修正——RF（1.94/0.15、1.45/0.09）、Alpha101 Classic（3.44/0.26、2.11/0.14）、Alpha101 Adapted（4.00/0.28、2.40/0.15），GPLearn/AlphaForge/AlphaAgent/FactorMiner 行原值核对无误。
2. **S12 记忆消融**：按 Figure 3 补全数据——高质量候选数 32→96、被拒候选数 14→53、产出率 20.0%→60.0%、准入 18→43、被拒率 43.8%→55.2%；注明消融放宽阈值（|IC|>0.02、θ=0.85）；标题"Φ/Ψ/Ξ"改为论文原文算子 F/E/R。
3. **S13 效率**：增补算子级实例（TsRank 1,843→393→31ms；CsRank 445→49→26ms）、GPU 平均较 C 快 5.4×、Table 3 单 A100 加速（CsRank 26×/TsRank 17×/TsDecay 9×/Rolling Corr 6.8×）。
4. **S14 局限**：改为论文原文口径（Section 7：未与端到端预测模型受控对比；误用风险与合规；Section 6：成本回测/更广资产/在线记忆列为未来工作）。
5. **S11 冗余度**：补全库 110 因子 Avg|ρ|=0.203（Fig. 2 图注），与 Top-40 选中集 0.30–0.31 区分。
6. **S6/S8 管线表述**：按 Algorithm 1 改为"多阶段（Stage 1/2/2.5/3/4）"。

## 低严重度说明（已知可接受）

- 16 条 `alignment_near_miss`（3.6–7.2pt）全部来自"色块容器与其内部文字"或"标题副行与标题块"的结构性偏移，为有意内边距，非未对齐缺陷；关键引导（标题左缘、图片左右缘、takeaway 条带、页脚）均对齐。
- 表 1（S10）为 PPT 原生表格，高亮 FactorMiner 行（浅蓝底 + 加粗）。

## 完成的质量检查

- 版式越界: 已检查并修复（S4 图片）。
- 文本溢出风险: 各文本块宽度留有保守边距；无自动收缩依赖。
- 反模板检查: 页面构图轮换（claim-led / process-wide / figure-dominant / comparison / discussion），无整页三卡片重复。
- 术语一致性: 采用 Terminology Ledger（FactorMiner、Ralph Loop、经验记忆、技能架构、IC/ICIR、相关性红海等固定译法）。
- 数字核对: **全部数字已逐一对照 arXiv:2602.14670v1 PDF 原文（20 页全文 + 附录 A–P）核验**；正文 4.2.3 与 Table 1 的一处 ICIR 内部出入（1.52/1.54 vs 1.29/1.31）已在精读报告 7.4 注明，slide 以 Table 1 为准。

## 已知局限

- 未做渲染级视觉 QA（无可靠 headless 渲染器）；建议用 PowerPoint/WPS 打开后通读一遍 15 页确认观感。
- 汇报封面无机构 logo，可自行补充。
- 论文未提供官方代码仓库链接；开源内容为 110 个 A 股因子公式（附录 P），PPT 中表述已与之一致。