# -*- coding: utf-8 -*-
"""对比：手标版(train.jsonl) vs 网页现版(manual_annotations.json 归并)"""
import json, os

BASE = r'D:\100001\homework\3.A\ai工作流\workbody\luggage-agent'
MERGE = {"伞": "雨伞", "雨伞 ": "雨伞", "充电线": "充电器", "充电器线": "充电器",
         "面膜": "护肤品", "护肤": "护肤品", "护肤品 ": "护肤品", "纸巾": "湿巾",
         "湿纸巾": "湿巾", "洗漱包": "洗漱用品", "防晒霜": "防晒", "防晒喷雾": "防晒",
         "药": "常用药品", "药品": "常用药品"}

tax = json.load(open(os.path.join(BASE, 'taxonomy.json'), encoding='utf-8'))
CANON = [it['name'] for it in tax['items']]
print('=== 当前清单 taxonomy.json ===')
print('项数:', len(CANON), '| 含"转换插头":', '转换插头' in CANON)
print('清单:', '、'.join(CANON))
print()

train = {}
for line in open(os.path.join(BASE, 'data', 'labeled', 'train.jsonl'), encoding='utf-8'):
    rec = json.loads(line)
    img = rec['image'].replace('\\', '/').split('/')[-1]
    ans = rec['answer']
    if isinstance(ans, str):
        ans = json.loads(ans)
    train[img] = set(a['name'] for a in ans if a.get('present'))

manual = json.load(open(os.path.join(BASE, 'data', 'labeled', 'manual_annotations.json'), encoding='utf-8'))

def manual_present(img):
    boxes = manual.get(img)
    if boxes is None:
        return None, None
    s = set()
    for b in boxes:
        nm = (b.get('name') or '').strip()
        nm = MERGE.get(nm, nm)
        if nm in CANON:
            s.add(nm)
    return s, len(boxes)

print('=== 逐图对比 ===')
print('手标 = train.jsonl(18:03 导出)；网页 = manual_annotations.json(21:02) 归并后')
print()
imgs = sorted(set(list(train.keys()) + list(manual.keys())))
for img in imgs:
    tp = train.get(img)
    mp, nbox = manual_present(img)
    t_str = '—（不在训练集）' if tp is None else ('、'.join(sorted(tp)) if tp else '（无清单项）')
    if mp is None:
        m_str = '—（网页无此图）'
    else:
        m_str = ('、'.join(sorted(mp)) if mp else '（无清单项）') + f'  [共{nbox}框]'
    if tp is None:
        flag = '※ 仅网页有(新上传)'
    elif mp is None:
        flag = '※ 仅训练集有'
    elif tp == mp:
        flag = 'OK 一致'
    else:
        flag = '>>> 不一致 <<<'
    print(f'[{flag}]')
    print(f'   {img}')
    print(f'     手标: {t_str}')
    print(f'     网页: {m_str}')
print()

extra = [k for k in manual if k not in train]
miss = [k for k in train if k not in manual]
print('网页多出、训练集没有的图:', extra if extra else '无')
print('训练集有、网页没有的图:', miss if miss else '无')
