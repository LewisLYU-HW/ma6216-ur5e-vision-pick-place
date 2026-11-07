# MA6216 · Model-free 6D 视觉操作

**分支：`feat/model-free-manipulation`** · UR5e + Robotiq 2F-85 · MuJoCo · 官方 FoundationPose

本分支接续小组原有抓放与码垛仿真，实现三个任务：**视觉装配与自动恢复、部分遮挡清理与换抓姿、运动目标跟踪与预测抓取**。
先从标定 RGB-D 参考图重建工件，再用官方 FoundationPose 估计三维位置和朝向，驱动真实接触下的夹持、重定位和插装。
颜色仅用于前景分割；抓取、翻转和装配使用完整 **6D pose（三维位置＋三维朝向）**。

[演示视频](docs/videos/README.md) · [详细复现与限制](docs/MODEL_FREE_TASKS.md) · [实测数据](docs/results/model-free-tasks.json) · [安装](docs/SETUP.md) · [小组 PR #3](https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/pull/3)

## 三个任务与视频

| 任务 | 机器人做什么 | 6D pose 用在哪里 | 全景＋腕部录像 |
|---|---|---|---|
| **装配与恢复** `assembly` | 从倾斜料架取件；夹具移位后触发接触保护，撤退、重定位并重试 | 完整抓取变换、腕部朝向校正、工件与夹具的相对位姿 | [观看视频](docs/videos/model-free-assembly-overview-wrist.mp4) |
| **遮挡与重抓** `clutter` | 搬走障碍物；侧抓平躺工件，翻转放上支架，松爪后换抓姿并插装 | 识别平躺姿态、构造侧抓关系、翻转与重新抓取 | [观看视频](docs/videos/model-free-clutter-overview-wrist.mp4) |
| **运动目标抓取** `conveyor` | 连续观察送料台上的工件，预测接触位置，在台面运动时夹取并插装 | 带时间戳的位姿跟踪、速度估计、接触时刻预测和腕部校正 | [观看视频](docs/videos/model-free-conveyor-overview-wrist.mp4) |

另有 [关闭自动恢复的失败对照](docs/videos/model-free-no-recovery-overview-wrist.mp4)：相同初始场景和夹具扰动，第一次接触保护后停止。
四段 H.264 视频均直接保存在仓库中；点击可查看或下载。每段左侧为全景，右侧为腕部视角。

![遮挡任务中，机器人将翻转后的工件放上重抓支架；左全景、右腕部](docs/media/model-free-regrasp.png)

上图取自已验证的遮挡重抓录像，展示放上支架、准备松爪换抓姿的阶段。

## 本分支增加了什么

| 原项目基础 | 本分支扩展 |
|---|---|
| RGB-D、颜色 mask、已知工件 CAD 输入 FoundationPose | 标定参考 RGB-D → 官方 Neural Object Field → 重建表面，无需输入工件 CAD |
| 固定相机定位后抓放、码垛 | 固定相机初定位＋腕部近景重定位，校正夹持关系与朝向歧义 |
| 预先定义的静态放置目标 | 夹具移位后的接触保护与重试、支架换抓姿、运动目标预测抓取 |
| 物理抓放及支撑验收 | 分别记录感知误差与最终落座误差，并提供恢复关闭对照 |

机械臂、夹爪、标定与基础抓放来自原项目；本分支接入并调用官方 FoundationPose，重建与位姿网络的来源见 [第三方说明](THIRD_PARTY_NOTICES.md)。
原阶段的功能、课程任务对应关系和实验记录见 [原项目总览](docs/BASELINE_PROJECT.md)。

## 系统流程与 Model-free 的含义

```mermaid
flowchart LR
  R[标定参考 RGB-D] --> N[官方 Neural Object Field]
  N --> M[重建表面与纹理]
  C[固定相机 / 腕部 RGB-D] --> P[官方 FoundationPose]
  M --> P
  P --> T[工件完整 6D 位姿]
  F[RGB-D ArUco 夹具定位] --> A[抓取变换与碰撞规划]
  T --> A
  A --> E[关节执行器与物理夹持]
  E --> W[腕部观察与接触监控]
  W --> P
  W --> A
```

这里采用 FoundationPose 的 **few-shot model-free** 路线：每件工件使用 24 张参考 RGB-D、mask 和扫描相机标定，先重建，再调用官方 `register()` / `track_one()`。
工件感知与碰撞规划使用 [仓库内的重建模型包](assets/reconstructed/README.md)，可以直接复现任务；也可按 [重建说明](docs/MODEL_FREE_TASKS.md)自行生成模型。

夹具几何、标记安装关系和操作坐标系由任务定义。当前参考扫描与腕部手眼安装采用理想合成标定；固定任务相机使用棋盘格估计标定。
工件由摩擦和双侧指垫接触保持，操作期间不通过写物体位置实现搬运。

## 已验证的结果

以下为本工作站 **seed 0 的三个完整视觉演示及一个失败对照**。位置与角度误差指松爪、稳定后的物理落座结果，视觉估计误差单独记录。

| 场景 | 验收结果 | 最终位置误差 | 最终角度误差 | 关键观测 |
|---|---|---|---|---|
| 装配与恢复 | 第二次插装成功 | 0.19 mm | 0.35° | 首次约 8 N 力增量触发保护，腕部重定位后重试 |
| 部分遮挡与重抓 | 成功 | 2.88 mm | 0.39° | 清障后前景像素 4478 → 5360；完成三次实际夹持 |
| 运动目标抓取 | 成功 | 0.54 mm | 0.43° | 视觉速度约 3.99 mm/s，送料设定为 4 mm/s |
| 关闭自动恢复 | 预期失败 | — | — | 首次保护后停止，无第二次插装 |

三个成功运行均通过槽底支撑和松爪后稳定性验收；7 项回归检查通过。数据与视频对应关系见 [结果摘要](docs/results/model-free-tasks.json) 和 [视频校验清单](docs/videos/manifest.json)。
这些结果仅覆盖列出的仿真场景；遮挡示例的最小槽壁余量约 0.01 mm。送料采用短行程移动台，IK 仍为同步规划，尚未验证随机场景稳健性、硬实时或真机效果。

## 组员快速开始

首次下载时直接指定本分支：

```bash
git clone --branch feat/model-free-manipulation https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place.git
cd ma6216-ur5e-vision-pick-place
```

已有本地仓库时，在仓库目录切换：

```bash
git fetch origin
git switch feat/model-free-manipulation
git pull --ff-only
```

先按 [SETUP.md](docs/SETUP.md) 配置仿真环境、Menagerie 机器人模型、官方 FoundationPose 与权重。
下面的 `python` 使用仿真环境，`FP_PYTHON` **需替换为你已配置的 FoundationPose 环境的 Python 路径**；两个环境可以分开。
默认官方源码目录为 `third_party/FoundationPose`，其他位置用 `--foundationpose-repository` 指定。使用附带模型包运行任务无需重新训练重建模型。

```bash
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl
FP_PYTHON=/path/to/foundationpose/env/bin/python
RUN_DIR="artifacts/model_free_$(date +%Y%m%d_%H%M%S)"

python scripts/run_model_free_task.py --task assembly \
  --plug-model assets/reconstructed/plug \
  --foundationpose-python "$FP_PYTHON" \
  --output "$RUN_DIR/assembly" --record

python scripts/run_model_free_task.py --task clutter \
  --plug-model assets/reconstructed/plug --blocker-model assets/reconstructed/blocker \
  --foundationpose-python "$FP_PYTHON" \
  --output "$RUN_DIR/clutter" --record

python scripts/run_model_free_task.py --task conveyor --belt-speed .004 \
  --plug-model assets/reconstructed/plug \
  --foundationpose-python "$FP_PYTHON" \
  --output "$RUN_DIR/conveyor" --record
```

每个任务输出 `summary.json`、RGB-D 观测、推理记录、运动日志及 `video/overview_wrist.mp4`。
在 Linux 打开录屏或运行回归检查：

```bash
xdg-open "$RUN_DIR/assembly/video/overview_wrist.mp4"
python scripts/check_model_free_tasks.py
```

`--disable-recovery` 用于恢复关闭对照；`--ground-truth` 是明确标记的物理控制诊断，不计作视觉结果。每次运行选择新输出目录。
详细环境版本、重建命令、传感器与验收判据见 [MODEL_FREE_TASKS.md](docs/MODEL_FREE_TASKS.md)。

## 从哪里读代码

| 文件 | 职责 |
|---|---|
| [run_model_free_task.py](scripts/run_model_free_task.py) | 三任务的观测、抓取、重抓、恢复和验收流程 |
| [capture_model_free_references.py](scripts/capture_model_free_references.py)、[reconstruct_neural_object.py](scripts/reconstruct_neural_object.py) | 参考图采集与官方 Neural Object Field 重建 |
| [serve_model_free_pose.py](scripts/serve_model_free_pose.py) | 独立 GPU 进程，调用官方位姿注册和跟踪 |
| [task_perception.py](src/ma6216/task_perception.py)、[online_pose.py](src/ma6216/online_pose.py) | RGB-D、腕部相机、夹具定位、时间戳与运动预测 |
| [task_control.py](src/ma6216/task_control.py) | 抓取变换、IK、碰撞检查、力保护与物理执行 |
| [advanced_scene.py](src/ma6216/advanced_scene.py) | 三个工作场景、重抓支架、夹具扰动和移动送料台 |
| [check_model_free_tasks.py](scripts/check_model_free_tasks.py) | 模型来源、预测时间戳、抓取方向与物理验收的回归检查 |

## 其他文档与历史阶段

| 入口 | 内容 |
|---|---|
| [详细复现](docs/MODEL_FREE_TASKS.md) / [实测数据](docs/results/model-free-tasks.json) | 当前分支的完整方法、命令、假设和验证记录 |
| [视频目录](docs/videos/README.md) | 三项新任务、恢复失败对照及原定向入槽录像 |
| [原项目总览](docs/BASELINE_PROJECT.md) / [版本选择](docs/VERSIONS.md) | v0.2 三工件、v0.3 多物品、v1.0 视觉码垛及课程任务对应关系 |
| [6D 定向入槽](docs/POSE_INSERTION.md) | 本分支继承的 Model-based 倾斜抓取与 yaw-only 对照 |
| [安装](docs/SETUP.md) / [小组协作](docs/TEAM_WORKFLOW.md) / [第三方来源](THIRD_PARTY_NOTICES.md) | 环境、分支与提交流程、官方依赖和资产来源 |

代码与演示位于小组原仓库的 `feat/model-free-manipulation` 分支，对应 [草稿 PR #3](https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/pull/3)。
