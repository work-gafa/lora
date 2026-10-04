# 行李必备物品提醒 Agent

出门前对着行李拍张照，AI 告诉你「带齐了没、东西在哪」。基于 **Qwen2.5-VL-3B** + **QLoRA 微调**，消费级显卡（RTX 4060 8GB）可训可跑。

---

## 效果

当前版本（v2，28 项清单 / 11 张标注图 / 64 个正样本）验证指标：

| 指标 | 数值 |
|---|---|
| 逐物准确率 | **82.8%** |
| present 精确率 P | 61.7% |
| present 召回率 R | 45.3% |
| present F1 | **52.3%** |

满分项：证件、鞋子 F1 = 100%；优秀：包袋、相机、衣物 F1 ≈ 80%。

> 瓶颈是**数据量偏少**（11 张）。扩到 50~150 张真实行李照后指标还有明显上升空间。

---

## 快速开始

### 1. 环境

```bat
conda create -n lora python=3.10 -y
conda activate lora
pip install torch==2.7.1+cu128 --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
```

### 2. 下载基座模型（约 7.7GB）

`vlm/` 已被 .gitignore 排除，**每人各自下一份**。先装下载工具：

```bat
pip install -U "huggingface_hub[cli]"
```

再下载：

```bat
set HF_ENDPOINT=https://hf-mirror.com
set HF_HUB_DISABLE_XET=1
hf download Qwen/Qwen2.5-VL-3B-Instruct --local-dir vlm/qwen2.5-vl-3b-instruct
```

### 3. 还原训练图片（**必做**，跳过会报「图片找不到」）

`data/raw/` 因体积原因没进仓库，但 `train.jsonl` 的图片路径指向它。用自带脚本从归档还原：

```bat
python _scripts/restore_data.py
```

会把 `data/archive/v2-20261004/images/` 的 11 张图复制到 `data/raw/reference_wuzi/`。

### 4. 训练

```bat
python train.py --data data/archive/v2-20261004/train.jsonl ^
    --model vlm/qwen2.5-vl-3b-instruct ^
    --out output/lora-adapter --epochs 8 --lr 1e-4
```

> 用归档里的 `train.jsonl`。`data/labeled/train.jsonl` 是本地工作副本，没进仓库。

### 5. 推理

```bat
python infer.py --image 你的行李照.jpg --adapter output/lora-adapter
```

### 6. 验证指标

```bat
python validate.py --adapter output/lora-adapter --taxonomy taxonomy.json
```

### 7. 标注平台（扩数据用）

双击 `anno-tool\启动标注平台.bat`，上传照片 → AI 预标 → 手改 → 导出（自动归类）。

---

## 项目结构

| 路径 | 说明 |
|---|---|
| `taxonomy.json` | **物品清单**（28 项 / 8 大类，每项带别名表）—— 全链路单一数据源 |
| `normalize.py` | **别名归类模块**：`双肩包/收纳包 → 包袋`、`蓝色相机 → 相机` |
| `prompt.py` | **提示词单一来源**：训练 / 推理 / 平台三处共用同一句 |
| `train.py` | QLoRA 训练（自定义 QwenCollator） |
| `infer.py` | 推理（输出自动归类 + 补齐缺席项） |
| `validate.py` | 验证评估，产出 `validate_report.json` |
| `gdino_detect.py` | GroundingDINO 自动预标注 |
| `anno-tool/` | Vue 标注平台 + FastAPI 后端 |
| `data/archive/` | **标注数据归档**（图片 + 表格，见下） |
| `_scripts/` | 一次性工具脚本 |

---

## 标注数据归档

`data/archive/v2-20261004/`

| 文件 | 内容 |
|---|---|
| `images/` | 11 张标注原图 |
| `overlays/` | 11 张框可视化对照图 |
| `labels_detail.csv` | 明细表：每个手标框一行，含「原始名 → 规范名」映射 |
| `labels_matrix.csv` | 矩阵表：图 × 28 项，单元格是 present 时的位置描述 |
| `labels_stats.csv` | 统计表：每项的框数、present 次数、覆盖图片数、别名 |
| `train.jsonl` | 训练数据 |
| `MANIFEST.md` | 归档说明 |

统计：82 个手标框，归类成功率 **100%**，训练正样本 64 个。

---

## 关键设计：为什么要有 `normalize.py`

早期版本导出训练数据时，会把「名称不在清单里」的框**静默丢弃**——82 个手标框里有 **45 个（55%）被白白扔掉**，其中「收纳包」一个名字就丢了 13 次。

`normalize.py` 做三步匹配（精确名 → 别名表 → 剥离修饰前缀），把这批数据**全部救回**（正样本 35 → 64，+83%），这是 F1 从 38% 涨到 52% 的主要原因之一。

---

## 已踩过的坑

| 坑 | 症状 | 解法 |
|---|---|---|
| conda 解释器路径 | `..\envs\lora\Scripts\python.exe 不是内部或外部命令` | `python.exe` 在**环境根目录**，没有 `Scripts` |
| HF Xet 协议 | `CAS Client Error 401 Unauthorized` | 设 `HF_HUB_DISABLE_XET=1` |
| 训练显存打满 | 整机卡死、进程被杀 | `MAX_SIDE=512` + `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`，训练前关浏览器 |
| transformers 5.x | `warmup_ratio` 不支持 | 改用 `warmup_steps` |
| **训练/推理提示词不一致** | 模型「A 问法学、B 问法考」，输出混乱 | 统一到 `prompt.py`，三处共用 |

---

## 文档

仓库内这份 `README.md` 是唯一对外说明，**照着「快速开始」走就能跑通**。

以下几份是**个人向文档，没有放进仓库**（存在本地 `个人留存_继续用/`），需要的话找作者要：

- `本机部署步骤清单.md` — 从零到跑通的完整步骤 + 进度
- `GitHub共享指南.md` — 推远端与协作流程
- `清单v2对照分析.md` — 清单 v2 相对旧版的新增 / 合并 / 待定项
- `行李提醒Agent_汇报PPT.pptx` — 汇报用演示稿（含讲稿备注）

---

## 路线图

- [x] 基座下载 + 零样本验证
- [x] GDINO 自动预标 + 人工修正
- [x] 清单 v2（28 项 + 别名）
- [x] 别名归类，修复丢框
- [x] 训练 + 验证（F1 52.3%）
- [ ] **扩数据：11 张 → 50~150 张真实行李照**
- [ ] 自定义场景（上学 / 出差 / 露营）
