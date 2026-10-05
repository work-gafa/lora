# -*- coding: utf-8 -*-
"""1) 给清单补「学习 / 书桌」类物品  2) 对补充图批量跑 AI 预标注。

通过平台接口操作，改完服务端立即热刷新（normalize + GroundingDINO 提示词）。
"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8004"
LA = Path(r"D:\100001\homework\3.A\ai工作流\workbody\luggage-agent")


def call(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------- 1. 清单补学习/书桌类 ----------------
print("=== 1) 扩充清单 ===")

# 1a. 娱乐用品释放「笔记本 / 本子」（它们要归到学习用品）
call("PUT", "/api/taxonomy/items/" + urllib.parse.quote("娱乐用品"), {
    "name": "娱乐用品", "en": "toy doll", "category": "其他",
    "aliases": ["玩具", "玩偶", "娃娃", "公仔", "扑克牌", "手办"],
})

# 1b. 证件补学生证类
call("PUT", "/api/taxonomy/items/" + urllib.parse.quote("证件"), {
    "name": "证件", "en": "ID card passport", "category": "证件钱财",
    "aliases": ["身份证", "护照", "驾照", "驾驶证", "身份证件", "通行证",
                "证件包", "证件袋", "护照(出境)", "学生证", "校园卡", "一卡通", "饭卡"],
})

# 1c. 便携电器补电脑外设
call("PUT", "/api/taxonomy/items/" + urllib.parse.quote("便携电器"), {
    "name": "便携电器", "en": "fan electronics", "category": "电子设备",
    "aliases": ["风扇", "小风扇", "手持风扇", "灯", "台灯", "小夜灯", "电子产品",
                "平板", "电脑", "电子书", "阅读器", "键盘", "鼠标", "显示器", "笔记本电脑"],
})

# 1d. 新增学习用品
NEW = [
    {"name": "课本教材", "en": "textbook", "category": "学习用品",
     "aliases": ["课本", "教材", "教科书", "课本教材", "专业书"]},
    {"name": "笔记本作业本", "en": "notebook", "category": "学习用品",
     "aliases": ["笔记本", "作业本", "练习本", "本子", "记事本", "草稿本"]},
    {"name": "文具", "en": "pen pencil stationery", "category": "学习用品",
     "aliases": ["笔", "铅笔", "钢笔", "圆珠笔", "中性笔", "尺子", "橡皮",
                 "文具", "文具盒", "笔袋", "修正带", "便利贴"]},
    {"name": "文件资料", "en": "folder documents", "category": "学习用品",
     "aliases": ["文件夹", "资料", "文件", "试卷", "纸张", "打印资料", "讲义"]},
]
for it in NEW:
    call("POST", "/api/taxonomy/items", it)
    print("   + 新增:", it["name"])

tax = get("/api/taxonomy")
print("   清单现有 %d 项" % len(tax["items"]))

# ---------------- 2. 批量 AI 预标注 ----------------
print()
print("=== 2) 批量 AI 预标注 ===")

imgs = get("/api/images")["images"]
targets = [i["name"] for i in imgs if i["name"].startswith("小红书补充")]
print("   待标注: %d 张" % len(targets))

annos = {}
for i, name in enumerate(targets, 1):
    try:
        d = call("POST", "/api/autodetect/" + urllib.parse.quote(name), {})
    except Exception as e:
        print("   [%2d/%d] %s  ❌ %s" % (i, len(targets), name, e))
        annos[name] = []
        continue
    W, H = d["size"]
    boxes = []
    for b in d.get("boxes", []):
        px = b["bbox_px"]
        boxes.append({
            "name": b["name"],
            "bbox": [round(px[0] / W, 4), round(px[1] / H, 4),
                     round(px[2] / W, 4), round(px[3] / H, 4)],
        })
    annos[name] = boxes
    print("   [%2d/%d] %-22s %d 框" % (i, len(targets), name, len(boxes)))

# ---------------- 3. 一次性保存（后端 merge，不影响已有标注） ----------------
print()
res = call("PUT", "/api/annotations", {"annotations": annos})
print("=== 3) 保存结果 ===")
print("   本次提交 %d 张，文件里现有 %d 张" % (res["saved"], res["total"]))

total_boxes = sum(len(v) for v in annos.values())
print("   预标总框数: %d" % total_boxes)
