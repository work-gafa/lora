# 行李识别 · 自动定位标注方案（汇报用）

> 适用场景：向老师汇报「出门前必备物品提醒」模型的训练数据是怎么标出来的。
> 核心一句话：**用开集检测器自动画框预标注，人只做检查与修正（human-in-the-loop）。**

---

## 一、任务背景与目标
- 我们要训练一个模型：看一张行李/出行照片，**逐项判断 23 类必备物品是否带齐，并说明各自位置**。
- 训练需要大量「图像 + 人工真值标注」。逐张人工框选 23 个物品太累、易错、慢。
- 方案：让检测模型**先自动预标注**，人工只负责**看图核对 + 改错**（把重复劳动交给模型）。

## 二、选用的模型：GroundingDINO
- **类别**：开集 / 零样本目标检测（open-vocabulary / zero-shot object detection）。
- **版本**：`grounding-dino-tiny`（轻量，约 700MB，本机 RTX 4060 8GB 可实时运行）。
- **来源**：IDEA Research 开源，Apache 2.0，HuggingFace `transformers` 直接调用。
- **关键能力**：输入一段文字（类别名），直接输出对应物体的边界框——**不必为我们的 23 类做任何训练**，这就是「零样本 / 开集」。

## 三、工作原理（核心，配原理图）
输入 = 一张图像 + 文本提示（把 23 个物品名写成英文逗号串，如 `cell phone . camera . umbrella .`）

1. **图像编码器（Swin Transformer）**：把图切成 patch，提取视觉特征。
2. **文本编码器（BERT）**：把 23 个类别名编码成文本特征。
3. **跨模态融合解码器（Transformer）**：用「语言引导的查询」做图文特征交叉注意力，让每个文本 token 去图里找对应物体。
4. **输出**：每个类别的边界框 `(x1,y1,x2,y2)` + 置信度分数。

> 关键卖点：**开放词汇（open vocabulary）**——要检测新类别，只改文字提示即可，无需重新训练。这正是本项目能"零样本预标注"的原因。

## 四、我们的标注流水线
```
中文 23 项  →  英文提示词映射  →  逐图检测  →  像素级边界框
                                          ├─ overlays/*_bbox.jpg  （原图画框+标签，给人看图核对）
                                          ├─ locations_review.csv （表格：每项 TRUE/FALSE + 坐标 + 区域文字）
                                          └─ detections.json       （程序用结构化数据）
```

## 五、为什么不用多模态大模型（Qwen2.5-VL）
| 维度 | Qwen2.5-VL 零样本 grounding | GroundingDINO |
|---|---|---|
| 定位稳定性 | 同图多次结果差异大，多物被套用同一框 | 稳定，框互相区分 |
| 整张漏检 | 常见（满桌物品曾被判 0 项） | 较少 |
| 位置精度 | 像素坐标常错乱 | 框贴合物体 |
| 速度 / 显存 | 3B 推理较重 | tiny 轻量 |

结论：**VLM 擅长"看图说话"，不擅长"精确定位"**；精确框交给专用检测器更可靠。

## 六、人工修正流程（你正在做的）
改哪都只在 `locations_review.csv`（建议另存为 `locations_corrected.csv` 防覆盖）。三类典型错误：

1. **标签张冠李戴**（框对、名字错，如把太阳镜标成"口罩"）
   → 把该行的 `item` 改成正确的 23 项内名称；若真实物体不在 23 项里 → 直接删掉或设 `present=FALSE`。
2. **误检**（框住整张图或不存在的物体，`score<0.35` 尤其可疑，如"常用药品 整张画面"）
   → `present` 改 `FALSE`，清空 `x1..y2` 坐标。
3. **漏标**（真实存在但模型没出框）
   → 在对应 `(图名, 正确项)` 那一行设 `present=TRUE`，填 `x1..y2`；或只在 `location` 列写"画面X区域"文字（不依赖像素框也行）。

> 提示：CSV 里**每个物品在每张图都有一行**，FALSE 行就是"待你确认是否真的不在"。

## 七、修正后 → 训练
```bash
# 1) 把改好的表另存为 locations_corrected.csv（防止重跑检测被覆盖）
# 2) 转训练数据
python gdino_to_train.py          # 自动优先读 locations_corrected.csv → 生成 train.jsonl
# 3) 开训
python train.py --data data/labeled/train.jsonl \
                --model vlm/qwen2.5-vl-3b-instruct --out output/lora-adapter
```

## 八、局限与后续
- 23 项固定清单；**框的位置可信度 > 名字可信度**，名字需人工把关。
- 当前 11 张为参考图，正式训练建议扩到 50~150 张真实行李照。
- 后续可把像素框用于"在图上圈出遗漏物"的增强提醒界面。

---

### 附：关键文件清单（项目 luggage-agent/）
| 文件 | 作用 |
|---|---|
| `gdino_detect.py` | GroundingDINO 自动检测，生成标注 |
| `data/labeled/overlays/*_bbox.jpg` | 带框对照图（核对用） |
| `data/labeled/locations_review.csv` | 机器草稿标注表 |
| `data/labeled/locations_corrected.csv` | **你改好的版本**（手动另存） |
| `gdino_to_train.py` | 标注 → 训练数据 桥梁 |
| `data/labeled/train.jsonl` | 最终训练数据 |
