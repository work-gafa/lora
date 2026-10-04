# -*- coding: utf-8 -*-
"""用新的 normalize 归类模块重导 train.jsonl：
把用户手标 manual_annotations.json 里的细名（收纳包/书包/鞋子…）归到规范大类，
算"救回率"，并按新清单 26 项生成训练数据。"""
import json, os, sys, collections

BASE = r'D:\100001\homework\3.A\ai工作流\workbody\luggage-agent'
sys.path.insert(0, BASE)
from normalize import CANON, normalize_name, CATEGORY

LAB = os.path.join(BASE, 'data', 'labeled')
anno = json.load(open(os.path.join(LAB, 'manual_annotations.json'), encoding='utf-8'))

# 图片 -> 相对路径（预设图 raw/reference_wuzi，上传图 labeled/uploads）
RAW_DIR = os.path.join(BASE, 'data', 'raw', 'reference_wuzi')
UP_DIR = os.path.join(BASE, 'data', 'labeled', 'uploads')

def rel_path(img):
    if os.path.exists(os.path.join(RAW_DIR, img)):
        return 'raw/reference_wuzi/' + img
    if os.path.exists(os.path.join(UP_DIR, img)):
        return 'labeled/uploads/' + img
    return None

INSTR = None
# 复用统一提示词
from prompt import build_prompt
INSTR = build_prompt(CANON)

kept, dropped = collections.Counter(), collections.Counter()
rows = []
for img, boxes in anno.items():
    rel = rel_path(img)
    if rel is None:
        continue
    present = {}
    for b in boxes:
        raw = (b.get('name') or '').strip()
        canon = normalize_name(raw)
        if canon is None:
            dropped[raw] += 1
            continue
        kept[canon] += 1
        # 同一大类取第一个框的位置
        if canon not in present:
            present[canon] = b.get('bbox')  # 归一化坐标，暂存
    answer = []
    for it in CANON:
        if it in present:
            answer.append({"name": it, "present": True, "location": "画面中"})
        else:
            answer.append({"name": it, "present": False, "location": None})
    rows.append({"image": rel, "instruction": INSTR,
                 "answer": json.dumps(answer, ensure_ascii=False)})

with open(os.path.join(LAB, 'train.jsonl'), 'w', encoding='utf-8') as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

pos = sum(1 for r in rows for a in json.loads(r['answer']) if a['present'])
tot = sum(kept.values()) + sum(dropped.values())
print(f'重导完成：{len(rows)} 张图，{pos} positive，清单 {len(CANON)} 项')
print(f'框归类：保留 {sum(kept.values())} / 丢弃 {sum(dropped.values())}（总 {tot}）'
      f' → 救回率 {sum(kept.values())/tot*100:.0f}%')
if dropped:
    print('仍丢弃的：', dict(dropped))
print()
print('--- 归入各大类的框数 ---')
for k, v in kept.most_common():
    print(f'   [{CATEGORY.get(k,"?"):5s}] {k}: {v}')
print()
print('--- 每图 positive 数 ---')
for r in rows:
    ans = json.loads(r['answer'])
    names = [a['name'] for a in ans if a['present']]
    print(f'   {r["image"]}: {len(names)} -> {names}')
