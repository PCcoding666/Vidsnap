# Git 子模块工作流规则

## 项目结构
- 主项目：`my_youtube_summarizer`
- 前端子模块：`frontend` (链接到 `learn-video-talk` 仓库)
  - 仓库地址：https://github.com/PCcoding666/learn-video-talk

## 场景 1：Lovable 更新了 UI

当 Lovable 将更改推送到 `learn-video-talk` (GitHub) 后，需要在 Qoder 中执行以下步骤拉取更新：

```bash
# 1. 进入子模块目录，拉取子模块的更新
cd frontend
git pull origin main  # 或者 Lovable 使用的主分支名

# 2. 回到主项目，告诉主项目子模块有更新
cd ..
git add frontend
git commit -m "Update frontend submodule from Lovable"
git push origin 0.1.2  # 或当前工作分支
```

## 场景 2：在 Qoder 中修改了前端逻辑

当你在 Qoder 中修改了 `frontend` 目录里的代码（例如添加 API 调用），需要执行以下步骤推送更新：

```bash
# 1. 进入子模块目录，提交并推送你的逻辑代码
cd frontend
git add .
git commit -m "feat: Add backend API calls"
git push origin main  # 推送到 learn-video-talk

# 2. 回到主项目，告诉主项目你更新了子模块的引用
cd ..
git add frontend
git commit -m "Update frontend submodule with new logic"
git push origin 0.1.2  # 或当前工作分支
```

## 场景 3：克隆项目时初始化子模块

当其他人克隆 `my_youtube_summarizer` 项目时，需要执行以下命令初始化子模块：

```bash
# 方法 1: 克隆时直接初始化子模块
git clone --recursive https://github.com/PCcoding666/my_youtube_summarizer.git

# 方法 2: 克隆后手动初始化子模块
git clone https://github.com/PCcoding666/my_youtube_summarizer.git
cd my_youtube_summarizer
git submodule init
git submodule update
```

## 注意事项

1. **避免嵌套仓库错误**：永远不要将远端仓库作为普通目录克隆到项目中，必须使用 `git submodule add` 添加
2. **子模块独立性**：子模块有自己的 Git 历史，在子模块目录内的操作会影响子模块仓库
3. **主项目引用**：主项目只记录子模块的当前 commit SHA，需要手动更新引用
4. **推送顺序**：先推送子模块更改，再推送主项目的子模块引用更新
5. **分支管理**：子模块可能使用不同的分支名（如 `main`），主项目使用 `0.1.2`

## 查看子模块状态

```bash
# 查看子模块状态
git submodule status

# 查看子模块配置
cat .gitmodules
```
