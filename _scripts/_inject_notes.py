#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 slides/*.slide 里的 <Slide notes={...}> 讲稿注入到生成的 .pptx。

背景：本机 slidep 引擎（0.4.4-alpha）的 SpeakerNotes.setText 是空实现
（其源码注释：「slide_add_notes 在缺 notes master theme 时报 [13096]，
slide_set_notes_text silent fail」），所以 <Slide notes> 不会进 pptx。
本脚本在页面定稿后补写讲稿。

另外，slidep 产出的 notesMaster 的 spTree 是空的（没有正文占位符），
导致 python-pptx 的 notes_text_frame 为 None，PowerPoint 也不会在
备注窗格里显示内容。所以这里同时给 notesMaster 补一个 body 占位符，
再把每页讲稿写成引用了该占位符的 <p:sp>。

用法：
    python _scripts/_inject_notes.py --dir _ppt_workspace \
        --pptx 行李提醒Agent_汇报.pptx

注意：**必须在页面定稿、引擎停止后运行**；引擎若再次编译会覆盖讲稿。
"""
import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

from lxml import etree

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"

NOTES_MASTER = "ppt/notesMasters/notesMaster1.xml"

# notesMaster 里补的正文占位符（idx=1 是备注正文的标准编号）
MASTER_BODY_PH = (
    f'<p:sp xmlns:p="{P}" xmlns:a="{A}">'
    "<p:nvSpPr>"
    '<p:cNvPr id="2" name="Notes Placeholder 1"/>'
    '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
    '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr>'
    "</p:nvSpPr>"
    "<p:spPr>"
    '<a:xfrm><a:off x="685800" y="685800"/>'
    '<a:ext cx="9601200" cy="4800600"/></a:xfrm>'
    '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
    "</p:spPr>"
    "<p:txBody>"
    '<a:bodyPr wrap="square"><a:normAutofit/></a:bodyPr>'
    "<a:lstStyle/><a:p/>"
    "</p:txBody>"
    "</p:sp>"
)

SHAPE_ID = 9001


def extract_notes(slide_file: Path):
    """从 .slide 源码中取出 notes={...} 模板字符串的正文。"""
    src = slide_file.read_text(encoding="utf-8")
    m = re.search(r"notes\s*=\s*\{\s*`(.*?)`\s*\}", src, re.S)
    if not m:
        return None
    body = m.group(1)
    body = body.replace("\\`", "`").replace("\\$", "$")
    body = body.replace("\\n", "\n").replace("\\r", "")
    return body.strip()


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def notes_sp(text: str) -> str:
    """构造带备注正文占位符的 <p:sp>。"""
    paras = []
    for line in text.split("\n"):
        if line.strip():
            paras.append(
                '<a:p><a:r><a:rPr lang="zh-CN" sz="1200" dirty="0"/>'
                f"<a:t>{_esc(line)}</a:t></a:r></a:p>"
            )
        else:
            paras.append("<a:p/>")
    return (
        f'<p:sp xmlns:p="{P}" xmlns:a="{A}">'
        "<p:nvSpPr>"
        f'<p:cNvPr id="{SHAPE_ID}" name="Speaker Notes"/>'
        "<p:cNvSpPr/>"
        '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr>'
        "</p:nvSpPr>"
        "<p:spPr/>"
        "<p:txBody>"
        '<a:bodyPr wrap="square"><a:normAutofit/></a:bodyPr>'
        "<a:lstStyle/>" + "".join(paras) +
        "</p:txBody>"
        "</p:sp>"
    )


def patch_master(xml: bytes) -> bytes:
    """往 notesMaster 的空 spTree 里补一个 body 占位符。"""
    root = etree.fromstring(xml)
    tree = root.find(f"{{{P}}}cSld/{{{P}}}spTree")
    if tree is None:
        raise RuntimeError("notesMaster 里找不到 spTree")
    if tree.findall(f"{{{P}}}sp"):
        return xml  # 已有占位符，不重复加
    tree.append(etree.fromstring(MASTER_BODY_PH))
    return etree.tostring(root, xml_declaration=True,
                          encoding="UTF-8", standalone=True)


def patch_notes_slide(xml: bytes, text: str) -> bytes:
    root = etree.fromstring(xml)
    tree = root.find(f"{{{P}}}cSld/{{{P}}}spTree")
    if tree is None:
        raise RuntimeError("notesSlide 里找不到 spTree")

    for sp in tree.findall(f"{{{P}}}sp"):          # 清掉旧注入
        nv = sp.find(f"{{{P}}}nvSpPr/{{{P}}}cNvPr")
        if nv is not None and nv.get("id") == str(SHAPE_ID):
            tree.remove(sp)

    tree.append(etree.fromstring(notes_sp(text)))
    return etree.tostring(root, xml_declaration=True,
                          encoding="UTF-8", standalone=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="PPT 工作区目录")
    ap.add_argument("--pptx", required=True, help="pptx 文件名（相对 --dir）")
    args = ap.parse_args()

    root = Path(args.dir).resolve()
    pptx_path = root / args.pptx
    slides_dir = root / "slides"

    if not pptx_path.is_file():
        sys.exit(f"找不到 pptx: {pptx_path}")
    if not slides_dir.is_dir():
        sys.exit(f"找不到 slides 目录: {slides_dir}")

    pages = sorted(slides_dir.glob("*.slide"), key=lambda p: p.stem)
    src = zipfile.ZipFile(pptx_path)
    items = src.infolist()
    payload = {i.filename: src.read(i.filename) for i in items}
    src.close()

    if NOTES_MASTER in payload:
        payload[NOTES_MASTER] = patch_master(payload[NOTES_MASTER])

    # notesSlideN.xml 的 N 与 slideN.xml 的 N 一一对应
    written, skipped = 0, []
    for idx, page in enumerate(pages, start=1):
        name = f"ppt/notesSlides/notesSlide{idx}.xml"
        if name not in payload:
            skipped.append(f"{page.name}(无notes页)")
            continue
        text = extract_notes(page)
        if not text:
            skipped.append(page.name)
            continue
        payload[name] = patch_notes_slide(payload[name], text)
        written += 1

    tmp = pptx_path.with_suffix(".pptx.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
        for i in items:
            out.writestr(i, payload[i.filename])
    shutil.move(str(tmp), str(pptx_path))

    print(f"✅ 已注入讲稿：{written} / {len(pages)} 页")
    if skipped:
        print(f"   跳过：{', '.join(skipped)}")


if __name__ == "__main__":
    main()
