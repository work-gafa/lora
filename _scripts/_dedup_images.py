# -*- coding: utf-8 -*-
"""清理重复上传的图片。

发现（MD5 完全相同）：
  组1: 小红书参考2.jpg / 小红书参考2_1.jpg / 小红书参考2_2.jpg  (都 0 框)
  组2: 小红书参考4.jpg(0 框) / 小红书参考4_1.jpg(14 框 ← 用户的成果在这里)

处理：
  1. 把 参考4_1 的 14 个框并到 参考4.jpg（保留规范名）
  2. 删掉 参考4_1、参考2_1、参考2_2（走平台删除接口，文件进 _trash 可找回）
"""
import json
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8004"


def call(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def enc(n):
    return urllib.parse.quote(n)


MAIN, DUP = "小红书参考4.jpg", "小红书参考4_1.jpg"

imgs = get("/api/images")
annos = imgs["annotations"]

boxes_dup = annos.get(DUP, [])
boxes_main = annos.get(MAIN, [])
print("处理前：")
print("  %s  -> %d 框" % (MAIN, len(boxes_main)))
print("  %s  -> %d 框" % (DUP, len(boxes_dup)))

# 1) 把副本上的框并到规范名（仅当主文件为空，避免覆盖）
if boxes_dup and not boxes_main:
    call("PUT", "/api/annotations", {"annotations": {MAIN: boxes_dup}})
    after = get("/api/images")["annotations"]
    print("\n已把 %d 个框并到 %s（现在是 %d 框）" % (len(boxes_dup), MAIN, len(after.get(MAIN, []))))
elif boxes_dup and boxes_main:
    print("\n⚠️ 两边都有框，未自动合并，请人工确认")
else:
    print("\n主文件已有框或副本为空，跳过合并")

# 2) 删除重复图
print("\n删除重复：")
for name in (DUP, "小红书参考2_1.jpg", "小红书参考2_2.jpg"):
    try:
        d = call("DELETE", "/api/images/" + enc(name))
        print("  ✅ %-22s 删掉 %d 个框 -> %s" % (name, d["removed_boxes"],
                                              d["moved_to"].split("\\")[-1]))
    except Exception as e:
        print("  ❌ %-22s %s" % (name, e))

# 3) 收尾核对
final = get("/api/images")
print("\n处理后：共 %d 张图 / %d 框" % (len(final["images"]),
                                      sum(len(v) for v in final["annotations"].values())))
for i in final["images"]:
    if "参考2" in i["name"] or "参考4" in i["name"]:
        print("  %-22s %d 框  场景=%s" % (i["name"], i["boxes"], i.get("scenario")))
