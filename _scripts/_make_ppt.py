# -*- coding: utf-8 -*-
"""生成项目汇报 PPT（含讲稿备注）。"""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "行李提醒Agent_汇报PPT.pptx"

# ---- 配色 ----
NAVY = RGBColor(0x0B, 0x3D, 0x5C)
TEAL = RGBColor(0x0F, 0x8B, 0x8B)
INK = RGBColor(0x1F, 0x29, 0x33)
GRAY = RGBColor(0x6B, 0x74, 0x80)
RED = RGBColor(0xC0, 0x39, 0x2B)
GREEN = RGBColor(0x2E, 0x7D, 0x32)
AMBER = RGBColor(0xD3, 0x7B, 0x12)
BG_SOFT = RGBColor(0xF2, 0xF6, 0xF9)
BG_WARN = RGBColor(0xFD, 0xF0, 0xEE)
BG_OK = RGBColor(0xEC, 0xF6, 0xEC)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

FONT = "微软雅黑"

W, H = Inches(13.333), Inches(7.5)
LEFT = Inches(0.75)
CONTENT_W = Inches(11.83)


def _set_font(run, size, color=INK, bold=False):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def page_frame(slide, title, subtitle=None):
    """通用页眉：标题 + 下方细线。"""
    tb = slide.shapes.add_textbox(LEFT, Inches(0.5), CONTENT_W, Inches(0.75))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = title
    _set_font(r, 30, NAVY, bold=True)

    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, LEFT, Inches(1.42), Inches(1.5), Inches(0.055))
    line.fill.solid()
    line.fill.fore_color.rgb = TEAL
    line.line.fill.background()
    line.shadow.inherit = False

    y = 1.42
    if subtitle:
        tb2 = slide.shapes.add_textbox(Inches(2.45), Inches(1.38), Inches(10.1), Inches(0.4))
        tf2 = tb2.text_frame
        tf2.word_wrap = True
        p2 = tf2.paragraphs[0]
        r2 = p2.add_run()
        r2.text = subtitle
        _set_font(r2, 13, GRAY)
    return y


def bullets(slide, items, top=Inches(1.95), width=CONTENT_W, left=LEFT, size=17, gap=0.62):
    """要点列表，支持 (文本, 层级, 颜色) 或纯文本。"""
    tb = slide.shapes.add_textbox(left, top, width, Inches(0.5))
    tf = tb.text_frame
    tf.word_wrap = True
    first = True
    for it in items:
        if isinstance(it, tuple):
            text, level = it[0], it[1]
            color = it[2] if len(it) > 2 else INK
        else:
            text, level, color = it, 0, INK
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.space_after = Pt(gap * 72 / 10)
        prefix = "▪  " if level == 0 else "    – "
        r = p.add_run()
        r.text = prefix + text
        _set_font(r, size if level == 0 else size - 3, color, bold=(level == 0))
    return tb


def note(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def box(slide, x, y, w, h, fill, text, size=15, color=INK, bold=False, line=None):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line:
        sh.line.color.rgb = line
        sh.line.width = Pt(1.2)
    else:
        sh.line.fill.background()
    sh.shadow.inherit = False
    tf = sh.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = Inches(0.16)
    tf.margin_right = Inches(0.16)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = text
    _set_font(r, size, color, bold)
    return sh


def arrow(slide, x, y, w=Inches(0.45), h=Inches(0.24)):
    sh = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x, y, w, h)
    sh.fill.solid()
    sh.fill.fore_color.rgb = TEAL
    sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def stats(slide, y, pairs, w=Inches(2.6), h=Inches(1.15), gap=Inches(0.35)):
    """一排数字卡片：pairs = [(值, 标签), ...]"""
    n = len(pairs)
    total = n * w + (n - 1) * gap
    x0 = (W - total) // 2
    for i, (val, label) in enumerate(pairs):
        x = x0 + i * (w + gap)
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
        card.fill.solid()
        card.fill.fore_color.rgb = BG_SOFT
        card.line.fill.background()
        card.shadow.inherit = False
        tf = card.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = val
        _set_font(r, 26, NAVY, bold=True)
        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run()
        r2.text = label
        _set_font(r2, 12, GRAY)


def table(slide, data, left, top, width, height, col_widths=None, header_fill=NAVY, font_size=14):
    rows, cols = len(data), len(data[0])
    shape = slide.shapes.add_table(rows, cols, left, top, width, height)
    tbl = shape.table
    if col_widths:
        for i, cw in enumerate(col_widths):
            tbl.columns[i].width = cw
    for ri, row in enumerate(data):
        tbl.rows[ri].height = Inches(0.45)
        for ci, val in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.text = str(val)
            cell.margin_left = Inches(0.1)
            cell.margin_right = Inches(0.1)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            for r in p.runs:
                r.font.name = FONT
                r.font.size = Pt(font_size)
                if ri == 0:
                    r.font.bold = True
                    r.font.color.rgb = WHITE
                else:
                    r.font.color.rgb = INK
                    r.font.bold = (ci == 0)
            cell.fill.solid()
            if ri == 0:
                cell.fill.fore_color.rgb = header_fill
            else:
                cell.fill.fore_color.rgb = WHITE if ri % 2 else BG_SOFT
    return tbl


def main():
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H

    # ============ 1 封面 ============
    s = blank(prs)
    band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, Inches(0.22))
    band.fill.solid()
    band.fill.fore_color.rgb = TEAL
    band.line.fill.background()
    band.shadow.inherit = False

    tb = s.shapes.add_textbox(LEFT, Inches(2.0), CONTENT_W, Inches(1.2))
    tf = tb.text_frame
    tf.word_wrap = True
    r = tf.paragraphs[0].add_run()
    r.text = "行李必备物品提醒 Agent"
    _set_font(r, 44, NAVY, bold=True)

    tb2 = s.shapes.add_textbox(LEFT, Inches(3.25), CONTENT_W, Inches(0.6))
    tf2 = tb2.text_frame
    tf2.word_wrap = True
    r2 = tf2.paragraphs[0].add_run()
    r2.text = "出门前拍一张行李照，AI 告诉你「带齐了没、东西在哪」"
    _set_font(r2, 19, GRAY)

    box(s, LEFT, Inches(4.3), Inches(7.6), Inches(0.9), BG_SOFT,
        "Qwen2.5-VL-3B 视觉语言模型  +  QLoRA 微调", 16, NAVY, True)

    tb3 = s.shapes.add_textbox(LEFT, Inches(5.6), CONTENT_W, Inches(0.5))
    tf3 = tb3.text_frame
    r3 = tf3.paragraphs[0].add_run()
    r3.text = "汇报人：门文迪　|　RTX 4060 8GB 消费级显卡可训可跑　|　2026-10"
    _set_font(r3, 13, GRAY)
    note(s, "老师好，同学们好。我汇报的题目是「行李必备物品提醒 Agent」。\n"
            "一句话概括我们要做的事：出门旅游前，你把自己收拾好的行李拍一张照片发给它，"
            "它就能告诉你身份证带了没、充电器带了没、在哪一个格子里。\n"
            "技术上我们用的是通义千问的视觉语言模型 Qwen2.5-VL，加上 QLoRA 微调。"
            "整个训练是在一张普通的 RTX 4060 笔记本显卡上跑的，8G 显存，不需要服务器。\n"
            "下面我按「为什么要做—怎么做—做到什么程度—还差什么」的顺序讲。")

    # ============ 2 要解决什么问题 ============
    s = blank(prs)
    page_frame(s, "一、我们要解决的问题")
    bullets(s, [
        "出门 / 旅游前，总担心忘带东西",
        "现有清单 App 要手动一项项勾，用起来麻烦，也容易漏",
        "我们的想法：拍一张照片，让 AI 直接「看图」判断",
        "模型要回答两个问题：",
        ("① 清单里的每一项，带了还是没带？", 1),
        ("② 如果带了，在照片的哪个位置？（如「左侧内袋」「桌上」）", 1),
    ])
    box(s, LEFT, Inches(5.35), CONTENT_W, Inches(1.05), BG_SOFT,
        "举个例子：照片里有充电器，模型输出 {\"充电器\": true, \"位置\": \"黑色收纳包内\"}", 15, NAVY)
    note(s, "先说问题。大家应该都有过这种体验：出门前一天晚上反复想，身份证带了吗、充电器带了吗。\n"
            "市面上有清单 App，但都要你自己一项一项去点，其实也不省事。\n"
            "所以我们想做的是反过来——你什么都不用填，就拍一张你行李的照片。"
            "模型看完图以后，直接告诉你两件事：第一，清单上的东西带没带；第二，带了的话在哪，"
            "比如它会说『充电器在黑色收纳包里』。\n"
            "这个输出形式是刻意选的：我们让它说人话描述位置，而不是画一个坐标框，"
            "因为说一句话标注起来比画框快五到十倍。")

    # ============ 3 技术选型 ============
    s = blank(prs)
    page_frame(s, "二、为什么选这个技术方案")
    bullets(s, [
        "这是「看懂图片」的任务，不是「生成图片」",
        ("所以用的是视觉语言模型 VLM，不是 Stable Diffusion 那类画图模型", 1),
        "基座选 Qwen2.5-VL-3B：中文理解好、体积小、3B 参数量适中",
        "训练方式选 QLoRA：冻结原模型，只训练一小层旁路网络",
        ("产物只有 148MB，而原模型是 7.7GB；8GB 显存就能训", 1),
        "关键取舍：不做像素级框定位，只输出文字位置描述",
        ("代价是位置没那么精确，换来的是标注成本降低 5~10 倍", 1),
    ])
    note(s, "第二，简单说一下技术选型，这里面有两个关键决定。\n"
            "第一个，这个任务是『看懂一张图』，不是『画一张图』，所以用的是视觉语言模型 VLM，"
            "不是大家常听的 Stable Diffusion。模型用的是阿里通义千问的 Qwen2.5-VL，3B 版本。\n"
            "第二个，训练方式用的是 QLoRA。它的意思是：原来的大模型不动，"
            "只在旁边挂一个很小的旁路模块来训练。好处是训练产物只有 148MB，"
            "而原模型是 7.7 个 G，所以我们一张 8G 显存的笔记本显卡就能跑得动。\n"
            "还有一个取舍想强调：我们没有让模型画精确的坐标框，而是让它用一句话描述位置。"
            "精确度上是有损失的，但标注的时候说一句话比画框快五到十倍，对我们这种自己标数据的人来说很值。")

    # ============ 4 流程图 ============
    s = blank(prs)
    page_frame(s, "三、整体流程")
    y = Inches(2.15)
    bw, bh = Inches(1.73), Inches(1.0)
    steps = [
        ("真实行李照片", "11 张", BG_SOFT, INK),
        ("GDINO\n自动预标注", "机器草稿", BG_SOFT, INK),
        ("人工在平台\n逐张手改", "82 个框", BG_SOFT, INK),
        ("别名归类\n整理数据", "normalize.py", BG_OK, GREEN),
        ("QLoRA\n微调训练", "约 5 分钟", BG_SOFT, INK),
        ("推理验证", "出指标", BG_SOFT, INK),
    ]
    x = Inches(0.42)
    for i, (t1, t2, fill, col) in enumerate(steps):
        box(s, x, y, bw, bh, fill, t1, 15, col, True)
        tb = s.shapes.add_textbox(x, y + bh + Inches(0.04), bw, Inches(0.3))
        p = tb.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = t2
        _set_font(r, 11, GRAY)
        if i < len(steps) - 1:
            arrow(s, x + bw + Inches(0.02), y + Inches(0.38), w=Inches(0.35))
        x += bw + Inches(0.37)

    box(s, LEFT, Inches(4.35), CONTENT_W, Inches(0.85), BG_SOFT,
        "前面三步是「准备数据」，中间一步是「整理数据」，最后两步是「训练 + 检验」", 15, NAVY)
    bullets(s, [
        ("其中第 4 步「别名归类」是我们这轮最关键的改进，后面单独讲", 0, RED),
    ], top=Inches(5.45), size=16)
    note(s, "这张图是整个项目的流程，一共六步。\n"
            "左边三步是准备数据：先有真实的行李照片，然后用一个叫 GroundingDINO 的检测模型"
            "自动框出可能是物品的区域，这算是机器打的草稿；接着我自己在标注平台上逐张修改，"
            "错标的改名、误检的删掉、漏标的补上，最后得到 82 个手工标注框。\n"
            "第四步是整理数据，也就是别名归类，这一步是我们这轮效果提升的关键，等下单独讲。\n"
            "最后两步是训练和验证。一轮训练大概五分钟，跑完会出一个评估报告。")

    # ============ 5 数据从哪来 ============
    s = blank(prs)
    page_frame(s, "四、数据是怎么来的")
    bullets(s, [
        "图片：11 张真实行李 / 开箱照（特意选没有文字的，避免文字干扰识别）",
        "第一步 机器预标：GroundingDINO 按 28 类自动框出候选物品 + 生成对照图",
        "第二步 人工修正：自己在标注平台上逐张看，改名字、删误检、补漏标",
        "第三步 导出：每条数据包含 图片 / 提问 / 答案（JSON）",
        "最终结果：11 张图、82 个手画框、64 个「确实带了」的正样本",
    ])
    box(s, LEFT, Inches(5.2), CONTENT_W, Inches(1.0), BG_SOFT,
        "数据量偏小是整个项目目前最大的瓶颈 —— 后面会讲，这也是下一步要补的", 15, AMBER, True)
    note(s, "第四，说说数据。\n"
            "图片是 11 张真实的行李和开箱照片。这里有个小细节：我特意选了没有文字的实拍图，"
            "因为如果照片上有小红书那种种草文案，模型会被文字干扰。\n"
            "标注分两步走。先让 GroundingDINO 这个检测模型自动框出可能是物品的区域，"
            "相当于机器先打一份草稿，同时它会生成带框的对照图方便我看。"
            "然后我在自己搭的标注平台上逐张修改：框错位置的改一下、框错的删掉、漏掉的补上。\n"
            "最后导出成训练格式，每张图一条数据，包含图片、提问和答案。\n"
            "最终是 11 张图、82 个手工框、其中 64 个是确认存在的正样本。\n"
            "这里要坦白一句：11 张确实很少，这是我们目前最大的短板。")

    # ============ 6 清单设计 ============
    s = blank(prs)
    page_frame(s, "五、物品清单的设计")
    bullets(s, [
        "28 个规范物品名，分成 8 大类",
        "证件钱财 · 电子设备 · 衣物鞋帽 · 洗漱护肤 · 健康医药 · 饮食雨具 · 收纳包袋 · 其他",
        "每项配一张「别名表」：同一个东西的不同叫法都归到一个规范名",
        ("收纳包 / 书包 / 双肩包 / 26寸行李箱 / 化妆包  →  全部归到「包袋」", 1, TEAL),
        ("拖鞋 → 鞋子　　排插 → 充电器　　证件包 → 证件", 1, TEAL),
        "清单是「单一数据源」：改这一个文件，标注平台、训练、推理三处同时生效",
    ])
    box(s, LEFT, Inches(5.3), CONTENT_W, Inches(0.9), BG_SOFT,
        "别名表不只让输出好看 —— 它直接决定了标注数据会不会被丢掉（下一页）", 15, NAVY, True)
    note(s, "第五，物品清单。\n"
            "我们定了 28 个规范物品名，分成 8 个大类，比如证件钱财、电子设备、衣物鞋帽这些。\n"
            "这里有个设计很关键：每一项我都配了一张别名表，把同一个东西的不同叫法都收进来。"
            "比如收纳包、书包、双肩包、26 寸行李箱、化妆包，这些名字其实指的都是「包袋」这一类，"
            "全部归到规范名『包袋』下。拖鞋归到鞋子，排插归到充电器，证件包归到证件。\n"
            "另外这个清单是单一数据源，我只改这一个文件，标注平台、训练、推理三个地方会同时生效，"
            "不会出现这边改了那边没改的情况。\n"
            "大家可能会觉得别名表只是让输出好看一点——其实不是，"
            "它直接决定了我标注的数据会不会被丢掉，这就是下一页要讲的。")

    # ============ 7 训练 ============
    s = blank(prs)
    page_frame(s, "六、训练是怎么做的")
    bullets(s, [
        "QLoRA：冻结 7.7GB 原模型，只训练旁路小网络",
        "参数：8 轮、学习率 1e-4、图片最长边压到 512（省显存）",
        "产物：148MB 适配器文件（便于分享，同学拿到就能用）",
        "一轮训练约 5 分钟，16 个训练步",
        "推理 / 验证：11 张图逐张跑，约 10 分钟，输出准确率与 F1",
    ])
    stats(s, Inches(5.15), [("7.7 GB", "原模型"), ("148 MB", "训练产物（占 1.9%）"), ("≈5 分钟", "单轮训练")])
    note(s, "第六，训练。\n"
            "用的是 QLoRA，原理是把 7.7 个 G 的原模型冻住不动，只在旁边训练一个很小的旁路网络。"
            "参数是 8 轮、学习率 1e-4，图片最长边压到 512 像素来省显存。\n"
            "最终产物是一个 148MB 的适配器文件，只占原模型的百分之二左右，很容易分享，"
            "同学拿到这个文件直接加载就能用。\n"
            "一轮训练大概五分钟，一共 16 个训练步。训完再拿那 11 张图逐张跑一遍验证，"
            "大概十分钟，会输出准确率和 F1 这些指标。")

    # ============ 8 关键发现 ============
    s = blank(prs)
    page_frame(s, "七、关键发现：一半的标注被白白丢掉了")
    box(s, LEFT, Inches(1.95), CONTENT_W, Inches(0.95), BG_WARN,
        "诊断发现：我手画的 82 个框，导出训练数据时只有 35 个进去了 —— 丢了 45 个，占 55%", 18, RED, True)
    bullets(s, [
        "原因：名字不在清单里的框，会被程序「静默丢弃」，没有任何提示",
        "被丢得最多的是：收纳包 13 次、梳子 4 次、书包 3 次",
        "还有鞋子、风扇、玩偶、发夹、排插、毛巾、帽子、拖鞋……",
        ("也就是说：标注花了大力气，一半以上是白干的", 0, RED),
    ], top=Inches(3.15), size=17)
    box(s, LEFT, Inches(5.75), CONTENT_W, Inches(0.85), BG_SOFT,
        "这正是模型一开始效果不好的隐藏原因 —— 不是模型不行，是喂进去的数据少了一半", 15, NAVY, True)
    note(s, "这一页是这次项目里最重要的发现，请老师特别注意。\n"
            "我做完标注以后去检查导出的数据，发现一个很严重的问题："
            "我手动画了 82 个框，但是导出成训练数据的时候，只有 35 个进去了，丢了 45 个，超过一半。\n"
            "原因是什么呢？程序在导出的时候会检查框的名字在不在清单里，"
            "不在的就悄悄丢掉，不会报任何错，也不会提示。\n"
            "丢得最多的是『收纳包』，丢了 13 次；还有梳子、书包、鞋子、排插、拖鞋这些。\n"
            "换句话说，我标注花了很大力气，一半以上是白干的。\n"
            "这也解释了为什么模型一开始效果不好——不是模型能力不行，是喂进去的训练数据凭空少了一半。")

    # ============ 9 解决办法 ============
    s = blank(prs)
    page_frame(s, "八、解决办法：自动归类")
    bullets(s, [
        "写了一个归类模块 normalize.py，三步匹配：",
        ("① 精确名匹配　② 查别名表　③ 剥离修饰词（颜色 / 尺寸 / 图案）", 1),
        "实际效果举例：",
        ("双肩包、26寸行李箱、Hello Kitty 图案的内袋  →  「包袋」", 1, TEAL),
        ("蓝色相机  →  「相机」（自动去掉颜色修饰）", 1, TEAL),
        ("粉红色眼镜盒、梳子、发夹  →  「梳妆饰品」　　排插  →  「充电器」", 1, TEAL),
        ("结果：救回率 100%，正样本 35 → 64，多了 83%", 0, GREEN),
    ])
    box(s, LEFT, Inches(5.85), CONTENT_W, Inches(0.8), BG_OK,
        "这一步没有改模型、没有调参数，只是把已有的数据救回来 —— 效果提升的主要来源", 15, GREEN, True)
    note(s, "发现问题以后，对应的解决办法就是做一个自动归类模块。\n"
            "它分三步匹配：先精确匹配名字，再查别名表，最后一步是剥离修饰词——"
            "颜色、尺寸、图案这些前缀都去掉。\n"
            "举几个实际例子：双肩包、26 寸行李箱、甚至『Hello Kitty 图案的内袋』，都会归到『包袋』；"
            "『蓝色相机』会自动去掉颜色，归到『相机』；粉红色眼镜盒、梳子、发夹归到『梳妆饰品』；"
            "排插归到『充电器』。\n"
            "做完这一步，救回率是百分之百，正样本从 35 个涨到 64 个，多了百分之八十三。\n"
            "想强调一下：这一步我们没有换模型，也没有调任何参数，"
            "就是把本来该用上的数据救回来了，而这恰恰是效果提升的主要来源。")

    # ============ 10 提示词不一致 ============
    s = blank(prs)
    page_frame(s, "九、另一个隐蔽的坑：问法不一致")
    bullets(s, [
        "发现：训练时用的提问是短句，推理时用的却是一大段长提示词",
        "相当于「学的是 A 种问法，考的却是 B 种问法」，模型自然答不好",
        "当时的表现：乱报一气，很多没带的东西也被说成带了（精确率只有 24%）",
        "做法：建 prompt.py 作为唯一出处，训练 / 推理 / 标注平台三处共用同一句话",
        "同时把措辞改得更克制（明确要求「宁可漏判，不要瞎猜」）",
    ])
    box(s, LEFT, Inches(5.5), CONTENT_W, Inches(0.9), BG_SOFT,
        "这类问题最危险：训练能跑通、不报错，但结果一直不好，很难想到是这里出问题", 15, NAVY, True)
    note(s, "还有一个坑想分享，因为它特别隐蔽。\n"
            "我发现训练数据里的提问是一句很短的话，但实际推理的时候，程序用的是一大段很长的提示词。"
            "这就相当于——你平时练的是 A 种问法，考试的时候却是 B 种问法，模型当然答不好。\n"
            "当时的表现是模型乱报，明明没带的东西也说带了，精确率只有百分之二十四。\n"
            "解决办法是把提示词抽出来做成一个单独的模块，训练、推理、标注平台三个地方都引用同一句话，"
            "从根上保证一致。同时我把措辞改得更克制，明确要求它『宁可漏判，不要瞎猜』。\n"
            "这类问题最危险的地方在于：程序能正常跑、不报任何错，但效果一直上不去，"
            "而且你很难想到是这里出的问题。")

    # ============ 11 效果对比 ============
    s = blank(prs)
    page_frame(s, "十、效果：三轮迭代的指标变化")
    data = [
        ["指标", "初版（23 项）", "第二版（22 项）", "最终版（28 项 + 归类）"],
        ["逐物准确率", "60.1%", "82.2%", "82.8%"],
        ["精确率 P（说了带，真带了吗）", "24.2%", "35.7%", "61.7%"],
        ["召回率 R（真带了，说出来了吗）", "88.6%", "28.6%", "45.3%"],
        ["F1 综合分", "38.0%", "31.7%", "52.3%"],
    ]
    table(s, data, LEFT, Inches(1.95), CONTENT_W, Inches(2.3),
          col_widths=[Inches(3.6), Inches(2.6), Inches(2.6), Inches(3.03)])
    bullets(s, [
        ("第二版治好了「乱报」，但矫枉过正变得太保守（召回率掉到 28.6%）", 0, AMBER),
        ("最终版靠「把数据救回来」，精确率和召回率同时上涨，F1 从 38% 提到 52.3%", 0, GREEN),
    ], top=Inches(4.5), size=15)
    note(s, "这是效果对比，我们一共迭代了三轮。\n"
            "第一版用的是 23 项清单，逐物准确率 60%，精确率只有 24%——"
            "意思是它说『带了』的东西里面，只有四分之一是真的带了，乱报很严重。\n"
            "第二版我们改了提示词，精确率上去了，但矫枉过正，"
            "模型变得太保守，该认出来的也不认了，召回率掉到 28%。\n"
            "最终版就是做了归类、把数据救回来之后，精确率和召回率同时上涨，"
            "F1 从 38% 提到 52.3%，准确率 82.8%。\n"
            "这里想说明的是：光调参数是救不回来的，真正起作用的是把数据用对。")

    # ============ 12 强弱项 ============
    s = blank(prs)
    page_frame(s, "十一、哪些认得好，哪些还不行")
    left_items = [
        ("认得好的", 0, NAVY),
        ("证件、鞋子 —— F1 = 100%", 1, GREEN),
        ("包袋、相机、衣物 —— F1 ≈ 80%", 1, GREEN),
        ("还不太行的", 0, NAVY),
        ("常用药品（体积小、外观相似，最难）", 1, RED),
        ("充电器、雨伞、内衣袜", 1, RED),
    ]
    bullets(s, left_items, top=Inches(1.95), width=Inches(5.7), size=16)
    tb = s.shapes.add_textbox(Inches(6.9), Inches(1.95), Inches(5.68), Inches(3.0))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, t in enumerate(["8 项在现有图片里一次都没出现", "（手机、钱包、银行卡、钥匙、防晒、门票等）",
                           "这不代表模型不行 —— 是这批照片里本来就没有这些东西",
                           "等真实行李照多了会自然覆盖到"]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run()
        r.text = t
        _set_font(r, 15 if i < 2 else 13, NAVY if i < 2 else GRAY, bold=(i < 2))
        p.space_after = Pt(8)
    box(s, LEFT, Inches(5.5), CONTENT_W, Inches(1.0), BG_SOFT,
        "整体判断：模型目前偏保守 —— 误报少了，但「该带的没认出来」还偏多（召回率 45.3%）", 15, AMBER, True)
    note(s, "具体分析一下强弱项。\n"
            "认得最好的是证件和鞋子，F1 是满分；包袋、相机、衣物在百分之八十左右。\n"
            "比较弱的是常用药品，因为它体积小、外观又都很像，是最难的一类；"
            "还有充电器、雨伞、内衣袜。\n"
            "另外有 8 项，比如手机、钱包、银行卡、钥匙这些，在这批图片里一次都没出现过。"
            "这里要说明一下：这不代表模型认不出它们，是这批照片里本来就没有这些东西，"
            "等以后真实行李照多了会自然覆盖到。\n"
            "整体的判断是：模型现在偏保守，误报确实少了，但『该带的东西没认出来』这种情况还偏多，"
            "也就是召回率只有 45%。")

    # ============ 13 踩过的坑 ============
    s = blank(prs)
    page_frame(s, "十二、踩过的坑（也是能跑通的原因）")
    data = [
        ["问题", "症状", "解决办法"],
        ["显存打满", "训练时整机卡死，进程被杀", "图片压到 512、开启显存扩展、训练前关浏览器"],
        ["下载模型报 401", "CAS Client Error", "HF 镜像不支持 Xet 协议，加参数禁用"],
        ["参数不支持", "transformers 5.x 取消了 warmup_ratio", "改用 warmup_steps"],
        ["解释器路径", "提示 python.exe 不是内部命令", "conda 的 python 在环境根目录，不在 Scripts 下"],
    ]
    table(s, data, LEFT, Inches(1.95), CONTENT_W, Inches(2.6),
          col_widths=[Inches(2.1), Inches(4.3), Inches(5.43)], font_size=13)
    box(s, LEFT, Inches(4.85), CONTENT_W, Inches(0.85), BG_SOFT,
        "最严重的是显存问题：8GB 显存被训练占满到 7852/8188 MB，整机直接卡死", 15, RED, True)
    bullets(s, [("经验：跑训练前先关掉浏览器和标注平台，把显存腾出来", 0, GRAY)],
            top=Inches(5.85), size=15)
    note(s, "这一页列一下踩过的坑，因为项目能跑通主要就是把这些解决了。\n"
            "最严重的是显存问题：8G 显存被训练占满到 7852 兆，几乎顶到上限，"
            "整机直接卡死，我中途有一次训练就是在第 5 步的时候被系统杀掉的。"
            "后来把图片压到 512 像素、开了显存扩展的参数，才跑顺。"
            "经验是跑训练之前先把浏览器和标注平台关掉，把显存腾出来。\n"
            "剩下几个：下载模型报 401，是因为 HF 镜像不支持 Xet 协议，加个参数禁用就行；"
            "transformers 5 这个版本把 warmup_ratio 参数取消了，得改成 warmup_steps；"
            "还有 conda 的路径，python.exe 是在环境根目录，不是 Scripts 目录下，这个很容易写错。")

    # ============ 14 还差什么 ============
    s = blank(prs)
    page_frame(s, "十三、还差什么 / 下一步")
    bullets(s, [
        ("最大瓶颈：数据只有 11 张（一般建议 50~150 张）", 0, RED),
        "数据少 → 模型只能在「太乐观」和「太保守」之间来回摆，调参已经到极限",
        "下一步：用标注平台多传真实行李照，标完再训一轮",
        "项目已经传到 GitHub（私有仓库），同学可以一起标、一起训",
        "训练产物 148MB 会通过 GitHub Releases 分享，同学下载就能直接用",
    ])
    stats(s, Inches(5.2), [("11 张", "现在"), ("50~150 张", "目标"), ("52.3%", "当前 F1")])
    note(s, "最后说说还差什么。\n"
            "最大的瓶颈还是数据量，现在只有 11 张，一般建议是 50 到 150 张。\n"
            "数据少会有什么后果呢？就是模型只能在『太乐观』和『太保守』之间来回摆："
            "你往乐观调，它就乱报；往保守调，它就漏判。这个我已经试过了，靠调参数是到极限的。"
            "所以要治本，还是得把数据量提上去。\n"
            "下一步就是用标注平台多传一些真实的行李照片，标完再训一轮。\n"
            "项目我已经传到 GitHub 上了，设的是私有仓库，同学可以一起参与标注和训练。"
            "训练产物那 148MB 的适配器会走 GitHub Releases 分享，同学下载下来直接就能用，"
            "不用自己重新训。")

    # ============ 15 总结 ============
    s = blank(prs)
    page_frame(s, "总结")
    bullets(s, [
        "做通了一条完整链路：数据 → 预标 → 人工修正 → 归类整理 → 训练 → 验证",
        "消费级显卡（RTX 4060 8GB）就能完成 VLM 的微调，门槛不高",
        "最关键的改进不是换模型、也不是调参，而是把被丢掉的 55% 标注数据救回来",
        "目前水平：逐物准确率 82.8%，F1 52.3%，证件和鞋子达到满分",
        "下一步：把数据从 11 张扩到 50~150 张",
    ], size=17)
    box(s, LEFT, Inches(5.6), CONTENT_W, Inches(0.9), BG_OK,
        "一句话心得：效果不好的时候，先检查数据有没有被正确用上，再去怀疑模型", 17, GREEN, True)
    note(s, "总结一下。\n"
            "我们做通了一条完整的链路：从数据准备、机器预标、人工修正、归类整理，到训练和验证，"
            "全部跑通了。\n"
            "技术上想说明的一点是，视觉语言模型的微调其实门槛不高，"
            "一张普通的 RTX 4060、8G 显存的显卡就能做，不一定要服务器。\n"
            "这次最关键的改进，不是换模型，也不是调参数，"
            "而是发现并救回了那些被程序悄悄丢掉的、占了一半以上的标注数据。\n"
            "目前的水平是逐物准确率 82.8%，F1 52.3%，证件和鞋子这两项是满分。\n"
            "下一步就是把数据从 11 张扩到 50 到 150 张。\n"
            "最后一句话心得，也是这次最大的收获：效果不好的时候，"
            "先去检查数据有没有被正确用上，然后再去怀疑模型。\n"
            "我的汇报到这里，谢谢老师。")

    prs.save(OUT)
    print(f"✅ 已生成: {OUT}")
    print(f"   共 {len(prs.slides.__iter__.__self__._sldIdLst)} 页")


if __name__ == "__main__":
    main()
