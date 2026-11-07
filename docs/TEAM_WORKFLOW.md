# 小组 Git 协作

仓库 `LewisLYU-HW/ma6216-ur5e-vision-pick-place` 为公开仓库，所有人均可浏览和直接克隆。需要直接向仓库推送分支的组员，由所有者在 GitHub 的 Settings → Collaborators 中邀请并授予相应权限。

本仓库使用 `main` 保存最新整合代码、功能分支进行调试，并以 `v0.2.0`、`v0.3.0`、`v1.0.0` 固定三工件、多种类物品和码垛阶段。按阶段拉取和复现见 [VERSIONS.md](VERSIONS.md)。已有版本标签保持不变，后续功能另建分支并发布新版本。

## 首次拉取

仓库创建完成后，在 WSL 终端进入希望放项目的目录。下面按已确认的账号 `LewisLYU-HW` 和计划仓库名给出命令。若最终地址有调整，从 GitHub 的 Code 按钮复制 HTTPS 地址替换即可。

```bash
cd ~/projects
git clone https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place.git
cd ma6216-ur5e-vision-pick-place
```

随后按 [SETUP.md](SETUP.md) 安装外部模型及本地环境。克隆公开仓库无需登录。推送分支时使用各自 GitHub 账号登录，并需要仓库写入权限；也可以 Fork 后从个人仓库提交 Pull Request。

## 每次修改

先更新主分支，再为一件具体工作创建分支。未提交的修改应先提交到自己的分支或妥善保存。

```bash
git switch main
git pull --ff-only
git switch -c feat/yourname-camera-evaluation
```

修改后检查差异，按实际文件名逐项暂存。下面文件名是操作示例，替换为本轮自己的修改。

```bash
git status --short
git diff
git add src/ma6216/vision.py docs/SETUP.md
git commit -m "Improve camera observation validation"
git push -u origin feat/yourname-camera-evaluation
```

然后到 GitHub 打开 Pull request，说明改了什么、原因、运行命令和结果。另一位组员检查后合并。主分支用于能够复现的版本。处理合并冲突时保留双方需要的逻辑，再重新运行相关检查。

## 适合提交的内容

- 项目源码、运行入口、配置样例和安装说明。
- 少量明确用于复现的标定样例及小型指标摘要。
- 引用、方法说明与经小组确认可分享的图。

原始逐轮录屏、RGB-D 序列、下载的模型与权重、虚拟环境、缓存和本地凭据保存在 Git 忽略目录。
供课程展示的已验收视频直接提交到 `docs/videos`，采用 H.264 压缩并附时长、来源和哈希，方便组员克隆后观看。
自行生成、用于复现的少量重建表面可连同来源清单放入 `assets/reconstructed`。
其他大文件可放小组共享存储或 GitHub Release。实际提交范围以 `git status` 和 `git diff --cached` 检查结果为准。

## 问题反馈与版本标记

Issue 中写明当前提交 `git rev-parse --short HEAD`、平台、运行命令、异常文本和预期行为。先附具体日志片段，保留本地完整输出。完成一次可复现的阶段演示后，小组可为相应提交建立 `v0.1.0` 等 tag，并在 Release 说明测试场景和实际结果。上传到小组资料前检查截图和日志中是否含个人路径或凭据。
