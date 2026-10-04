# -*- coding: utf-8 -*-
"""生成'清单对照分析'：原清单 vs 实测需求，给出 缺少 / 不必要 / 新增 的判断依据。"""
import json, os, sys, collections

BASE = r'D:\100001\homework\3.A\ai工作流\workbody\luggage-agent'
sys.path.insert(0, BASE)
from normalize import CANON, CATEGORY, normalize_name

LAB = os.path.join(BASE, 'data', 'labeled')
anno = json.load(open(os.path.join(LAB, 'manual_annotations.json'), encoding='utf-8'))

# 统计：每个规范大类被手标多少次、出现在多少张图
cnt = collections.Counter()
img_cnt = collections.Counter()
for img, boxes in anno.items():
    seen = set()
    for b in boxes:
        c = normalize_name((b.get('name') or '').strip())
        if c:
            cnt[c] += 1
            seen.add(c)
    for c in seen:
        img_cnt[c] += 1

OLD = ["身份证","手机","充电器","充电宝","耳机","相机","钱包/现金","银行卡","钥匙","衣物",
       "内衣袜","洗漱用品","护肤品","防晒","常用药品","口罩","湿巾","雨伞","水杯",
       "护照(出境)","门票/订单","零食","转换插头"]

print("原清单 %d 项，新清单 %d 项\n" % (len(OLD), len(CANON)))
print("=== 新清单各项实测热度（手标框数 / 出现图数）===")
for c in CANON:
    print(f"  [{CATEGORY.get(c,'?'):5s}] {c:8s}  框数={cnt.get(c,0):2d}  图数={img_cnt.get(c,0):2d}")
print()
print("=== 原清单里、实测 0 次出现的项（考虑移除/降权）===")
for c in OLD:
    n = normalize_name(c)
    if n is None:
        n = c
    if cnt.get(n, 0) == 0:
        print(f"  {c}（归为 {n}）-> 实测 0 框")
print()
print("=== 实测出现、原清单没有的类（缺失项）===")
for c in CANON:
    if c not in [normalize_name(o) or o for o in OLD] and cnt.get(c, 0) > 0:
        print(f"  {c}（{CATEGORY.get(c)}）-> {cnt[c]} 框 / {img_cnt[c]} 图")

# 输出 JSON 供后续用
out = {"canon": CANON, "category": CATEGORY,
       "count": dict(cnt), "images": dict(img_cnt),
       "old_list": OLD}
json.dump(out, open(os.path.join(LAB, '_taxonomy_analysis.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)
print("\n✅ 已写 data/labeled/_taxonomy_analysis.json")
