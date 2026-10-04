# 标注数据归档 · v2-20261004

生成时间：2026-10-04 23:43:42

## 概览

| 项目 | 数值 |
|---|---|
| 标注图片数 | 11 |
| 框可视化图 | 11 |
| 手标框总数 | 82 |
| 归类成功 | 82 / 82 |
| 训练正样本(present=true) | 64 |
| 清单项数 | 28 |
| 类别数 | 8 |

## 目录说明

| 路径 | 内容 |
|---|---|
| `images/` | 原图副本（训练集来源：`data/raw/reference_wuzi/`） |
| `overlays/` | GroundingDINO 框可视化对照图 |
| `labels_detail.csv` | 明细表：每个手标框一行，含「原始名 → 规范名」映射 |
| `labels_matrix.csv` | 矩阵表：图 × 清单项，单元格为 present 时的位置描述 |
| `labels_stats.csv` | 统计表：每项的框数、present 次数、覆盖图片数、别名 |
| `train.jsonl` | 训练数据副本（image / instruction / answer） |
| `taxonomy.json` | 本归档对应的清单版本（28 项 + 别名） |
| `manual_annotations.json` | 原始手标框数据 |

## 数据来源链路

```
reference_wuzi/ 原图
  -> gdino_detect.py 自动预标 -> locations_review.csv + overlays/
  -> 人工在标注平台手改      -> locations_corrected.csv / manual_annotations.json
  -> normalize.py 别名归类   -> train.jsonl（本次已修复丢框问题）
```

> **重要**：早期导出会把「名称不在清单里」的框静默丢弃（82 框丢了 45 个）。
> 本版本经 `normalize.py` 归类后**救回率 100%**，正样本 35 → 64。

## 未归类项

无，全部已归入清单项。

## 复现方式

```bat
conda activate lora
python train.py --data data/archive/v2-20261004/train.jsonl ^
    --model vlm/qwen2.5-vl-3b-instruct --out output/lora-adapter --epochs 8 --lr 1e-4
```
