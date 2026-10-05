"""
luggage-agent/infer.py
==================================================
加载「4-bit 基座 + 可选 LoRA 适配器」，识别照片里的必备物品带齐情况。

输出 JSON 结构（前端据此渲染清单）：
{
  "scenario": "travel",
  "items": [
    {"name": "身份证", "present": true,  "location": "左侧内袋"},
    {"name": "充电宝", "present": false, "location": null}
  ]
}
- present=true  → 前端：横线划掉 + 颜色变浅
- present=false → 前端：保持原样（单个可选项）

命令行运行（无适配器时跑基座零样本）：
  python infer.py --image data/raw/reference_xhs/小红书行李参考图1.png --scenario travel
  python infer.py --image data/raw/reference_xhs --scenario travel   # 整个文件夹批量
  python infer.py --image 照片.jpg --scenario school --adapter output/lora-adapter

说明：Qwen2.5-VL 必须把图片经过 process_vision_info 转成专用张量
（pixel_values + image_grid_thw）再喂给 processor，否则图像不会真正注入模型。
==================================================
"""
import argparse
import glob
import json
import os
import re

from PIL import Image
import torch
from transformers import (
    Qwen2_5_VLForConditionalGeneration,
    AutoProcessor,
    BitsAndBytesConfig,
)
from peft import PeftModel
from qwen_vl_utils import process_vision_info


# 统一提示词：从 prompt.py 引入，保证【训练与推理问法完全一致】
from prompt import build_prompt


def load_model(model_dir, adapter_dir=None):
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_type=torch.float16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        model_dir, device_map="auto", quantization_config=bnb
    )
    if adapter_dir and os.path.exists(adapter_dir):
        print(">> 加载 LoRA 适配器：", adapter_dir)
        model = PeftModel.from_pretrained(model, adapter_dir)
    else:
        print(">> 未加载适配器，使用基座零样本能力")
    processor = AutoProcessor.from_pretrained(model_dir)
    return model, processor


def infer_one(image_path, items, model, processor, max_new_tokens=768,
              scenario: str = "travel"):
    image = Image.open(image_path).convert("RGB")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": build_prompt(items, scenario)},
            ],
        }
    ]
    # 1) 把对话模板化成文本（图片位置变成 <image> 占位符）
    text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    # 2) 把 PIL 图片转成模型专用张量（这一步是关键，缺了图像就进不去）
    image_inputs, video_inputs = process_vision_info(messages)
    # 3) 一起交给 processor 编码成张量
    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        return_tensors="pt",
    ).to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens)
    # 只解码新生成的部分
    resp = processor.decode(
        out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True
    )
    return resp


def collect_images(path):
    """如果是文件夹就返回里面所有图片，否则返回单个。"""
    exts = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp")
    if os.path.isdir(path):
        files = []
        for e in exts:
            files += glob.glob(os.path.join(path, "**", e), recursive=True)
        return sorted(files)
    return [path]


def try_parse_json(raw, canon=None):
    """从模型输出里尽量抠出 JSON。

    模型返回格式并不稳定，实测存在两种：
      1) {"items": [ {...}, {...} ]}   —— 带 items 包裹
      2) [ {...}, {...} ]              —— 裸数组
    这里统一解析成「物品列表」，两种都能吃。

    传入 canon（规范清单）时，会把每项 name 归类到规范大类并去重补齐
    （治自由命名：'蓝色相机'->'相机'）。
    """
    if raw is None:
        return None
    s = raw.strip()
    # 去掉 ```json ... ``` 代码围栏
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"\s*```$", "", s).strip()

    data = None
    # 先整段直接解析
    for cand in (s, s[s.find("{"): s.rfind("}") + 1] if "{" in s else "",
                 s[s.find("["): s.rfind("]") + 1] if "[" in s else ""):
        if not cand:
            continue
        try:
            data = json.loads(cand)
            break
        except Exception:
            continue

    if data is None:
        return None
    # 归一化：带 items 包裹 → 取 items；裸数组 → 直接用
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        items = data["items"]
    elif isinstance(data, list):
        items = data
    else:
        return None

    # 归类：把模型自由命名（"蓝色相机"）并到规范大类（"相机"），并去重
    if canon:
        try:
            from normalize import normalize_name
            merged = {}
            for it in items:
                if not isinstance(it, dict):
                    continue
                c = normalize_name(it.get("name"))
                if c is None or c not in canon:
                    continue
                # 新格式只输出「看到的」物品（没有 present 字段）→ 视为 present=True；
                # 旧格式会带 present 字段 → 按它自己写的值走（向后兼容）。
                present = bool(it["present"]) if "present" in it else True
                if c not in merged:
                    merged[c] = {"name": c,
                                 "present": present,
                                 "location": it.get("location")}
                else:
                    merged[c]["present"] = merged[c]["present"] or present
                    if not merged[c]["location"] and it.get("location"):
                        merged[c]["location"] = it["location"]
            # 按清单顺序补齐缺席项为 present=false
            for name in canon:
                if name not in merged:
                    merged[name] = {"name": name, "present": False, "location": None}
            items = [merged[n] for n in canon]
        except Exception:
            pass
    return items


def load_items(taxonomy_path: str, scenario: str = "travel") -> list[str]:
    """读取清单，按场景过滤。兼容三种格式：

    1) 新格式（项目根 taxonomy.json）：items 每项带 scenarios 数组
       {"items": [{"name": ..., "scenarios": ["travel"]}, ...]}
    2) 旧格式 A（demo/taxonomy.json）：{"scenarios": {"travel": {"items": [...]}}}
    3) 旧格式 B（扁平无场景）：{"items": [{"name": ...}]} → 全部返回
    """
    with open(taxonomy_path, encoding="utf-8") as f:
        tax = json.load(f)

    # 旧格式 A：顶层 scenarios 是「场景 -> 清单」的字典
    scenarios = tax.get("scenarios")
    if isinstance(scenarios, dict) and scenarios:
        first = next(iter(scenarios.values()))
        if isinstance(first, dict) and "items" in first:
            return scenarios.get(scenario, {}).get("items", [])

    items = tax.get("items", [])
    if not items:
        return []

    # 只要有任何一项带 scenarios 字段，就按场景过滤
    if any("scenarios" in it for it in items):
        picked = [
            it["name"] for it in items
            if scenario in (it.get("scenarios") or ["travel"])
        ]
        return picked

    # 全部没有 scenarios 字段 → 视为通用清单，原样返回
    return [it["name"] for it in items]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, help="单张图片路径，或含图片的文件夹")
    ap.add_argument("--scenario", default="travel")
    ap.add_argument("--taxonomy", default="taxonomy.json", help="清单文件，默认项目根 taxonomy.json")
    ap.add_argument("--model", default="vlm/qwen2.5-vl-3b-instruct")
    ap.add_argument("--adapter", default="output/lora-adapter")
    ap.add_argument("--json", action="store_true", help="只输出纯 JSON，供程序调用（不打印调试信息）")
    args = ap.parse_args()

    items = load_items(args.taxonomy, args.scenario)
    if not items:
        print(f"场景 {args.scenario} 暂无物品清单（自定义场景需后续填充）")
        return

    model, processor = load_model(
        args.model, args.adapter if os.path.exists(args.adapter) else None
    )

    images = collect_images(args.image)
    results = []
    if not args.json:
        print(f">> 共 {len(images)} 张待检测\n")

    for img in images:
        entry = {"image": os.path.basename(img), "path": img, "present": [], "missing": []}
        if not args.json:
            print(f"===== {entry['image']} =====")
        try:
            raw = infer_one(img, items, model, processor, scenario=args.scenario)
        except Exception as e:
            print("  推理失败：", repr(e))
            entry["error"] = repr(e)
            results.append(entry)
            continue

        parsed = try_parse_json(raw, canon=items)
        if parsed:
            entry["present"] = [
                {"name": it.get("name"), "location": it.get("location")}
                for it in parsed if it.get("present")
            ]
            entry["missing"] = [it.get("name") for it in parsed if not it.get("present")]
        else:
            entry["error"] = "未能解析出结构化 JSON"
            entry["raw"] = raw
        results.append(entry)

        if args.json:
            continue

        print("模型原始输出：")
        print(raw)
        if parsed:
            print("解析后结构化：")
            print(json.dumps({"items": parsed}, ensure_ascii=False, indent=2))
            print(f"→ 已带({len(entry['present'])})：{'、'.join(p['name'] for p in entry['present']) or '无'}")
            print(f"→ 未带({len(entry['missing'])})：{'、'.join(entry['missing']) or '无'}")
        else:
            print("（未能解析出结构化 JSON，见上方原始输出）")
        print()

    if args.json:
        print(json.dumps({"items": items, "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
