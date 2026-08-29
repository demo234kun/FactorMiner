# -*- coding: utf-8 -*-
"""
FactorMiner 中文汇报 PPT 构建脚本
论文: FactorMiner: A Self-Evolving Agent with Skills and Experience Memory
      for Financial Alpha Discovery (arXiv:2602.14670, ICLR 2026)
设计: Nature 风格学术汇报, 16:9, 中文为主
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
import copy

# ---------------------------------------------------------------- constants
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN_L = Inches(0.6)
MARGIN_R = Inches(0.6)
MARGIN_T = Inches(0.45)
TITLE_H = Inches(0.75)
CONTENT_T = MARGIN_T + TITLE_H + Inches(0.1)

# palette (Nature 风格, 克制)
INK = RGBColor(0x14, 0x21, 0x3D)          # 主文字 深藏青
BODY = RGBColor(0x2B, 0x36, 0x4A)         # 正文
MUTED = RGBColor(0x6B, 0x77, 0x88)        # 次级/来源
ACCENT = RGBColor(0x2A, 0x6F, 0x97)       # 主强调 蓝
ACCENT2 = RGBColor(0x8A, 0x5A, 0x2B)      # 次强调 赭
GREEN = RGBColor(0x1E, 0x7A, 0x46)        # 正向
RED = RGBColor(0xB3, 0x3A, 0x3A)          # 负向/警示
LIGHT_BG = RGBColor(0xF4, 0xF6, 0xF8)     # 浅底
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GRAY_LINE = RGBColor(0xD8, 0xDE, 0xE6)

FONT_CN = "Microsoft YaHei"
FONT_EN = "Segoe UI"

ASSET_DIR = r"E:\博士论文\research\study three\Factor-miner\assets\figures"
OUT_PATH = r"E:\博士论文\research\study three\Factor-miner\final_presentation_cn.pptx"


def set_font(run, size, bold=False, color=INK, font=FONT_CN):
    f = run.font
    f.size = Pt(size)
    f.bold = bold
    f.name = font
    f.color.rgb = color
    # 东亚字体
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = rPr.makeelement(qn("a:ea"), {})
        rPr.append(ea)
    ea.set("typeface", FONT_CN)


def add_text(slide, x, y, w, h, lines, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
             wrap=True):
    """lines: list of (text, size, bold, color) or list of list-of-runs"""
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    first = True
    for line in lines:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.alignment = align
        if isinstance(line, tuple):
            line = [line]
        for (text, size, bold, color) in line:
            r = p.add_run()
            r.text = text
            set_font(r, size, bold, color)
    return box


def add_title(slide, text, sub=None):
    """统一标题块: 左缘对齐 MARGIN_L, 26pt 粗体"""
    add_text(slide, MARGIN_L, MARGIN_T, SLIDE_W - MARGIN_L - MARGIN_R, TITLE_H,
             [(text, 26, True, INK)])
    if sub:
        add_text(slide, MARGIN_L, MARGIN_T + Inches(0.62), SLIDE_W - MARGIN_L - MARGIN_R,
                 Inches(0.3), [(sub, 12, False, MUTED)])


def add_rule(slide, y, x0=MARGIN_L, x1=SLIDE_W - MARGIN_R, color=GRAY_LINE):
    ln = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x0, y, x1 - x0, Pt(1.2))
    ln.fill.solid()
    ln.fill.fore_color.rgb = color
    ln.line.fill.background()
    ln.shadow.inherit = False
    return ln


def add_caption_source(slide, caption, source, y):
    """底部说明条: 图注 + 来源, 小字灰色"""
    add_text(slide, MARGIN_L, y, SLIDE_W - MARGIN_L - MARGIN_R, Inches(0.5),
             [(caption, 10.5, False, BODY), (source, 9, False, MUTED)])


def add_takeaway(slide, text, y=None, color=ACCENT):
    """底部 takeaway 条带"""
    if y is None:
        y = SLIDE_H - Inches(0.62)
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, MARGIN_L, y,
                                 SLIDE_W - MARGIN_L - MARGIN_R, Inches(0.44))
    bar.fill.solid()
    bar.fill.fore_color.rgb = LIGHT_BG
    bar.line.fill.background()
    bar.shadow.inherit = False
    add_text(slide, MARGIN_L + Inches(0.25), y + Inches(0.05),
             SLIDE_W - MARGIN_L - MARGIN_R - Inches(0.5), Inches(0.34),
             [(text, 13, True, color)])
    return bar


def add_image(slide, path, x, y, w=None, h=None):
    """按给定宽/高插入图片, 保持比例"""
    kw = {}
    if w is not None:
        kw["width"] = w
    if h is not None:
        kw["height"] = h
    return slide.shapes.add_picture(path, x, y, **kw)


def add_bullets(slide, x, y, w, h, items, size=13.5, gap=8):
    """items: list of (lead, rest) 或纯文本; lead 为加粗前缀"""
    lines = []
    for it in items:
        if isinstance(it, tuple):
            lead, rest = it
            lines.append([("▪  ", size, True, ACCENT),
                          (lead, size, True, INK),
                          (rest, size, False, BODY)])
        else:
            lines.append([("▪  ", size, True, ACCENT),
                          (it, size, False, BODY)])
    box = add_text(slide, x, y, w, h, lines)
    # 段落间距
    for i, p in enumerate(box.text_frame.paragraphs):
        p.space_after = Pt(gap)
    return box


def add_metric_chip(slide, x, y, w, value, label, vcolor=ACCENT):
    """指标块: 大数字 + 小标签"""
    add_text(slide, x, y, w, Inches(0.55), [(value, 24, True, vcolor)])
    add_text(slide, x, y + Inches(0.5), w, Inches(0.3), [(label, 10.5, False, MUTED)])


def new_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def add_table(slide, x, y, w, h, data, n_cols, col_widths=None):
    """data: 2D 文本数组, 首行为表头; n_cols: 列数"""
    shape = slide.shapes.add_table(len(data), n_cols, x, y, w, h)
    tbl = shape.table
    for c in range(n_cols):
        if col_widths:
            tbl.columns[c].width = col_widths[c]
    for r in range(len(data)):
        tbl.rows[r].height = Inches(0.4)
        for c in range(n_cols):
            cell = tbl.cell(r, c)
            cell.margin_left = Inches(0.08)
            cell.margin_right = Inches(0.08)
            cell.margin_top = Inches(0.02)
            cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = str(data[r][c])
            if r == 0:
                set_font(run, 12, True, WHITE)
                cell.fill.solid()
                cell.fill.fore_color.rgb = INK
            else:
                set_font(run, 11.5, False, BODY)
                cell.fill.solid()
                cell.fill.fore_color.rgb = WHITE if r % 2 == 1 else LIGHT_BG
            if c == 0 and r > 0:
                run.font.bold = True
                run.font.color.rgb = INK
    return shape


def style_table_borders(shape):
    """给表格加细边框; shape 为 add_table 返回的 GraphicFrame"""
    from pptx.oxml.ns import qn as _qn
    tbl = shape.table._tbl
    tblPr = tbl.find(_qn("a:tblPr"))
    if tblPr is None:
        tblPr = tbl.makeelement(_qn("a:tblPr"), {})
        tbl.insert(0, tblPr)
    tblPr.set("firstRow", "1")
    tblPr.set("bandRow", "0")


# ---------------------------------------------------------------- helpers
def footer(slide, idx, total=15):
    add_text(slide, SLIDE_W - Inches(1.1), SLIDE_H - Inches(0.42), Inches(0.8),
             Inches(0.3), [(f"{idx:02d}", 10, False, MUTED)], align=PP_ALIGN.RIGHT)


def add_notes(slide, text):
    """写入演讲者备注"""
    slide.notes_slide.notes_text_frame.text = text


def build():
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    # ============ S1 标题页 ============
    s = new_slide(prs)
    add_rule(s, Inches(2.6), x0=Inches(1.2), x1=SLIDE_W - Inches(1.2), color=ACCENT)
    add_text(s, Inches(1.2), Inches(2.85), SLIDE_W - Inches(2.4), Inches(0.5),
             [("FACTORMINER", 40, True, INK)], align=PP_ALIGN.CENTER)
    add_text(s, Inches(1.2), Inches(3.45), SLIDE_W - Inches(2.4), Inches(0.45),
             [("A Self-Evolving Agent with Skills and Experience Memory for Financial Alpha Discovery",
               14, False, MUTED)], align=PP_ALIGN.CENTER)
    add_text(s, Inches(1.2), Inches(4.15), SLIDE_W - Inches(2.4), Inches(0.4),
             [("自进化智能体：技能 + 经验记忆驱动的公式化 Alpha 因子挖掘", 18, True, ACCENT)],
             align=PP_ALIGN.CENTER)
    add_text(s, Inches(1.2), Inches(5.05), SLIDE_W - Inches(2.4), Inches(1.2),
             [("Yanlong Wang, Jian Xu, Hongkang Zhang, Shao-Lun Huang, Danny Dongning Sun, Xiao-Ping Zhang", 12, False, BODY),
              ("清华大学 · 鹏城实验室   |   ICLR 2026（arXiv:2602.14670）", 12, False, BODY),
              ("文献汇报", 11, False, MUTED)],
             align=PP_ALIGN.CENTER)
    add_notes(s, "各位老师同学好，今天汇报的论文是 FactorMiner: A Self-Evolving Agent with Skills and Experience Memory for Financial Alpha Discovery（ICLR 2026，arXiv:2602.14670）。"
                  "作者来自清华大学与鹏城实验室。论文解决的核心问题是：当因子库越来越大、正交空间越来越窄时，如何让自动因子挖掘持续发现高质量且低冗余的公式化因子。"
                  "核心答案是一个自进化智能体：用技能架构保证评估的确定性，用经验记忆让搜索过程跨会话积累知识。今天我会按 问题→方案→实验→局限 的顺序讲 15 页，约 20 分钟。")
    footer(s, 1)

    # ============ S2 研究背景: 三大挑战 ============
    s = new_slide(prs)
    add_title(s, "因子挖掘的三重困境：搜索、记忆与可解释", "背景: 公式化 alpha 因子是量化投资的核心原料")
    add_bullets(s, MARGIN_L, CONTENT_T, Inches(7.2), Inches(4.2), [
        ("搜索空间爆炸: ", "算子组合与参数使公式空间呈组合式增长，人工穷举不可行"),
        ("知识无法积累: ", "遗传规划/强化学习在会话间遗忘经验，重复试错、收敛慢"),
        ("可解释性约束: ", "监管与风控要求透明可审计的显式公式，拒绝黑箱神经预测"),
    ], size=14)
    add_text(s, MARGIN_L, Inches(4.9), Inches(7.2), Inches(0.9),
             [("更深处的问题——\"相关性红海\"（Correlation Red Sea）：", 13.5, True, INK),
              ("因子库不断增长，与既有库正交的新因子可行域急剧收窄，新候选总在相关性门槛前被拒。",
               13, False, BODY)])
    # 右侧视觉: 简单示意图(正交空间收缩)
    box = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(8.6), Inches(1.7), Inches(3.4), Inches(3.4))
    box.fill.solid(); box.fill.fore_color.rgb = LIGHT_BG
    box.line.color.rgb = GRAY_LINE
    box.shadow.inherit = False
    box2 = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(9.3), Inches(2.4), Inches(2.0), Inches(2.0))
    box2.fill.solid(); box2.fill.fore_color.rgb = WHITE
    box2.line.color.rgb = ACCENT
    box2.shadow.inherit = False
    add_text(s, Inches(8.6), Inches(5.2), Inches(3.4), Inches(0.8),
             [("P_orth: 与库内因子 |ρ|<θ 的可行区", 10.5, False, MUTED)],
             align=PP_ALIGN.CENTER)
    add_takeaway(s, "库越大越难新增因子——单纯\"生成更多候选\"无法打破增长瓶颈。")
    add_notes(s, "先讲背景。公式化 alpha 因子——用显式表达式把行情字段变成预测信号——是量化交易的核心原料，但要自动挖掘它面临三重困境："
                  "第一，搜索空间按算子组合与参数呈组合式爆炸，人工枚举不可行；第二，传统搜索方法如遗传规划和强化学习在会话之间遗忘知识，反复踩同一块石头；"
                  "第三，监管和风控要求公式透明可审计，黑箱神经网络的预测能力再强也不能直接用。"
                  "更深一层的问题是论文定义的\"相关性红海\"：库内因子越多，与既有因子两两相关性低于阈值 θ 的正交可行域越小，新候选总是卡在相关性门槛上。"
                  "左边画的是 P_orth 随库增长收缩的示意：外圈是全部程序空间，内圈是正交可行区，库变大时内圈萎缩。所以论文的靶子不是\"生成更多候选\"，而是如何在红海里继续前进。")
    footer(s, 2)

    # ============ S3 现有方法缺陷 ============
    s = new_slide(prs)
    add_title(s, "已有自动化挖掘各自缺什么", "定位: 现有方法逐因子优化，缺少全局视角与跨会话知识")
    rows = [
        ["方法族", "代表", "主要缺陷"],
        ["人工因子库", "Alpha101 / Alpha191", "依赖专家、日频为主、无法扩展"],
        ["遗传规划 (GP)", "GPLearn 等", "语法级变异、收敛慢、语义指导弱"],
        ["强化学习", "RL 因子搜索", "训练与评估开销大、知识遗忘"],
        ["LLM 框架", "AlphaAgent 等", "无跨会话记忆、不感知库内冗余"],
    ]
    t = add_table(s, MARGIN_L, CONTENT_T, Inches(9.2), Inches(2.4), rows, 3,
                  [Inches(2.2), Inches(3.0), Inches(4.0)])
    style_table_borders(t)
    add_text(s, MARGIN_L, Inches(4.6), Inches(9.2), Inches(0.8),
             [("共同盲区: ", 13.5, True, INK),
              ("所有方法都把每个因子当作孤立个体，忽略新因子与既有库的交互，也不保存\"什么方向已撞墙\"的结构知识。",
               13, False, BODY)])
    add_takeaway(s, "FactorMiner 的目标：在全局正交约束下，让搜索过程自己学会搜索。")
    add_notes(s, "这是论文对现有方法的定位。人工因子库如 Alpha101/Alpha191 质量高但依赖专家、以日频为主，扩展性差；"
                  "遗传规划把公式当程序做交叉变异，但算子作用在语法上而不是语义上，收敛慢、缺少语义引导；"
                  "强化学习把 IC/ICIR 当奖励去导航离散公式空间，训练和反复评估开销大，而且跨会话遗忘；"
                  "LLM 框架（比如 AlphaAgent）能生成候选，但没有跨会话记忆，也不知道库内已经有什么、什么方向已经撞墙。"
                  "所有方法的共同盲区：把每个因子当孤立个体优化，既没有全局库视角，也不保存结构知识。FactorMiner 的对策就是在挖掘循环里显式引入这两样东西——全局视角和记忆。")
    footer(s, 3)

    # ============ S4 方法总览: 架构图 ============
    s = new_slide(prs)
    add_title(s, "系统总览：Ralph Loop 自进化因子挖掘", "三层协同: 经验记忆 + 技能架构 + 动态因子库")
    img_h = Inches(4.7)
    img_w = Emu(int(img_h * 2029 / 1134))
    img_x = (SLIDE_W - img_w) // 2
    img = add_image(s, ASSET_DIR + r"\fig1_framework.png",
                    img_x, Inches(1.32), w=img_w)
    add_caption_source(s, "Ralph Loop 框架：检索记忆先验 → 调用技能生成候选 → 多阶段验证 → 蒸馏回记忆，循环迭代。",
                       "Source: Fig. 1, FactorMiner (arXiv:2602.14670)", Inches(6.2))
    add_takeaway(s, "记忆让搜索\"越挖越聪明\"：每一轮挖掘的成败都沉淀为下一轮的先验。", y=Inches(6.82))
    add_notes(s, "这是整篇论文的骨架图。Ralph Loop 把自进化拆成四步：检索（从经验记忆取先验）→ 生成（LLM 按先验提候选公式）→ 评估（技能里的多阶段管线做确定性验证）→ 蒸馏（把结果写回记忆）。"
                  "图里三个核心组件：左下是经验记忆，存成功模式和禁区；右上是技能架构，封装 60+ 算子和多阶段验证管线；右下是动态增长的因子库，靠正交约束维持多样性。"
                  "记忆和库的状态共同决定下一轮采样方向——这就是\"自进化\"：每一轮挖掘都让下一轮更聪明。注意右侧还有反馈回路：库的准入日志和饱和指标会回到记忆，供检索使用。")
    footer(s, 4)

    # ============ S5 问题形式化 ============
    s = new_slide(prs)
    add_title(s, "形式化：正交库合成与记忆决策", "目标函数: 在相关性预算 θ 下最大化库的聚合质量")
    add_text(s, MARGIN_L, CONTENT_T, SLIDE_W - MARGIN_L - MARGIN_R, Inches(1.0),
             [("L* = argmax Σ Φ(α)   s.t.   ∀αi≠αj∈L: |ρ(αi,αj)| < θ", 17, True, INK),
              ("ρ 为信号时序平均的截面 Spearman 相关；Φ 为适应度（IC 等）。", 11.5, False, MUTED)])
    add_bullets(s, MARGIN_L, Inches(2.4), Inches(11.0), Inches(3.0), [
        ("相关性红海: ", "可行域 P_orth = {α : max|ρ(α,g)|<θ} 随库增长迅速萎缩，标准 GP/RL 因无记忆而困在其中"),
        ("记忆决策化: ", "把发现过程重构为对演化知识状态 S_t=(L_t, M_t) 的序贯决策，采样策略 π(α|m_t) 受记忆信号 m_t 约束"),
        ("蒸馏算子 Ψ: ", "M_{t+1} = Ψ(M_t, τ_t)，把历史轨迹 τ 蒸馏为结构化模式，把采样质量推向正交流形 P_orth"),
    ], size=13.5)
    add_takeaway(s, "记忆的本质作用：把程序空间上的均匀采样，收缩为指向正交区域的概率测度。")
    add_notes(s, "形式化部分。上面是库合成目标：在所有程序空间中选一个子集 L，最大化库内因子适应度之和，同时约束任意两两因子的信号相关性绝对值小于 θ。"
                  "ρ 用的是信号序列在时间上平均的截面 Spearman 相关，就是因子信号和下一个周期收益的秩相关在时间上的均值。"
                  "下面把记忆纳入决策论框架：系统状态是 (库 L_t, 记忆 M_t)，每轮先从记忆中检索信号 m_t，再按条件策略 π(α|m_t) 采样候选。"
                  "关键等式是蒸馏算子 Ψ：M_{t+1} = Ψ(M_t, τ_t)，把这一批挖掘轨迹 τ 蒸馏成结构化模式。"
                  "直觉上，记忆的作用是让采样分布从整个程序空间收缩到正交可行区 P_orth 附近——不是硬剪枝，而是概率质量的重新分配。")
    footer(s, 5)

    # ============ S6 技能架构 ============
    s = new_slide(prs)
    add_title(s, "模块化技能架构：把评估装进确定性工具", "Skill = 算子库 + 多阶段验证管线, 与 LLM 推理解耦")
    add_bullets(s, MARGIN_L, CONTENT_T, Inches(7.0), Inches(3.6), [
        ("算子层: ", "60+ 金融算子（TsRank、Rsquare…），GPU 加速后端，保证符号提案可执行"),
        ("验证管线: ", "check_ic → check_correlation → admit，多阶段流水线（快速 IC 筛选 → 相关性检查 → 替换检查 → 批量去重 → 全量 OOS 验证）"),
        ("三优势: ", "防计算幻觉（指标全部由代码计算）、跨市场可迁移（换配置即用）、可独立优化（不动 LLM 骨干）"),
    ], size=13)
    # 右侧 管线示意
    stages = ["Stage 1\n快速 IC 筛选", "Stage 2\n相关性检查", "Stage 2.5\n替换检查", "Stage 3\n批量去重", "Stage 4\n全量 OOS"]
    y0 = CONTENT_T + Inches(0.2)
    for i, st in enumerate(stages):
        yy = y0 + i * Inches(0.72)
        box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.1), yy, Inches(4.2), Inches(0.58))
        box.fill.solid()
        box.fill.fore_color.rgb = ACCENT if i % 2 == 0 else INK
        box.line.fill.background()
        box.shadow.inherit = False
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.1); tf.margin_right = Inches(0.1)
        tf.margin_top = Inches(0.02); tf.margin_bottom = Inches(0.02)
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        for j, seg in enumerate(st.split("\n")):
            p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.CENTER
            r = p.add_run(); r.text = seg
            set_font(r, 11.5 if j == 0 else 10, j == 0, WHITE)
    add_takeaway(s, "生成与验证彻底分离：LLM 只提公式，IC 与相关性判定全部由确定性代码完成。")
    add_notes(s, "技能架构的设计动机是：LLM 擅长符号推理，但数值计算不可靠——让 LLM 自己报 IC 就会产生\"计算幻觉\"。"
                  "所以论文把整个因子评估封装成独立可复用的 Agent Skill：底层是 60 多个金融算子，比如 TsRank（时序秩）、Rsquare（滚动回归 R²），全部 GPU 加速；"
                  "上层是五阶段验证管线：Stage 1 在小资产子集上快速筛 IC，过不了 |IC|≥τ 直接淘汰；Stage 2 跟整个库做相关性检查，超 θ 就拒绝；"
                  "Stage 2.5 是替换检查——如果新候选与某个已有因子高度相关但严格更优，允许替换；Stage 3 在当前批次内去重；Stage 4 全资产 OOS 验证。"
                  "右侧就是这条管线。三个优势：防计算幻觉、换配置文件就能跨市场复用、评估引擎可以独立优化而不用重训 LLM。")
    footer(s, 6)

    # ============ S7 经验记忆 ============
    s = new_slide(prs)
    add_title(s, "经验记忆：成功模式、禁区与战略洞察", "三个算子驱动记忆生命周期: 形成 F → 演化 E → 检索 R")
    add_bullets(s, MARGIN_L, CONTENT_T, Inches(7.0), Inches(3.6), [
        ("记忆形成 F: ", "从每批挖掘轨迹 τ_t 提取符号模式——通过准入的归入成功模式 P_succ，因高相关被拒的归入禁区 P_fail"),
        ("记忆演化 E: ", "合并冗余条目、淘汰低效用信息；如 VWAP 偏离类因子与库内相关 0.82，即被重分类为禁区"),
        ("记忆检索 R: ", "按库诊断与近期拒绝原因匹配，生成\"推荐方向/禁忌方向\"自然语言先验注入提示词"),
    ], size=13)
    # 右侧: 记忆内容三分类
    y0 = CONTENT_T + Inches(0.1)
    mems = [
        ("挖掘状态 S", "库规模 |L|、准入日志、饱和指标", ACCENT),
        ("结构经验 P", "推荐方向 P_succ + 禁区 P_fail", INK),
        ("战略洞察 I", "如: 非线性合成优于线性、高阶矩在高频不稳", ACCENT2),
    ]
    for i, (t1, t2, col) in enumerate(mems):
        yy = y0 + i * Inches(1.15)
        box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.2), yy, Inches(4.1), Inches(0.98))
        box.fill.solid(); box.fill.fore_color.rgb = WHITE
        box.line.color.rgb = col
        box.line.width = Pt(1.2)
        box.shadow.inherit = False
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.15); tf.margin_right = Inches(0.12)
        tf.margin_top = Inches(0.08)
        p = tf.paragraphs[0]
        r = p.add_run(); r.text = t1
        set_font(r, 13, True, col)
        p2 = tf.add_paragraph()
        r2 = p2.add_run(); r2.text = t2
        set_font(r2, 10.5, False, BODY)
    add_takeaway(s, "记忆保存的是\"该往哪挖、别再往哪挖\"的结构知识，而非原始轨迹数据。")
    add_notes(s, "经验记忆是论文的第二个支柱。它不存原始数据，只存蒸馏后的结构知识。生命周期由三个算子管理："
                  "形成算子 F 在每批挖掘结束后分析轨迹，通过准入的提炼成成功模式 P_succ，因为高相关被拒的归入禁区 P_fail；"
                  "演化算子 E 负责合并冗余、淘汰低效用条目——论文举例：某个 VWAP 偏离变体被准入后发现和库内因子相关 0.82，就把它重分类进禁区，防止以后重复探索；"
                  "检索算子 R 在生成阶段按当前库的诊断和最近的拒绝原因取回先验，写成\"推荐方向/禁忌方向\"两段自然语言模板注入提示词。"
                  "右侧是记忆的三块内容：挖掘状态 S（库规模、准入日志、饱和指标）、结构经验 P（推荐方向+禁区）、战略洞察 I（例如非线性组合优于线性、高阶矩在高频数据上不稳定这类教训）。")
    footer(s, 7)

    # ============ S8 Ralph Loop 四步循环 ============
    s = new_slide(prs)
    add_title(s, "Ralph Loop：检索 → 生成 → 评估 → 蒸馏", "一次循环 = 一轮批量挖掘 + 一次记忆更新")
    loop = ["① 检索\nm ← R(M, L)", "② 引导生成\nC ~ π(α|m)", "③ 多阶段评估\nStage 1-4", "④ 蒸馏更新\nM ← Ψ(M, τ)"]
    y0 = CONTENT_T + Inches(0.3)
    x0 = MARGIN_L + Inches(0.2)
    bw = Inches(2.5)
    gap = Inches(0.35)
    for i, (label, col) in enumerate(zip(loop, [ACCENT, INK, ACCENT2, GREEN])):
        xx = x0 + i * (bw + gap)
        box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, xx, y0, bw, Inches(1.6))
        box.fill.solid(); box.fill.fore_color.rgb = col
        box.line.fill.background()
        box.shadow.inherit = False
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.margin_left = Inches(0.12); tf.margin_right = Inches(0.12)
        for j, seg in enumerate(label.split("\n")):
            p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.CENTER
            r = p.add_run(); r.text = seg
            set_font(r, 14 if j == 0 else 11, j == 0, WHITE)
        if i < 3:
            ar = s.shapes.add_shape(MSO_SHAPE.CHEVRON, xx + bw - Inches(0.06), y0 + Inches(0.55),
                                    Inches(0.4), Inches(0.5))
            ar.fill.solid(); ar.fill.fore_color.rgb = GRAY_LINE
            ar.line.fill.background()
            ar.shadow.inherit = False
    add_bullets(s, MARGIN_L, y0 + Inches(2.0), SLIDE_W - MARGIN_L - MARGIN_R, Inches(2.4), [
        ("评估多阶段: ", "Stage 1 快速 IC 筛选(小资产子集) → Stage 2 与全库相关性检查(θ) → Stage 2.5 替换检查(严格更优才换) → Stage 3 批量去重 → Stage 4 全量资产 OOS"),
        ("正反馈: ", "每轮准入/拒绝的结论蒸馏回记忆，下一轮采样更靠近正交可行域"),
    ], size=13)
    add_takeaway(s, "循环让\"探索效率\"本身随轮次增长——记忆即搜索策略的学习器。")
    add_notes(s, "把三块拼起来就是 Ralph Loop，对应论文 Algorithm 1。每一步展开："
                  "检索：从记忆 M 和当前库 L 计算记忆信号 m；"
                  "生成：LLM 以 m 为提示先验，从算子库采样一批候选 C；"
                  "评估：走四阶段管线，先快速 IC 筛选，再与全库做相关性检查，然后是替换检查和批量去重，最后全量 OOS；"
                  "蒸馏：把本批每个候选的公式、IC、相关性、准入决定写回记忆，更新成功模式和禁区。"
                  "循环直到库规模达到 K 或预算耗尽。要点是正反馈：每轮准入/拒绝的结论都改变下一轮的采样分布，探索效率随轮次单调增长——这是与一次性挖掘的本质区别。")
    footer(s, 8)

    # ============ S9 实验设置 ============
    s = new_slide(prs)
    add_title(s, "评测设置：多市场、统一协议、公平基线", "预测目标: 下一 10 分钟 open-to-close 收益率")
    add_bullets(s, MARGIN_L, CONTENT_T, Inches(6.6), Inches(3.8), [
        ("数据: ", "A 股三大指数成分（CSI500/CSI1000/HS300，10 分钟 K 线，合计超 2500 万条）+ 币安 64 资产加密货币 10 分钟 K 线"),
        ("划分: ", "训练期 2024 Q1–Q4，留出测试期 2025"),
        ("协议: ", "Top-40 冻结——仅在 CSI500(2024) 上选一次，冻结后跨全部市场评测"),
        ("基线: ", "Alpha101(经典/高频适配)、随机公式、GPLearn、AlphaForge、AlphaAgent，共用同一算子库与准入规则"),
        ("LLM: ", "Gemini 3.0 Flash 符号程序合成"),
    ], size=12.5)
    # 右侧 指标
    add_metric_chip(s, Inches(8.0), CONTENT_T, Inches(2.2), "IC", "截面 Spearman 秩相关（信号 vs 次期收益）", ACCENT)
    add_metric_chip(s, Inches(10.3), CONTENT_T, Inches(2.2), "ICIR", "IC 均值 / IC 标准差（时序稳定性）", INK)
    add_metric_chip(s, Inches(8.0), CONTENT_T + Inches(1.15), Inches(2.2), "ρ<θ", "库内因子两两相关性上限（正交预算）", ACCENT2)
    add_metric_chip(s, Inches(10.3), CONTENT_T + Inches(1.15), Inches(2.2), "|IC|≥τ", "准入的 IC 绝对阈值", GREEN)
    add_takeaway(s, "所有方法共享算子库、准入规则与评测引擎——对比只隔离\"搜索算法\"本身。")
    add_notes(s, "实验设置。数据分两个市场：A 股三大指数成分——CSI500 中盘、CSI1000 中小盘、HS300 大盘，用 10 分钟 K 线，合计超过 2500 万条数据点；"
                  "加密货币市场用币安 64 个主要资产的 10 分钟 K 线。训练期 2024 年 Q1 到 Q4，测试期是留出的 2025 年。预测目标是下一根 10 分钟 K 线的开收比（open-to-close 收益率）。"
                  "协议是 Top-40 冻结：只在 CSI500 的 2024 年数据上选一次 Top-40 因子，然后冻结，拿到全部市场评测，杜绝测试期选择偏差。"
                  "基线六个：Random Formula、Alpha101 经典版和高频适配版、GPLearn、AlphaForge、AlphaAgent。所有方法共用同一个算子库、准入规则和评测引擎，所以对比隔离的就是搜索算法本身。"
                  "LLM 骨干用 Gemini 3.0 Flash。右边是四个核心指标：IC 是截面秩相关，ICIR 是时序稳定性，ρ<θ 是正交预算，|IC|≥τ 是准入阈值。")
    footer(s, 9)

    # ============ S10 主结果: Table 1 ============
    s = new_slide(prs)
    add_title(s, "主结果：四市场样本外 IC/ICIR 全面领先", "2025 样本外, Top-40 冻结协议")
    # 表格数据: 等待 librarian 确认
    rows = [
        ["方法", "CSI500", "CSI1000", "HS300", "Crypto"],
        ["Random Formula", "2.68 / 0.25", "2.88 / 0.30", "1.94 / 0.15", "1.45 / 0.09"],
        ["Alpha101 Classic", "4.49 / 0.42", "4.86 / 0.50", "3.44 / 0.26", "2.11 / 0.14"],
        ["Alpha101 Adapted", "5.06 / 0.43", "5.32 / 0.49", "4.00 / 0.28", "2.40 / 0.15"],
        ["GPLearn", "6.04 / 0.43", "5.86 / 0.48", "4.12 / 0.16", "2.50 / 0.15"],
        ["AlphaForge", "4.48 / 0.38", "4.64 / 0.42", "3.53 / 0.25", "2.52 / 0.16"],
        ["AlphaAgent", "5.90 / 0.46", "6.21 / 0.51", "4.69 / 0.30", "2.86 / 0.17"],
        ["FactorMiner", "8.25 / 0.77", "7.78 / 0.76", "7.46 / 0.38", "3.82 / 0.28"],
    ]
    t = add_table(s, MARGIN_L, CONTENT_T + Inches(0.15), Inches(12.1), Inches(3.4), rows, 5,
                  [Inches(2.7), Inches(2.35), Inches(2.35), Inches(2.35), Inches(2.35)])
    style_table_borders(t)
    add_text(s, MARGIN_L, Inches(4.6), Inches(12.1), Inches(0.5),
             [("格式: IC(%) / ICIR。粗体行 = FactorMiner（最后一行）。", 10, False, MUTED)])
    # 高亮 FactorMiner 行
    for c in range(5):
        cell = t.table.cell(7, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(0xE3, 0xEF, 0xF7)
        cell.text_frame.paragraphs[0].runs[0].font.bold = True
        cell.text_frame.paragraphs[0].runs[0].font.color.rgb = INK
    add_metric_chip(s, MARGIN_L, Inches(5.15), Inches(3.6), "≈40%", "CSI500 IC 相对最强基线 AlphaAgent 的提升", GREEN)
    add_metric_chip(s, Inches(4.6), Inches(5.15), Inches(3.6), "≈67%", "CSI500 ICIR 相对 AlphaAgent 的提升", GREEN)
    add_metric_chip(s, Inches(8.6), Inches(5.15), Inches(3.6), "4/4", "四个市场 IC 与 ICIR 全部第一", ACCENT)
    add_notes(s, "主结果。这是 2025 年样本外、Top-40 冻结协议下的完整对比表，格式是 IC(%)/ICIR，数字逐一核对了论文 Table 1。"
                  "FactorMiner 在四个市场全部第一：CSI500 上 IC 8.25%、ICIR 0.77；CSI1000 上 7.78/0.76；HS300 上 7.46/0.38；加密市场 3.82/0.28。"
                  "各市场最强基线不同：CSI500/CSI1000 是 AlphaAgent（5.90/0.46、6.21/0.51），HS300 是 GPLearn（4.12/0.16），加密市场是 AlphaAgent（2.86/0.17）。"
                  "相对各自最强基线，IC 提升分别约 40%、25%、81%、34%——越难的市场（HS300 大盘、加密）领先幅度越大。"
                  "HS300 的 IC 绝对值整体比中小盘低——大盘股微观结构信号更弱，这是市场特性，所有方法在 HS300 上都更低。"
                  "加密市场数值低但 FactorMiner 依然领先，说明方法跨市场泛化。注意论文 4.2.3 正文引用的 ICIR 与 Table 1 数值略有出入（正文写 EW/ICW 1.52/1.54），我们以 Table 1 为准。")
    footer(s, 10)

    # ============ S11 多样性 + 集成消融 ============
    s = new_slide(prs)
    add_title(s, "低冗余库红利：简单加权即可榨干预测力", "正交性在建库时内嵌 → 集成学习几乎没有剩余可挖")
    add_bullets(s, MARGIN_L, CONTENT_T, Inches(6.6), Inches(3.2), [
        ("库内冗余: ", "Top-40 选中集 A 股平均绝对相关 0.30–0.31、加密市场 0.25；全库 110 因子平均仅 0.203"),
        ("集成对比: ", "FactorMiner 库上等权(EW)/IC 加权(ICW) 组合 ICIR 达 1.29/1.31，Lasso/XGBoost 仅 1.21/1.29——学习式选择不再带来提升"),
        ("对照基线: ", "多数基线库上学习式选择有明确增益，说明其库内冗余未受控"),
    ], size=12.5)
    # 右侧 简单柱状对比
    add_text(s, Inches(7.6), CONTENT_T, Inches(5.0), Inches(0.3),
             [("组合 ICIR（CSI500 测试期）", 11.5, True, INK)])
    bars = [("EW", 1.29, GREEN), ("ICW", 1.31, GREEN), ("Lasso", 1.21, ACCENT2), ("XGBoost", 1.29, ACCENT2)]
    bx = Inches(7.6); by = CONTENT_T + Inches(0.45)
    bw2 = Inches(0.7); bgap = Inches(0.5)
    for i, (name, val, col) in enumerate(bars):
        xx = bx + i * (bw2 + bgap)
        hh = Inches(val * 1.6)
        bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, xx, by + Inches(2.4) - hh, bw2, hh)
        bar.fill.solid(); bar.fill.fore_color.rgb = col
        bar.line.fill.background(); bar.shadow.inherit = False
        add_text(s, xx, by + Inches(2.5), bw2, Inches(0.3),
                 [(name, 11, True, INK)], align=PP_ALIGN.CENTER)
    add_text(s, bx, by + Inches(2.8), Inches(5.0), Inches(0.3),
             [("刻度示意（1.0 单位 = 0.6 英寸）", 9, False, MUTED)])
    add_takeaway(s, "建库阶段的正交约束省掉了下游的模型选择——简单加权即达最优。")
    add_notes(s, "这一页讲因子库的低冗余特性带来的下游红利。先看冗余数字：A 股三个市场库内因子平均绝对相关只有 0.30 到 0.31，加密市场约 0.25——正交约束在建库时就内嵌了。"
                  "然后论文做了一个有趣的实验：把因子库喂给等权（EW）、IC 加权（ICW）和两个学习式选择模型（Lasso、XGBoost），比较组合的 ICIR。"
                  "结果是 FactorMiner 的库上 EW 和 ICW 已经到 1.29 和 1.31，Lasso 和 XGBoost 反而只有 1.21 和 1.29——学习式选择不再带来提升。"
                  "对照基线的库，学习式选择普遍有明显增益，因为它们库内冗余没有受控。右边是 ICIR 的示意柱状对比。"
                  "这个结果的解读：正交化在挖掘阶段完成，等权加权就已经把可挖掘的预测信号基本提取干净了——库本身就是结构化资产。")
    footer(s, 11)

    # ============ S12 记忆消融 ============
    s = new_slide(prs)
    add_title(s, "消融：经验记忆是效率与精度的来源", "关闭记忆算子 F/E/R 对比 (阈值放宽: |IC|>0.02, θ=0.85)")
    rows = [
        ["指标", "无记忆 (No Memory)", "带记忆 (FactorMiner)", "变化"],
        ["高质量候选数", "32", "96", "+200% (3×)"],
        ["高质量候选产出率 (yield)", "20.0%", "60.0%", "+40pp"],
        ["准入因子数", "18", "43", "+139%"],
        ["因冗余被拒候选数", "14", "53", "+279%"],
        ["被拒率 (冗余)", "43.8%", "55.2%", "更严正交把关"],
    ]
    t = add_table(s, MARGIN_L, CONTENT_T + Inches(0.15), Inches(10.6), Inches(2.3), rows, 4,
                  [Inches(3.6), Inches(2.6), Inches(2.6), Inches(1.8)])
    style_table_borders(t)
    for c in range(4):
        cell = t.table.cell(1, c)
        cell.text_frame.paragraphs[0].runs[0].font.bold = (c in (0, 3))
    add_text(s, MARGIN_L, Inches(4.1), Inches(10.6), Inches(1.2),
             [("被拒率上升是设计使然: ", 13.5, True, INK),
              ("记忆引导的候选 IC 更高、但也更容易撞上既有库——去重环节必须更用力才能保住正交性。这正对应记忆的 Ψ 算子把单目标 IC 搜索升级为 IC+正交联合优化。",
               13, False, BODY)])
    add_metric_chip(s, MARGIN_L, Inches(5.5), Inches(3.8), "3×", "高质量候选产出率提升", GREEN)
    add_metric_chip(s, Inches(4.6), Inches(5.5), Inches(3.8), "+25", "净新增准入因子 (43−18)", ACCENT)
    add_notes(s, "关键消融（论文 Figure 3 的完整数据）：关掉记忆的三个算子（形成 F、演化 E、检索 R），其余配置完全一样。"
                  "为控制变量，本次消融放宽了阈值（IC 门槛 |IC|>0.02、相关性门槛 θ=0.85），保证两组都有足够样本。"
                  "带记忆组产出 96 个高质量候选、无记忆组只有 32 个——产出率从 20.0% 提升到 60.0%，正好 3 倍。"
                  "最终准入因子数从 18 增加到 43。最反直觉的是第三块：带记忆组因冗余被拒的候选更多（53 vs 14，被拒率 55.2% vs 43.8%）。"
                  "被拒率上升不是坏事——记忆引导的候选 IC 更高，但也更容易撞上既有库，去重环节必须更用力才能保住正交性。"
                  "这正是记忆蒸馏算子 Ψ 的作用：把单目标 IC 搜索升级成 IC+正交的联合优化。"
                  "结论：记忆让搜索更精准——既更多地产出高质量候选，又更严格地维护库的正交性。")
    footer(s, 12)

    # ============ S13 计算效率 ============
    s = new_slide(prs)
    add_title(s, "轻量高效：GPU 算子 + 多进程并行", "评估引擎是支撑大规模迭代的物质基础")
    add_metric_chip(s, MARGIN_L, CONTENT_T, Inches(3.0), "8–59×", "核心算子相对 Pandas 实现加速", ACCENT)
    add_metric_chip(s, Inches(3.9), CONTENT_T, Inches(3.0), "2–13×", "相对 C 编译实现的加速", INK)
    add_metric_chip(s, Inches(6.8), CONTENT_T, Inches(3.0), "23–27×", "排序密集型端到端评估加速", ACCENT2)
    add_metric_chip(s, Inches(9.7), CONTENT_T, Inches(3.0), "40", "worker 多进程并行评估池", GREEN)
    add_bullets(s, MARGIN_L, Inches(2.6), Inches(11.5), Inches(2.6), [
        ("算子级示例: ", "TsRank 1,843ms(Pandas)→393ms(C)→31ms(GPU)；CsRank 445→49→26ms；GPU 平均比 C 快 5.4×"),
        ("算子级加速: ", "CsRank 26×、TsRank 17×、TsDecay 9×、Rolling Corr 6.8×（单张 A100, 相对 CPU）"),
        ("典型吞吐: ", "1000 个候选因子全流程评估约 6 分钟，传统方法约 70 分钟"),
        ("技术栈: ", "NumPy + CuPy（GPU 加速）、C 编译算子、40 worker 多进程并行，适配不同服务器配置"),
    ], size=12.5)
    add_takeaway(s, "效率换来了\"大规模迭代\"的可行性——每轮循环可以同时评估整批候选。")
    add_notes(s, "效率是这套系统能落地的物质基础（论文 Figure 4，真实 CSI500 矩阵 12,610×500）。算子层面：GPU 加速的算子相对纯 Pandas 快 8 到 59 倍，相对 C 编译实现也快 2 到 13 倍。"
                  "具体例子：TsRank 从 Pandas 的 1843 毫秒降到 C 的 393 毫秒、再降到 GPU 的 31 毫秒；CsRank 445→49→26 毫秒。GPU 平均比手写 C 还快 5.4 倍（202ms vs 1092ms）。"
                  "独立基准（Appendix D, Table 3）里核心算子在单张 A100 上相对 CPU 加速：CsRank 26×、TsRank 17×、TsDecay 9×、Rolling Corr 6.8×。"
                  "排序密集型端到端评估（F43/F48/F53）快 23 到 27 倍。吞吐层面：1000 个候选因子全流程评估大约 6 分钟，传统 Pandas 路线要 70 分钟量级。"
                  "工程上是一个 40 worker 的多进程池做并行评估，算子层用 NumPy + CuPy，热路径用 C 编译。"
                  "这个效率的意义：Ralph Loop 每轮可以同时评估整批候选，大规模迭代才有可行性——否则自进化循环根本转不动。")
    footer(s, 13)

    # ============ S14 讨论 / 局限 ============
    s = new_slide(prs)
    add_title(s, "讨论与局限：记忆即持续学习", "边界要讲清楚，才能判断这套框架能搬到哪")
    add_bullets(s, MARGIN_L, CONTENT_T, Inches(11.5), Inches(3.4), [
        ("持续学习视角: ", "经验记忆可视为不依赖重放缓冲的持续学习——符号规则 + 汇总统计，天然抵抗灾难性遗忘"),
        ("跨市场迁移: ", "A 股训练的记忆零样本迁移到加密市场仍有增益，技能层换配置即用"),
        ("局限一(原文): ", "仅内部评测与库构建，未与端到端预测模型做受控对比（Section 7）"),
        ("局限二(原文): ", "因子可能被误用于投机/操纵策略；部署需合规审查与风险控制（Section 7）"),
        ("局限三(原文): ", "成本感知回测、更广资产与频率、在线记忆更新均列为未来工作（Section 6）"),
    ], size=12.5)
    add_takeaway(s, "框架的价值在\"可持续的发现能力\"：库越大、轮次越多，记忆的回报越高。", color=ACCENT2)
    add_notes(s, "讨论与局限。论文把经验记忆放在持续学习的视角下看：它不依赖重放缓冲，而是把经验蒸馏成符号规则和汇总统计，天然抵抗灾难性遗忘，这是与 RL/GP 类方法的关键差别。"
                  "跨市场迁移也有亮点：A 股训练出的记忆零样本迁移到加密市场仍然有效，技能层换配置文件即可复用。"
                  "局限按论文原文（Section 7）讲：第一，论文只做内部评测、库构建与分析，没有和端到端预测模型做受控对比；"
                  "第二，论文自己提示伦理风险——挖掘出的因子可能被误用于投机或操纵策略，部署必须合规审查并配风险控制；"
                  "第三，论文把交易成本感知的回测、更广资产与频率、面向非平稳市场的在线记忆更新明确列为未来工作。"
                  "另外补充两点论文没细谈的观察：只用了一个 LLM 骨干 Gemini 3.0 Flash，没做骨干敏感性分析；评测口径以 IC/ICIR 预测精度为主。"
                  "这些局限决定了这套框架当前更适合研究场景而非直接实盘。")
    footer(s, 14)

    # ============ S15 总结 ============
    s = new_slide(prs)
    add_title(s, "总结：把\"找因子\"变成\"学会找因子\"", "四项贡献 + 一个开放成果")
    add_bullets(s, MARGIN_L, CONTENT_T, Inches(11.5), Inches(3.2), [
        ("经验记忆: ", "把挖掘轨迹蒸馏为成功模式/禁区/洞察，实现跨会话知识积累与自进化"),
        ("技能架构: ", "评估封装为可复用工具，杜绝计算幻觉，支持跨市场复用与独立升级"),
        ("全局库视角: ", "准入机制内嵌正交约束，直接对抗\"相关性红海\""),
        ("轻量系统: ", "GPU + 多进程 + C 编译，千级因子分钟级评估"),
        ("开放成果: ", "公开 110 个经真实数据验证的 A 股公式化因子库，可直接用于下游研究"),
    ], size=13)
    add_text(s, MARGIN_L, Inches(5.6), Inches(11.5), Inches(1.0),
             [("未来工作: ", 13, True, INK),
              ("交易成本感知回测、更广资产与频率、面向非平稳市场的在线记忆更新。", 12.5, False, BODY)])
    add_takeaway(s, "FactorMiner 证明：因子挖掘的瓶颈可以从\"生成更多\"转向\"更聪明地记忆\"。", color=ACCENT)
    add_notes(s, "总结。论文把\"找因子\"升级成\"学会找因子\"：经验记忆让知识跨会话积累，技能架构让评估确定可靠，全局库视角直接对抗相关性红海，轻量引擎让千级因子分钟级评估，"
                  "并且开源了 110 个经过真实数据验证的 A 股公式化因子库——这是可以直接复用的研究资产。"
                  "未来工作：加入交易成本感知的回测、扩展到更广的资产和频率、做面向非平稳市场的在线记忆更新。"
                  "对我的借鉴：一是\"评估与生成解耦\"的架构思路可以直接借鉴到我们自己的因子挖掘管线；二是\"记忆即搜索策略\"的想法——把每轮挖掘的成败结构化沉淀，"
                  "减少重复试错——对我们的研究三机制挖掘流程有直接参考价值。")
    footer(s, 15)

    prs.save(OUT_PATH)
    print("saved:", OUT_PATH)
    print("slides:", len(prs.slides.__iter__.__self__._sldIdLst))


if __name__ == "__main__":
    build()