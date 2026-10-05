# -*- coding: utf-8 -*-
"""给 taxonomy.json 的每一项加 scenarios 标签（travel / school）。

分配原则（用户可在平台上任意改）：
  - 旅行专属：只有出门旅游才会带的（门票、相机、防晒、洗漱护肤、衣物鞋帽…）
  - 上学专属：只有上学/书桌场景才有的（课本、笔记本、文具、文件资料）
  - 通用：两个场景都可能用到（证件、手机、充电器、水杯、雨伞、钥匙…）
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TAX = BASE / "taxonomy.json"

TRAVEL_ONLY = {"门票/订单", "相机", "防晒", "洗漱用品", "护肤品",
               "梳妆饰品", "衣物", "内衣袜", "鞋子", "帽子", "娱乐用品"}

SCHOOL_ONLY = {"课本教材", "笔记本作业本", "文具", "文件资料"}

SCENARIOS = {
    "travel": "出门旅行 / 旅游",
    "school": "上学 / 回家",
}


def main():
    shutil.copy2(TAX, BASE / "data" / "labeled" / "_backup" /
                 f"taxonomy.before-scenarios.{datetime.now():%Y%m%d-%H%M%S}.json")

    data = json.loads(TAX.read_text(encoding="utf-8"))
    data["scenarios"] = SCENARIOS
    data["_comment"] = (
        "出行必备物品清单（单一数据源）。\n"
        "每项 scenarios 标明它属于哪些场景：用户在平台上选「旅行」就只检查 travel 项，"
        "选「上学」就只检查 school 项，两个都有则都检查。\n"
        "训练与推理共用本文件 + prompt.py 生成的指令，改这里全链路生效。"
    )

    counts = {"travel": 0, "school": 0}
    unknown = []
    for it in data["items"]:
        name = it["name"]
        if name in SCHOOL_ONLY:
            it["scenarios"] = ["school"]
        elif name in TRAVEL_ONLY:
            it["scenarios"] = ["travel"]
        elif name:
            it["scenarios"] = ["travel", "school"]
        else:
            unknown.append(name)
        for s in it["scenarios"]:
            counts[s] += 1

    TAX.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("✅ 已写入 scenarios")
    print(f"   旅行场景 {counts['travel']} 项 | 上学场景 {counts['school']} 项")
    print()
    print("   【旅行专属】:", "、".join(sorted(TRAVEL_ONLY)))
    print("   【上学专属】:", "、".join(sorted(SCHOOL_ONLY)))
    print("   【两场景通用】:", "、".join(sorted(
        i["name"] for i in data["items"]
        if i["name"] not in TRAVEL_ONLY and i["name"] not in SCHOOL_ONLY)))
    if unknown:
        print("   ⚠️ 未分类:", unknown)


if __name__ == "__main__":
    main()
