# 行李必备物品提醒 Agent

出门前对着行李拍张照，AI 告诉你「带齐了没、东西在哪」。基于 **Qwen2.5-VL-3B** + **QLoRA 微调**，消费级显卡（RTX 4060 8GB）可训可跑。

---

## 效果

当前版本（v3，32 项清单 / 2 个场景 / 31 张标注图 / 273 个手标框 / 202 个正样本）验证指标：

| 指标 | 数值 |
|---|---|
| 逐物准确率 | **76.7%** |
| present 精确率 P | 48.4% |
| present 召回率 R | 58.9% |
| present F1 | **53.1%** |

分场景：

| 场景 | 图片 | 准确率 | P | R | F1 |
|---|---|---|---|---|---|
| 出门旅行 / 旅游 | 20 | 78.4% | 52.0% | 61.4% | **56.3%** |
| 上学 / 回家 | 11 | 73.9% | 42.7% | 54.7% | **48.0%** |

表现好的项：衣物 F1 = 94.7%、相机 80.0%、鞋子 / 梳妆饰品 76.9%、耳机 / 包袋 / 文具 66.7%。
短板（训练集里样本太少）：钱包现金、银行卡、门票订单、手机、内衣袜、防晒、口罩、钥匙、笔记本 F1 = 0%。

> 瓶颈是**数据量**（31 张 / 901 个判定）。扩到 100~200 张真实照片、补齐短板项后指标还有明显上升空间。
> 评估口径：同一批 31 张图既是训练集也是测试集，属**过拟合场景下的上限估计**，不是泛化性能。

---

## 场景机制（v3 新增）

同一个模型、同一套权重，靠**提示词里给哪份清单**区分场景：

- 用户选「旅行」→ 只给 28 项旅行清单，**上学专属项（书本、文具…）不会出现在结果里**
- 用户选「上学」→ 只给 31 项上学清单，**旅行专属项（门票、相机…）不会被误报**

「未带」不靠模型生成，而是 **该场景清单 − 模型列出的**，由程序算。所以模型只需输出「看到的」，输出从 ~700 token 缩到 ~80 token，小样本下更容易学会看图。

清单项归属哪些场景，写在 `taxonomy.json` 每项的 `scenarios` 字段；每张图属于哪个场景，写在 `data/labeled/image_scenarios.json`（都能在平台上直接改）。

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

`data/raw/` 与 `data/labeled/uploads/` 因体积 / 隐私没进仓库，但 `train.jsonl` 的图片路径指向它们。用自带脚本从归档还原：

```bat
python _scripts/restore_data.py
```

会把 `data/archive/v3-20261005/images/**` 按原相对结构复制回 `data/**`
（`raw/reference_wuzi/` 11 张 + `labeled/uploads/` 20 张，共 31 张）。

### 4. 训练

```bat
python train.py --data data/archive/v3-20261005/train.jsonl ^
    --model vlm/qwen2.5-vl-3b-instruct ^
    --out output/lora-adapter --epochs 16 --lr 1e-4
```

> 用归档里的 `train.jsonl`。`data/labeled/train.jsonl` 是本地工作副本，没进仓库。
> `--epochs 16` 是当前最优配置（loss 9.93 → 2.88）；8 epoch 会欠拟合。

### 5. 推理

```bat
python infer.py --image 你的行李照.jpg --scenario travel --adapter output/lora-adapter
```

### 6. 验证指标

```bat
python validate.py --adapter output/lora-adapter --taxonomy taxonomy.json ^
    --data data/archive/v3-20261005/train.jsonl
```

### 7. 标注平台（扩数据用）

双击项目根目录的 **`启动标注平台.bat`**（会自动开浏览器，地址 http://127.0.0.1:8004）。

流程：上传照片 →（可选）AI 预标 → 手改名字 → **保存标注** → 导出训练数据。

界面分工：

| 标签页 | 干什么 |
|---|---|
| **数据集（我的标注）** | 缩略图网格看全部图，角标显示框数；可切场景、**删图**、点图直接去标注 |
| **方框标注** | 画 / 移 / 缩 / 改名 / 删框，AI 预标，LoRA 识别，保存，导出 |
| **VLM 识别** | 面向用户的测试页：选场景 → 传图 → 告诉你带了没、在哪，并给**只读方框预览** |
| **物品清单** | 32 项规范名 + 类别 + 别名 + 场景，**直接在平台上增删改** |

---

## 项目结构

| 路径 | 说明 |
|---|---|
| `taxonomy.json` | **物品清单**（32 项 / 9 大类，每项带别名与归属场景）—— 全链路单一数据源 |
| `normalize.py` | **别名归类模块**：`双肩包/收纳包 → 包袋`、`蓝色相机 → 相机` |
| `prompt.py` | **提示词单一来源**（含场景机制）：训练 / 推理 / 平台三处共用 |
| `train.py` | QLoRA 训练（自定义 QwenCollator） |
| `infer.py` | 推理（`--scenario` 选场景，输出自动归类 + 补齐缺席项） |
| `validate.py` | 验证评估（按图所属场景分别提问），产出 `validate_report.json` |
| `gdino_detect.py` | GroundingDINO 自动预标注 |
| `anno-tool/` | 标注平台（FastAPI + Vue3，免构建） |
| `data/archive/` | **标注数据归档**（图片 + 表格，见下） |
| `_scripts/` | 一次性工具脚本（归档 / 还原 / 生成 PPT…） |

---

## 标注数据归档

`data/archive/v3-20261005/`

| 文件 | 内容 |
|---|---|
| `images/` | 31 张标注原图（**保留 `data/` 相对结构**，供 `restore_data.py` 一键还原） |
| `overlays/` | 11 张框可视化对照图 |
| `labels_detail.csv` | 明细表：每个手标框一行，含「原始名 → 规范名」+ 场景 |
| `labels_matrix.csv` | 矩阵表：图 × 32 项，单元格是 present 时的位置描述 |
| `labels_stats.csv` | 统计表：每项的框数、present 次数、覆盖图片数、归属场景、别名 |
| `labels_by_scenario.csv` | 场景分布表 |
| `train.jsonl` | 训练数据（含 `scenario` 字段） |
| `taxonomy.json` / `image_scenarios.json` / `manual_annotations.json` | 清单 / 场景 / 手标框快照 |
| `MANIFEST.md` | 归档说明 |

统计：273 个手标框，归类成功率 **100%**，训练正样本 202 个。

> 归档是**快照，不覆盖旧的**。加数据后请用新版本号重跑 `_archive.py`（如 `v4-日期`），
> 万一新数据训崩了还能退回上一版。

### 答案格式（本版本）

```json
{"items": [{"name": "充电宝", "location": "画面右侧"}]}
```

只列画面里**真实看到的**物品，不带 `present` 字段；一样都没看到时返回 `{"items": []}`。
（旧格式 `[{name,present,location}]` 在 `validate.py` 里仍兼容。）

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
| **提示词写「必备物品」** | 模型把所有项都答成"在" | 改成中性的「待核对清单」+ 明确「不代表它们都在照片里」 |
| **模型输出全量太长** | 复读模板、学不会看图 | 改「只输出看到的」，输出 ~700 → ~80 token |
| **训练轮数不够** | 8 epoch 欠拟合 | 16 epoch（loss 9.93 → 2.88） |
| 前端改了没生效 | 浏览器缓存旧 `app.js` | 后端加 `no-store` 中间件 + `index.html` 里 `?v=` 版本号 |
| bat 中文乱码 | UTF-8 + `chcp 65001` 反而报错 | 用 GBK 保存、不写 `chcp`、用 `%~dp0` 绝对路径 |

---

## 文档

仓库内这份 `README.md` 是唯一对外说明，**照着「快速开始」走就能跑通**。

以下几份是**个人向文档，没有放进仓库**（存在本地 `个人留存_继续用/`），需要的话找作者要：

- `本机部署步骤清单.md` — 从零到跑通的完整步骤 + 进度
- `GitHub共享指南.md` — 推远端与协作流程
- `备份与更新指南.md` — 网盘备份该传什么、改了什么该替换什么
- `清单v2对照分析.md` — 清单 v2 相对旧版的新增 / 合并 / 待定项
- `行李提醒Agent_汇报PPT.pptx` — 汇报用演示稿（含讲稿备注）

---

## 路线图

- [x] 基座下载 + 零样本验证
- [x] GDINO 自动预标 + 人工修正
- [x] 清单 v2 → v3（32 项 + 别名）
- [x] 别名归类，修复丢框（归类率 100%）
- [x] 提示词对齐 + 输出格式改为「只列看到的」
- [x] 场景机制（旅行 / 上学）+ 平台场景切换
- [x] 标注平台：在线改清单 / 删图 / 识别预览
- [x] 训练 + 验证（F1 53.1%，16 epoch）
- [ ] **扩数据：31 张 → 100~200 张真实照片，重点补齐口罩 / 湿巾 / 钥匙 / 文件资料**
- [ ] 清单按用户描述 AI 自动生成（与同学商定方案）
- [ ] 更多场景（出差 / 露营 / 健身）
