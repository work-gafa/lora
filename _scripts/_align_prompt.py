# -*- coding: utf-8 -*-
"""把 train.jsonl 每行的 instruction 换成统一的 build_prompt(CANON)，
让训练与推理用完全相同的问法。"""
import json, os, sys

BASE = r'D:\100001\homework\3.A\ai工作流\workbody\luggage-agent'
sys.path.insert(0, BASE)
from prompt import build_prompt

LAB = os.path.join(BASE, 'data', 'labeled')
tax = json.load(open(os.path.join(BASE, 'taxonomy.json'), encoding='utf-8'))
CANON = [it['name'] for it in tax['items']]
INSTR = build_prompt(CANON)

p = os.path.join(LAB, 'train.jsonl')
rows = [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]
for r in rows:
    r['instruction'] = INSTR
with open(p, 'w', encoding='utf-8') as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

print('已统一 instruction，共', len(rows), '行')
print('--- instruction 预览 ---')
print(INSTR)
