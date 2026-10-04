"""
luggage-agent/normalize.py
==================================================
【统一归类模块】把「手写细名 / 模型自由命名」归并到规范大类。

设计要点：
  1. 单一来源：类别与别名都来自项目根 taxonomy.json，不再各处硬编码 MERGE。
  2. 三步匹配（由严到松）：
     a) 精确命中规范名
     b) 精确命中某别名
     c) 剥离"颜色/图案/材质+的"等修饰前缀后，再匹配规范名/别名
        （治模型的"蓝色相机""粉红色眼镜盒""Hello Kitty图案的内袋"）
  3. 兜底：仍不中 → 返回 None（视为清单外噪声，调用方决定丢弃还是记录）。

用法：
    from normalize import normalize_name, CANON, CATEGORY
    canon = normalize_name("双肩包")   # -> "包袋"
    canon = normalize_name("蓝色相机")  # -> "相机"
    canon = normalize_name("Hello Kitty图案的内袋")  # -> None
"""
import json
import re
from pathlib import Path

_TAX_FILE = Path(__file__).resolve().parent / "taxonomy.json"


def _load():
    data = json.loads(_TAX_FILE.read_text(encoding="utf-8"))
    items = data["items"]
    canon = [it["name"] for it in items]
    aliases = {}      # 别名 -> 规范名
    en = {}           # 规范名 -> 英文提示词
    category = {}     # 规范名 -> 类别
    for it in items:
        name = it["name"]
        en[name] = it.get("en", name)
        category[name] = it.get("category", "其他")
        for a in it.get("aliases", []):
            aliases[str(a).strip()] = name
        # 规范名本身也算别名，方便统一查找
        aliases.setdefault(name, name)
    return canon, aliases, en, category


CANON, _ALIAS, EN, CATEGORY = _load()
# 反查：英文提示词(小写) -> 规范名（给 GroundingDINO 用）
EN2CANON = {v.lower(): k for k, v in EN.items()}

# 需要剥离的修饰前缀（颜色/图案/材质/尺寸），治"蓝色相机""26寸行李箱"
_MOD_PREFIX = re.compile(
    r"^(一个|一只|一件|两个|几个|"
    r"[红橙黄绿青蓝紫粉黑白灰金银棕褐米驼彩]色的?|"
    r"粉红色?|粉?红色?|蓝[色]?|白色?|黑色?|绿色?|红色?|黄色?|橙色?|紫色?|灰色?|金色?|银色?|"
    r"透明|磨砂|网格|网状|条纹|格子|碎花|卡通|可爱|"
    r"\d+\s*(寸|英寸|cm|厘米|L|升)|大|小|中|"
    r"[A-Za-z ]+图案的?|"
    r")+"
)
# 尾部修饰词（如 "…包/…袋/…盒/…用品" 已被别名覆盖，这里兜底去除）
_TAIL = re.compile(r"(盒|袋|包|瓶|罐|器|套|片|条|个)$")


def _match(s):
    """在规范名/别名里查（精确）。"""
    if s in _ALIAS:
        return _ALIAS[s]
    return None


def normalize_name(raw):
    """把任意细名归并到规范大类；无匹配返回 None。"""
    if not raw:
        return None
    s = str(raw).strip().strip("。.，,；;：:、!！?？\"'（）()[]【】")
    if not s:
        return None

    # a/b) 精确匹配规范名或别名
    hit = _match(s)
    if hit:
        return hit

    # 去掉内部空白再试
    s2 = re.sub(r"\s+", "", s)
    hit = _match(s2)
    if hit:
        return hit

    # c) 剥离修饰前缀
    s3 = _MOD_PREFIX.sub("", s2)
    hit = _match(s3)
    if hit:
        return hit

    # 再剥离尾部量词/单位后匹配
    s4 = _TAIL.sub("", s3)
    hit = _match(s4)
    if hit:
        return hit

    # 最后：子串包含（别名出现在长名里，如 "Hello Kitty图案的内袋" 含 "内袋"）
    for alias, canon in _ALIAS.items():
        if len(alias) >= 2 and alias in s2:
            return canon

    return None


def normalize_boxes(boxes):
    """把 [{name, ...}] 归类；丢弃无法归类的。返回 (结果列表, 被丢弃名字列表)。"""
    out, dropped = [], []
    for b in boxes:
        canon = normalize_name(b.get("name"))
        if canon is None:
            dropped.append(b.get("name"))
            continue
        nb = dict(b)
        nb["name"] = canon
        out.append(nb)
    return out, dropped


if __name__ == "__main__":
    tests = ["双肩包", "26寸行李箱", "蓝色相机", "粉红色眼镜盒", "绿色发圈",
             "Hello Kitty图案的内袋", "白色鱼形收纳袋", "证件包", "一次性用品",
             "衣服", "化妆品", "洗护包", "电子产品", "网状收纳袋", "米色梳子",
             "收纳包", "书包", "拖鞋", "梳子", "卫生巾", "排插", "红色钱包"]
    print(f"清单 {len(CANON)} 大类：", "、".join(CANON))
    print()
    for t in tests:
        print(f"  {t:24s} -> {normalize_name(t)}")
