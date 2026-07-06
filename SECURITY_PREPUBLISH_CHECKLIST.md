# 开源发布前安全清单（SECURITY PRE-PUBLISH CHECKLIST）

> 本文件是把 VidSnap 仓库转为 **public 之前必须完成** 的止血清单。
> 背景：真实密钥曾被提交进 git，`.env` 虽已从 HEAD 删除，但仍存在于**历史 blob** 中；
> 且其中部分密钥与当前磁盘上的 `.env` 一致，即**仍然有效**。
> 在下面第 1、2 步完成前，**不要** 把仓库设为 public。

---

## 0. 已由代码改动完成的部分（无需你手动做）

- [x] 加入 `LICENSE`（MIT）。
- [x] 移除源码中写死的 JWT 默认密钥常量：`config.py` / `auth.py` 统一到 `settings.JWT_SECRET`，
      未设环境变量时生成进程级随机密钥（生产必须用环境变量注入固定值）。
- [x] CORS 不再写死 `allow_origins=["*"]`，改由 `CORS_ALLOW_ORIGINS` 环境变量控制（默认仅本地来源）。
- [x] `.gitignore` 补充忽略个人笔记（`note_output.md` / `notes_*.md` / `*_图文版.md`）与 `.qoder/`、`.understand-anything/`。

---

## 1. 轮换（Rotate）所有泄露密钥 —— 必须你亲自在各控制台操作

这些密钥已进入 git 历史，视为**已泄露**，必须作废旧值、生成新值。轮换后只把新值放进**未被追踪的** `.env`。

- [ ] **阿里云 AccessKey 对**（`ALIYUN_ACCESS_KEY_ID` / `ALIYUN_ACCESS_KEY_SECRET`）——最高优先级，账号级凭证。
      建议直接删除旧 AccessKey，新建一个**最小权限**（仅目标 OSS bucket 读写）的 RAM 子账号 AccessKey。
- [ ] **DashScope / Qwen key**（`QWEN_API_KEY` / `TRANSCRIPT_SERVICE_API_KEY`）。
- [ ] **Supabase**：`SUPABASE_SERVICE_KEY`（service_role，绕过 RLS，务必轮换）+ anon / publishable key。
- [ ] **Google OAuth**：`GOOGLE_OAUTH_CLIENT_SECRET`（在 Google Cloud Console 重置）。
- [ ] **HuggingFace**：`HF_TOKEN`。
- [ ] **Google/YouTube API key**：`YOUTUBE_API_KEY`。
- [ ] **Supadata**：`SUPADATA_API_KEY`。
- [ ] **应用 `SECRET_KEY`**。
- [ ] **生产 `JWT_SECRET`**：用 `python -c "import secrets;print(secrets.token_urlsafe(48))"` 生成，仅通过环境变量/Secret Manager 注入。
- [ ] （可选）本地 Postgres 口令 `vidsnap_secret_2024`：仅 localhost 容器使用，风险低；如生产用则改掉。

## 2. 清理 git 历史（filter-repo 方案）—— 必须你亲自做

> 你选择的是「清现有仓库历史」。以下用 `git-filter-repo`（比 BFG 更可靠）。先在**克隆副本**上操作、确认无误再动主仓库。

```bash
# 安装（macOS）
brew install git-filter-repo

# 0) 先做一个裸镜像备份，避免误操作不可逆
git clone --mirror . ../vidsnap-backup.git

# 1) 从所有历史中彻底移除三个 .env 文件
git filter-repo --path .env --path backend/.env --path frontend/.env --invert-paths

# 2) filter-repo 会移除 origin，重新指向远端
git remote add origin https://github.com/PCcoding666/my_youtube_summarizer.git

# 3) 校验：下面两条应当【无任何输出】
git log --all --full-history -- .env backend/.env frontend/.env
git rev-list --all | xargs -I{} git grep -lI -e "sk-proj-" -e "LTAI" -e "hf_" {} 2>/dev/null

# 4) 确认干净后强推所有分支与标签（会重写远端历史）
git push origin --force --all
git push origin --force --tags
```

- [ ] 已在备份副本验证历史中不再含 `.env` / 任何密钥字符串。
- [ ] 已 force-push；**通知所有协作者重新 clone**（旧 clone 仍含泄露历史）。
- [ ] 如该仓库曾被 fork 或曾短暂 public：假设已被抓取，第 1 步的轮换是唯一可靠止血。

## 3. 发布前最后检查

- [ ] `git ls-files | grep -iE "\.env$"` 无输出（`.env` 不在追踪中）。
- [ ] `.env.example` / `.env.prod.example` 仅含占位符（已确认）。
- [ ] `docs/getting-started.md` 中的个人绝对路径 `/Users/chengpeng/...` 已改为相对/占位（见 M2，可选）。
- [ ] 生产环境已设置 `JWT_SECRET`、收紧 `CORS_ALLOW_ORIGINS`、注入而非硬编码所有密钥。
- [ ] （建议）接入 GitHub Secret Scanning / push protection，防止再次误提交。
