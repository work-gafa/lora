# -*- coding: utf-8 -*-
"""以【用户手标版 train.jsonl】为准：
1) 备份当前 train.jsonl（手标 23 项原版）
2) 生成新 train.jsonl：删除「转换插头」项 -> 22 项（与 taxonomy.json 对齐）
3) 修复 manual_annotations.json：小红书参考10 恢复为空、移除未手标的 小红书参考4
"""
import json, os, shutil, datetime

BASE = r'D:\100001\homework\3.A\ai工作流\workbody\luggage-agent'
LAB = os.path.join(BASE, 'data', 'labeled')
BK = os.path.join(LAB, '_backup')
os.makedirs(BK, exist_ok=True)

# ---- 1. 备份手标原版 ----
shutil.copy(os.path.join(LAB, 'train.jsonl'), os.path.join(BK, 'train.manual23.jsonl'))
print('已备份手标原版 -> _backup/train.manual23.jsonl')

# ---- 2. 生成 22 项 train.jsonl ----
tax = json.load(open(os.path.join(BASE, 'taxonomy.json'), encoding='utf-8'))
CANON = [it['name'] for it in tax['items']]
DROP = {'转换插头'}

rows = []
for line in open(os.path.join(LAB, 'train.jsonl'), encoding='utf-8'):
    rec = json.loads(line)
    ans = rec['answer']
    if isinstance(ans, str):
        ans = json.loads(ans)
    # 过滤掉已废弃项，并按当前清单顺序重排
    by = {a['name']: a for a in ans}
    new_ans = [by[n] for n in CANON if n in by]
    rec['answer'] = json.dumps(new_ans, ensure_ascii=False)
    rows.append(rec)

with open(os.path.join(LAB, 'train.jsonl'), 'w', encoding='utf-8') as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

pos = sum(1 for r in rows for a in json.loads(r['answer']) if a['present'])
print(f'新 train.jsonl: {len(rows)} 行, {pos} positive, schema={len(CANON)} 项')
print('  含转换插头:', '转换插头' in [a['name'] for a in json.loads(rows[0]['answer'])])

# ---- 3. 修复 manual_annotations.json ----
MA = os.path.join(LAB, 'manual_annotations.json')
shutil.copy(MA, os.path.join(BK, 'manual_annotations.polluted.json'))
a = json.load(open(MA, encoding='utf-8'))

changed = []
if '小红书参考10.jpg' in a and len(a['小红书参考10.jpg']) > 0:
    a['小红书参考10.jpg'] = []          # 手标时为空，清掉 AI 填充
    changed.append('小红书参考10.jpg(清空AI框)')
if '小红书参考4.jpg' in a:
    del a['小红书参考4.jpg']            # 未手标的新上传图，移出标注集
    changed.append('小红书参考4.jpg(移除未手标图)')

json.dump(a, open(MA, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('已修复 manual_annotations.json:', changed if changed else '无需改动')
print('  现存图片数:', len(a), '| 总框数:', sum(len(v) for v in a.values()))
