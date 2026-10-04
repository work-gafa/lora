# 行李标注 · AI预标 + 手动画框工具（anno-tool）

实时标注窗：**不需要写任何坐标**。支持两种来源的图片——

- **预设图集** `data/raw/reference_wuzi`（教材参考图，左侧点选切换）
- **自主上传** 任意行李照片（点「上传行李图片」，落到 `data/labeled/uploads/`）

两种图都能由 **GroundingDINO 自动框一遍清单内的出行物品**（清单见项目根 `taxonomy.json`），你再在浏览器里微调。
左侧图集 / 中间画布 / 右侧标注列表，改完自动存盘，一键导出 `train.jsonl`。

> 与 lora 平台同构：FastAPI 后端 + 单页 HTML 前端，模块划分为
> 图集列表 / 图片资源 / 标注存储 / 一键导出训练数据。

## 启动（按需：开窗口即用，关窗口即停）
**方式一（推荐，双击即用）**：双击 `anno-tool\启动标注平台.bat`
- 自动打开浏览器 http://127.0.0.1:8003；
- 在窗口里**前台运行 uvicorn**；**直接关掉这个 cmd 窗口 = 停止服务**（GroundingDINO 显存自动释放）。

**方式二（聊天里让我开/关）**：告诉我就行——说「开标注平台」我后台拉起并给你链接，说「关标注平台」我立刻停掉。

**方式三（手动命令行）**：
```bat
cd luggage-agent
D:\10604\ANACONDA\envs\lora\python.exe -m uvicorn anno-tool.app:app --host 127.0.0.1 --port 8003
```
> 服务**只在你要用时才跑**，平时不占 GPU。验证 LoRA 训练时也无需它常驻。

## 用法（推荐流程：上传 → AI 预标 → 人工改）
1. 点右上 **「上传行李图片」**，选一张行李/房间照 → 上传后 GroundingDINO 会**先自动框一遍**（返回候选框，颜色随机）。
2. 你再微调：
   - **拖动框体** = 移动；**拖四角/四边手柄** = 缩放；
   - 点框 → 右侧「改」名（从清单项选或自填）；「×」删除；
   - 空白处拖拽 = 新增一个框（松开选物品名）。
3. 改动**自动保存**（也可点「保存」）；标注存于 `data/labeled/manual_annotations.json`。
4. 想对某张图重跑 AI：点 **「AI自动标注当前图」**（覆盖当前框）。预设图集也可用「导入草稿」加载旧的 `detections.json`。
5. **「导出训练数据」**：遍历【全部已标注图片】生成 `data/labeled/train.jsonl`（与 `gdino_to_train.py` 同 schema），直接喂 `train.py`。
   - 上传图的 `image` 字段记为 `labeled/uploads/xxx`；预设图记为 `raw/reference_wuzi/xxx`。

## 接口一览
| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/images` | 图集列表（含 source: preset/upload） |
| GET  | `/api/image/{name}` | 图片文件（预设或上传） |
| GET  | `/api/annotations` | 读取全部标注 |
| POST | `/api/annotations` | 保存全部标注 |
| POST | `/api/upload` | 上传图片 + GroundingDINO 自动标注，返回 `{name,boxes,size}` |
| GET  | `/api/autodetect/{name}` | 对任意已加载图重跑自动标注 |
| GET  | `/api/autodraft` | 导入旧 `detections.json` 草稿 |
| GET  | `/api/canon` | 返回当前必备物品清单（来自 `taxonomy.json`） |
| POST | `/api/lora_recognize/{name}` | **用训练后的 LoRA 识别**：返回每项「带没带 + 文字位置」 |
| POST | `/api/export` | 导出 `train.jsonl` |

## 用训练后的 LoRA 识别（混合模式）
平台有**两个引擎**，各司其职：

| 引擎 | 负责 | 输出 |
|------|------|------|
| **GroundingDINO** | 画**精确像素框**（位置准） | 可拖拽的框 |
| **训练后的 LoRA（Qwen2.5-VL）** | **语义识别**（这项到底带没带、大概在哪） | `带/没带 + 文字位置`（无精确框） |

用法：选一张图 → 点右上 **「用训练后LoRA识别」** → 右侧面板按**完整清单**逐项列出：
- ✅ 绿 = 模型认为**带了**；❌ 红 = **没带**；❔ 灰 = **未判断**（模型未提及该项）；
- 面板顶部有「带了 N · 没带 N · 未判断 N」汇总；
- 左侧的精确框仍由 GroundingDINO 画，两者**并列供你对照确认**。

> 为什么 LoRA 不给精确框？因为训练数据的 `location` 只存了「画面左上角」这类**文字描述**，且 VLM 本身定位会飘——所以精确框仍交给 GroundingDINO。
> ⚠️ 当前 `output/lora-adapter` 是**旧 23 项**训练版，`validate.py` 实测**过度预测明显（精确率约 24%）**，面板会提示「结果仅供参考」。要真准，需用新 22 项清单**重训**（见下）。

## 修改必备物品清单（集中配置 v2）
必备物品清单是 **单一文件** `luggage-agent/taxonomy.json`（项目根，不在 anno-tool 内），全链路（AI 自动标注 / 平台选择项 / 导出训练 / 推理）都从它加载，**改这一处全链路生效**：

- 结构（v2，带类别与别名）：
  ```json
  { "items": [
    {"name": "包袋", "en": "backpack", "category": "收纳包袋",
     "aliases": ["收纳包", "书包", "双肩包", "行李箱", "化妆包"]},
    ...
  ] }
  ```
- `name` = 规范大类名（模型只输出这些）；`en` = GroundingDINO 英文提示词；`category` = 归类；`aliases` = **别名表**（手写/模型输出的细名自动归到该大类）。
- **删除某项**：删掉那一行 → AI 自动标注不再框它，导出/训练 schema 也不再含它。
- **新增某项**：加一行 `{"name": …, "en": …, "category": …, "aliases": [...]}`。
- **别名归类**：由 `luggage-agent/normalize.py` 统一处理——精确名 → 别名 → **自动剥离颜色/图案/尺寸修饰**（"蓝色相机"→相机、"26寸行李箱"→包袋）→ 子串包含。
- **生效方式**：改完**重启 anno-tool 服务**（关黑窗口、再双击 `.bat`）。
- ⚠️ 已训好的 LoRA 推理侧**不会自动变**：要让推理同步，需**重导 train.jsonl + 重训**。
- 另：`demo/taxonomy.json` 是旧的「场景推荐」清单（school/travel，23 项含转换插头），与主链路独立，基本未用。

## 清单 v2 设计说明（28 大类 / 8 类别）
| 类别 | 大类 |
|---|---|
| 证件钱财 | 证件、钱包/现金、银行卡、门票/订单 |
| 电子设备 | 手机、充电器、充电宝、耳机、相机、便携电器 |
| 衣物鞋帽 | 衣物、内衣袜、鞋子、帽子 |
| 洗漱护肤 | 洗漱用品、护肤品、防晒、梳妆饰品 |
| 健康医药 | 常用药品、口罩、湿巾、卫生用品 |
| 收纳包袋 | 包袋 |
| 其他 | 钥匙、娱乐用品 |
| 饮食雨具 | 水杯、零食、雨伞 |

> 相比旧 23 项：**新增** 包袋 / 鞋子 / 帽子 / 便携电器 / 梳妆饰品 / 卫生用品 / 娱乐用品；**合并** 身份证+护照→证件；**转换插头**并入充电器（不再单列）。
> 关键收益：把"收纳包/书包/双肩包"等归到 **包袋** 后，导出时不再丢弃，**手标框救回率从 45% 提升到 100%**。
- **生效方式**：改完**重启 anno-tool 服务**（关掉黑色 cmd 窗口、再双击 `启动标注平台.bat`）。
- ⚠️ 已训好的 LoRA 推理侧**不会自动变**：要让 `infer.py` 也不再输出某项，需**重导 train.jsonl（关服务重开后点「导出训练数据」）+ 重训**（用 `train.py`）。
- 另：`demo/taxonomy.json` 是「场景推荐」清单（school/travel/custom），与检测/训练链路独立，如用到也同步删改。

## 数据约定
- 框坐标用**归一化 [0,1]** 存储（与显示尺寸无关），导出时乘原图宽高转像素。
- 导出 schema 与 `gdino_to_train.py` 完全一致，清单项顺序一致，无缝接 `train.py`。

## 注意
- GroundingDINO 模型首次调用时懒加载（`vlm/grounding-dino-tiny`），约几秒；之后复用。
- 本工具产出的 `manual_annotations.json` 是独立来源；点「导出」会**覆盖** `train.jsonl`。
- 旧「Excel 改 CSV」流程已弃用，建议直接用本工具完成标注。

## 验证 LoRA 效果
```bat
cd luggage-agent
D:\10604\ANACONDA\envs\lora\python.exe validate.py --adapter output/lora-adapter
```
逐物品比对预测与人工 GT，输出整体准确率、每类 P/R/F1、最易漏带/误报项，报告写 `validate_report.json`。
