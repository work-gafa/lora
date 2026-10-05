# 标注数据归档 · v3-20261005

生成时间：2026-10-05 22:54:35

## 概览

| 项目 | 数值 |
|---|---|
| 标注图片数 | 31 |
| 框可视化图 | 11 |
| 手标框总数 | 273 |
| 归类成功 | 273 / 273 |
| 训练正样本(present) | 202 |
| 清单项数 | 32 |
| 类别数 | 9 |
| 场景数 | 2 |

## 分场景

| 场景 | 清单项 | 图片数 | 正样本 |
|---|---|---|---|
| 出门旅行 / 旅游（`travel`） | 28 | 20 | 127 |
| 上学 / 回家（`school`） | 31 | 11 | 75 |

## 目录说明

| 路径 | 内容 |
|---|---|
| `images/` | 原图副本，**保留 `data/` 下的相对结构**（`raw/reference_wuzi/`、`labeled/uploads/`） |
| `overlays/` | GroundingDINO 框可视化对照图（仅预设图有） |
| `labels_detail.csv` | 明细表：每个手标框一行，含「原始名 → 规范名」与场景 |
| `labels_matrix.csv` | 矩阵表：图 × 清单项，单元格为 present 时的位置描述 |
| `labels_stats.csv` | 统计表：每项的框数、present 次数、覆盖图片数、归属场景、别名 |
| `labels_by_scenario.csv` | 场景分布表：每个场景的清单项、图片数、正样本 |
| `train.jsonl` | 训练数据副本（image / scenario / instruction / answer） |
| `taxonomy.json` | 本归档对应的清单版本 |
| `image_scenarios.json` | 每张图属于哪个场景 |
| `manual_annotations.json` | 原始手标框数据 |

## 答案格式（本版本）

```json
{"items": [{"name": "充电宝", "location": "画面右侧"}]}
```

**只列画面里真实看到的物品**，不要 `present` 字段；
「未带」= 该场景清单 − 已列出的，由程序计算，不占模型输出长度。
一样都没看到时返回 `{"items": []}`。

> 旧格式（`[{name,present,location}]` 全量）在 `validate.py` 里仍兼容。

## 数据来源链路

```
reference_wuzi/ 预设图 + labeled/uploads/ 上传图
  -> gdino_detect.py 自动预标 -> locations_review.csv + overlays/
  -> 标注平台手改              -> manual_annotations.json + image_scenarios.json
  -> normalize.py 别名归类     -> train.jsonl（按图所属场景取清单）
```

## 未归类项

无，全部已归入清单项。

## 复现方式

```bat
python _scripts/restore_data.py v3-20261005   :: 还原图片到 data/
conda activate lora
python train.py --data data/archive/v3-20261005/train.jsonl ^
    --model vlm/qwen2.5-vl-3b-instruct --out output/lora-adapter ^
    --epochs 16 --lr 1e-4
python validate.py --adapter output/lora-adapter --taxonomy taxonomy.json ^
    --data data/archive/v3-20261005/train.jsonl
```
