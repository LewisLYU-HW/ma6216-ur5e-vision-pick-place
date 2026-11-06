# 小组 Git 协作

仓库建议命名为 `ma6216-ur5e-vision-pick-place`，描述 UR5e、视觉估计与物理抓放这一用途。初次共享可采用私有仓库，由仓库所有者在 GitHub 的 Settings → Collaborators 中邀请组员，各人接受邀请后即可拉取。账号拥有者、仓库可见性和最终地址以创建结果为准。

## 首次拉取

仓库创建完成后，在 WSL 终端进入希望放项目的目录。下面按已确认的账号 `LewisLYU-HW` 和计划仓库名给出命令。若最终地址有调整，从 GitHub 的 Code 按钮复制 HTTPS 地址替换即可。

```bash
cd ~/projects
git clone https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place.git
cd ma6216-ur5e-vision-pick-place
```

随后按 [SETUP.md](SETUP.md) 安装外部模型及本地环境。GitHub 身份验证使用个人账号的 GitHub CLI 登录或个人 SSH 配置，组员各自保管凭据。

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

每轮录屏、原始 RGB-D 序列、下载的模型与权重、虚拟环境、缓存和本地凭据应保存在 Git 忽略目录。需要给组员看大视频时，可放小组共享存储或 GitHub Release，并在 Issue/PR 中附链接。实际是否提交某个文件，以 `git status` 和 `git diff --cached` 检查结果为准。

## 问题反馈与版本标记

Issue 中写明当前提交 `git rev-parse --short HEAD`、平台、运行命令、异常文本和预期行为。先附具体日志片段，保留本地完整输出。完成一次可复现的阶段演示后，小组可为相应提交建立 `v0.1.0` 等 tag，并在 Release 说明测试场景和实际结果。上传到小组资料前检查截图和日志中是否含个人路径或凭据。
