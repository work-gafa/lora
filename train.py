"""
luggage-agent/train.py
==================================================
用 QLoRA 微调 Qwen2.5-VL-3B，让模型学会：
「看一张行李/房间照片 → 输出必备物品带齐情况的 JSON」。

数据格式（data/labeled/train.jsonl，每行一条）：
{
  "image": "raw/reference_xhs/小红书行李参考图1.png",
  "instruction": "请检查照片中的出行必备物品，逐项判断是否在照片内并给出位置",
  "answer": "[{\"name\":\"身份证\",\"present\":true,\"location\":\"左侧内袋\"},{\"name\":\"充电宝\",\"present\":false,\"location\":null}]"
}

训练后 LoRA 适配器保存到 output/lora-adapter（很小的文件，方便发给组员）。

运行：
  python train.py --data data/labeled/train.jsonl --model vlm/qwen2.5-vl-3b-instruct --out output/lora-adapter

关键说明：
  之前版本用 SFTTrainer(dataset_text_field="messages") 直接塞 PIL 图，
  但 Qwen2.5-VL 需要先把图片经 process_vision_info 转成专用张量，
  SFTTrainer 默认 collator 不会做这件事 → 图像进不去、等于白训。
  本版本改用自定义 QwenCollator 显式完成「模板化 + 图像张量化 + 对齐 + 掩码」，
  才是 Qwen2.5-VL 多模态 SFT 的正确写法。
==================================================
"""
import argparse
import json
import os

from PIL import Image
import torch
from transformers import (
    Qwen2_5_VLForConditionalGeneration,
    AutoProcessor,
    BitsAndBytesConfig,
    Trainer,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model
from datasets import Dataset, Image as DImage, Value
from qwen_vl_utils import process_vision_info


# ---- 4-bit 量化：让 3B 模型能在 RTX 4060 8GB 上训练 ----
def make_bnb_config():
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_type=torch.float16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )


# ---- 把一条 jsonl 变成扁平样本（图片为 PIL，collator 内再组装对话）----
MAX_SIDE = 512  # 全局：训练图片最长边。512 比 768 视觉 token 少 ~44%，8GB 显卡不易卡机


def load_sample(example, data_root):
    img_path = os.path.join(data_root, example["image"])
    image = Image.open(img_path).convert("RGB")
    # 限制最长边，控制视觉 token 数，避免 RTX 4060 8GB 训练 OOM / 整机卡死
    w, h = image.size
    if max(w, h) > MAX_SIDE:
        scale = MAX_SIDE / max(w, h)
        image = image.resize((int(w * scale + 0.5), int(h * scale + 0.5)), Image.BILINEAR)
    return {
        "image": image,
        "instruction": example["instruction"],
        "answer": example["answer"],
    }


def build_dataset(jsonl_path, data_root):
    rows = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    ds = Dataset.from_list([load_sample(r, data_root) for r in rows])
    return ds


# ---- 自定义 collator：多模态 SFT 的核心 ----
class QwenCollator:
    def __init__(self, processor, max_length=2048):
        self.processor = processor
        self.max_length = max_length

    def __call__(self, examples):
        texts, image_lists = [], []
        for ex in examples:
            msgs = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": ex["image"]},
                        {"type": "text", "text": ex["instruction"]},
                    ],
                },
                {"role": "assistant", "content": ex["answer"]},
            ]
            text = self.processor.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=False
            )
            image_inputs, _ = process_vision_info(msgs)
            texts.append(text)
            image_lists.append(image_inputs)

        batch = self.processor(
            text=texts,
            images=image_lists,
            return_tensors="pt",
            padding=True,
            truncation=False,  # 多模态：不能截断，否则图片占位 token 错位
        )
        # 训练目标 = 输入本身；把 padding 位置掩掉，不计算损失
        labels = batch["input_ids"].clone()
        labels[labels == self.processor.tokenizer.pad_token_id] = -100
        batch["labels"] = labels
        return batch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/labeled/train.jsonl")
    ap.add_argument("--model", default="vlm/qwen2.5-vl-3b-instruct")
    ap.add_argument("--out", default="output/lora-adapter")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--bs", type=int, default=1)
    ap.add_argument("--grad_accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--data_root", default="data")
    ap.add_argument("--max_length", type=int, default=2048)
    ap.add_argument("--resume", action="store_true",
                    help="从 output_dir 下最近的 checkpoint 续训（被中断后用）")
    args = ap.parse_args()

    print(">> 加载 4-bit 量化基座：", args.model)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        args.model,
        device_map="auto",
        quantization_config=make_bnb_config(),
    )
    model.config.use_cache = False  # 训练时必须关掉 KV cache
    processor = AutoProcessor.from_pretrained(args.model)

    # 双保险：从 processor 侧再压视觉 token 上限（配合 load_sample 的 resize）
    try:
        ip = processor.image_processor
        ip.max_pixels = MAX_SIDE * MAX_SIDE          # 视觉 token 上限
        ip.min_pixels = 28 * 28 * 4                   # 下限，防止过小图被放大
        print(f">> processor 像素上限: max_pixels={ip.max_pixels}, min_pixels={ip.min_pixels}")
    except Exception as e:
        print(">> 设置 processor 像素上限跳过：", e)

    # LoRA 只训练少量低秩矩阵（基座冻结）
    lora_cfg = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    print(">> 读取训练数据：", args.data)
    train_ds = build_dataset(args.data, args.data_root)

    training_args = TrainingArguments(
        output_dir=args.out,
        per_device_train_batch_size=args.bs,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_steps=2,
        fp16=True,
        logging_steps=5,
        save_strategy="steps",
        save_steps=5,  # 每 5 步存一次，断点可续训
        save_total_limit=3,
        optim="paged_adamw_8bit",
        report_to="none",
        remove_unused_columns=False,  # 多模态：image/instruction/answer 由 collator 用，不能删
        gradient_checkpointing=True,  # 用计算换显存，避免 8GB OOM
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        data_collator=QwenCollator(processor, max_length=args.max_length),
    )

    print(">> 开始训练 ...")
    trainer.train(resume_from_checkpoint=args.resume)
    trainer.save_model(args.out)
    print("✅ LoRA 适配器已保存到：", args.out)


if __name__ == "__main__":
    main()
