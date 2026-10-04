# 推 GitHub 并共享给组员

本地仓库 **已经准备好**：`git init` 完成、`.gitignore` 已配好、文件已全部放进暂存区。
下面每一步都可以直接复制执行。

> ⚠️ 有一步需要你自己填东西：**第 1 步的身份**（我没你的邮箱）。填完后面都是复制粘贴。

---

## 第 1 步：设置 Git 身份（每人只做一次）

`git commit` 必须知道你是谁。在 **Anaconda Prompt** 里执行：

```bat
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
```

> 邮箱建议填**你注册 GitHub 用的那个**，这样 GitHub 页面才会把提交归到你的头像下。
> 不想公开真实邮箱的话，去 GitHub → Settings → Emails 勾选 `Keep my email addresses private`，
> 然后用它提供的 `xxx@users.noreply.github.com`。

---

## 第 2 步：首次提交

我已经把文件放进暂存区了，你直接提交：

```bat
cd /d "D:\100001\homework\3.A\ai工作流\workbody\luggage-agent"
git commit -m "init: 行李必备物品提醒 agent（28 项清单 + QLoRA 微调，F1 52.3%）"
git branch -M main
```

确认提交成功：

```bat
git log --oneline
git status
```

应该看到一条记录，且 `git status` 显示 `nothing to commit`（工作区干净）。

---

## 第 3 步：在 GitHub 上建仓库

浏览器打开 <https://github.com/new>：

| 选项 | 填什么 |
|---|---|
| Repository name | `luggage-agent` |
| Description | `行李必备物品提醒 Agent — Qwen2.5-VL + QLoRA` |
| **可见性** | ⚠️ 建议选 **Private**（理由见下方提醒） |
| Initialize this repository with | **全部不要勾**（不要 README / .gitignore / LICENSE） |

> ⚠️ **关于可见性**：归档里有 11 张**小红书参考图**。仓库设成 Public 的话，
> 这些图会公开可见，存在版权风险，建议 **Private**。
> 要交作业给老师看的话，可以给老师单独开 Collaborator 权限，或者临时切 Public。

建好后，GitHub 会给你一个地址，形如：

```
https://github.com/<你的账号>/luggage-agent.git
```

---

## 第 4 步：关联并推送

把 `<你的账号>` 换成你的 GitHub 用户名：

```bat
git remote add origin https://github.com/<你的账号>/luggage-agent.git
git push -u origin main
```

**首次推送会弹窗让你登录** —— 选 *Browser* 方式，在浏览器里授权即可（Windows 凭据管理器会记住，以后不用再登录）。

> 如果弹窗报错或者压根没弹出来，说明没装 Git 凭据管理器。
> 备选方案：用 **Token** 推送 —— GitHub → Settings → Developer settings →
> Personal access tokens → Tokens (classic) → 勾选 `repo` 权限 → 生成后把地址改成：
> ```bat
> git remote set-url origin https://<你的账号>:<你的token>@github.com/<你的账号>/luggage-agent.git
> git push -u origin main
> ```

推送的内容约 **13 MB**（含 22 张图片），大概几十秒。

---

## 第 5 步：邀请组员协作

仓库页面 → **Settings** → **Collaborators** → **Add people**，填同学的 GitHub 用户名或邮箱。
对方会收到邮件邀请，接受后就有完整读写权限。

两人以上长期协作的话，建议建 **Organization**（Settings → Organizations），之后还能分组权限。

---

## 第 6 步：发给组员的操作说明

把下面这段直接发给同学：

```bat
:: 1. 克隆仓库
git clone https://github.com/<你的账号>/luggage-agent.git
cd luggage-agent

:: 2. 建环境
conda create -n lora python=3.10 -y
conda activate lora
pip install torch==2.7.1+cu128 --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt

:: 3. 下载基座模型（7.7GB，各自下各自的，仓库里没有）
set HF_ENDPOINT=https://hf-mirror.com
set HF_HUB_DISABLE_XET=1
hf download Qwen/Qwen2.5-VL-3B-Instruct --local-dir vlm/qwen2.5-vl-3b-instruct

:: 4. 直接用归档数据复现训练
python train.py --data data/archive/v2-20261004/train.jsonl ^
    --model vlm/qwen2.5-vl-3b-instruct --out output/lora-adapter --epochs 8 --lr 1e-4
```

---

## 怎么分享训练好的 LoRA 适配器

适配器 **148MB**，`.gitignore` 已经排除了 `output/`，**不要直接塞进 git**（会让仓库体积爆炸）。

三种推荐方式，选一个：

| 方式 | 操作 |
|---|---|
| **GitHub Releases**（推荐） | 仓库页面 → Releases → Create a new release → 上传 `adapter_model.safetensors` 作为附件 |
| 网盘 | 打包 `.zip` 发链接，配一句 sha256 便于校验完整性 |
| Git LFS | `git lfs install` + `git lfs track "*.safetensors"`，适合要版本管理的场景 |

---

## 日常协作命令速查

```bat
git pull                          :: 拉最新代码（每天开工先做）
git add -A                        :: 暂存改动
git commit -m "说明改了什么"        :: 提交
git push                          :: 推送
git status                        :: 看当前状态
```

> **经验**：`pull` 一定要先做。组员改了同一个文件时，`push` 会被拒绝，
> 需要先 `pull` 合并冲突再推。

---

## 这次会推上去的内容

| 类别 | 文件 |
|---|---|
| 核心代码 | `train.py` `infer.py` `validate.py` `normalize.py` `prompt.py` `gdino_detect.py` `gdino_to_train.py` `download_model.py` |
| 清单配置 | `taxonomy.json`（28 项 + 别名） |
| 标注平台 | `anno-tool/`（FastAPI + Vue） |
| **数据归档** | `data/archive/v2-20261004/` — 11 张原图、11 张框可视化图、3 个 CSV 表格、`train.jsonl`、`MANIFEST.md` |
| 评估结果 | `validate_report.json` |
| 文档 | `README.md` `本机部署步骤清单.md` `标注方案_PPT说明.md` `清单v2对照分析.md` `同步文档_同学版.md` |
| 工具脚本 | `_scripts/` |

**不会推上去的**（已在 `.gitignore` 排除）：

- `vlm/` — 7.7GB 基座权重（每人各自下载）
- `output/` — 148MB LoRA 适配器（走 Releases 分享）
- `data/raw/` — 原始照片
- `data/labeled/_backup/`、`overlays/`、`uploads/` — 中间产物（overlays 已进归档）
- `*.log`、`*.bak`、`__pycache__/`、`.workbuddy/`、`_trash/`
