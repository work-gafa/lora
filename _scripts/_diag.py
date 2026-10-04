# -*- coding: utf-8 -*-
"""诊断：手标的 100 个框里，有多少因"名称不在清单"而被导出时丢弃？"""
import json, collections, os

BASE = r'D:\100001\homework\3.A\ai工作流\workbody\luggage-agent'
tax = json.load(open(os.path.join(BASE, 'taxonomy.json'), encoding='utf-8'))
CANON = [it['name'] for it in tax['items']]
MERGE = {"伞": "雨伞", "雨伞 ": "雨伞", "充电线": "充电器", "充电器线": "充电器",
         "面膜": "护肤品", "护肤": "护肤品", "护肤品 ": "护肤品", "纸巾": "湿巾",
         "湿纸巾": "湿巾", "洗漱包": "洗漱用品", "防晒霜": "防晒", "防晒喷雾": "防晒",
         "药": "常用药品", "药品": "常用药品"}

a = json.load(open(os.path.join(BASE, 'data', 'labeled', 'manual_annotations.json'), encoding='utf-8'))
kept = collections.Counter()
dropped = collections.Counter()
for img, boxes in a.items():
    for b in boxes:
        nm = (b.get('name') or '').strip()
        m = MERGE.get(nm, nm)
        if m in CANON:
            kept[m] += 1
        else:
            dropped[nm] += 1

print('=== 手标框总数 ===', sum(kept.values()) + sum(dropped.values()))
print(f'=== 归入清单保留: {sum(kept.values())} 个 ===')
for k, v in kept.most_common():
    print(f'   {k} x{v}')
print(f'\n=== 因名称不在清单被丢弃: {sum(dropped.values())} 个（{len(dropped)} 种）===')
for k, v in dropped.most_common():
    print(f'   {k} x{v}')
print(f'\n>> 丢弃率: {sum(dropped.values())/(sum(kept.values())+sum(dropped.values()))*100:.0f}%')
