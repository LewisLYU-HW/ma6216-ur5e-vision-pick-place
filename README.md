# MA6216 UR5e Vision-Guided Manipulation

面向 MA6216 Project 1 的视觉引导机器人抓放与码垛仿真。UR5e + Robotiq 2F-85 在 MuJoCo 中完成接近、夹取、抬升、横向搬运、放置和撤离，并支持四料块、两列两层的物理码垛。固定 RGB-D 相机提供观测，OpenCV 估计相机参数并分割目标，FoundationPose Model-based 估计物体位姿；坐标变换与 Python 运动规划将视觉结果转换为经过碰撞检查的关节轨迹。

本分支 `feat/model-free-manipulation` 新增 **参考 RGB-D 重建驱动的装配恢复、遮挡重抓和运动目标抓取**。
工件感知与规划使用官方 Neural Object Field 的重建表面，无需输入工件 CAD。
[三任务运行说明与适用范围](docs/MODEL_FREE_TASKS.md) · [演示视频](docs/videos/README.md)

![FoundationPose 视觉引导四料块两列两层物理码垛](docs/media/palletizing-final.png)

[码垛录像](docs/media/palletizing.mp4) · [码垛复现](docs/PALLETIZING.md) · [Project 1 任务与选型](docs/PROJECT1_PALLETIZING.md) · [多物品抓放视频](docs/media/diverse-object-pick-place.mp4) · [安装与复现](docs/SETUP.md) · [小组协作](docs/TEAM_WORKFLOW.md)

## FoundationPose 接入与来源

本项目通过适配层直接调用 [NVIDIA FoundationPose 官方实现](https://github.com/NVlabs/FoundationPose/tree/a1b694b83e633c2cb6115b9063d940a687759392)和预训练网络，采用 Model-based 方法。MuJoCo 渲染的 RGB、米制深度、图像 mask、估计内参和物体 CAD 输入官方模型，得到相机坐标下的物体位姿，再经估计外参变换为机器人抓取目标。

- [FoundationPoseAdapter](src/ma6216/foundationpose.py#L203) 导入官方 `estimater.py`，创建 `FoundationPose`、`ScorePredictor` 和 `PoseRefinePredictor`，调用 `register()`；序列推理也支持 `track_one()`。
- [推理入口](scripts/run_foundationpose.py)与[多物体流程](scripts/run_multi_pick_place.py)连接仿真观测和官方推理；[坐标转换](src/ma6216/vision.py#L67)把估计物体位姿交给机器人规划。
- 本仓库提供标定、分割、数据适配、坐标变换、抓取配置、运动规划和物理验证。官方源码与预训练权重作为外部依赖加载，未随本仓库打包分发；机器人模型同样从 Menagerie 加载。

调用链、权重位置、运行记录和安装方式见 [FoundationPose 集成说明](docs/FOUNDATIONPOSE_INTEGRATION.md)。使用 `--ground-truth` 的物理对照会跳过 FoundationPose。

## 按阶段选择版本

| 固定版本 | 自动抓放内容 | 入口 |
|---|---|---|
| [v0.2.0：三工件](https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/releases/tag/v0.2.0) | 绿色、橙色、紫色异形工件 | `scripts/run_multi_pick_place.py` |
| [v0.3.0：多种类物品](https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/releases/tag/v0.3.0) | 锤子、红球、带孔螺母 | 同一入口加 `--collection diverse` |
| [v1.0.0：视觉码垛](https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/releases/tag/v1.0.0) | 四料块、两列两层，包含指定下层支撑与整垛稳定性验收 | `scripts/run_palletizing.py` |

`main` 保持最新整合代码；各固定版本提供源码和打印文件下载，原 Pick-and-Place 入口继续保留。绿色螺丝刀仅出现在四物件预览中，尚未验证抓取。组员按阶段拉取、运行和打印交接的完整命令见 [VERSIONS.md](docs/VERSIONS.md)。

## 分支扩展：Model-free 三任务

| 任务 | 演示重点 | 全景＋腕部视频 |
|---|---|---|
| 视觉装配与恢复 | 腕部重定位、夹具移位、接触保护后自动重试 | [装配恢复](docs/videos/model-free-assembly-overview-wrist.mp4) |
| 遮挡清理与换抓姿 | 搬走障碍物、侧抓翻转、支架松爪、重新抓取并插装 | [遮挡重抓](docs/videos/model-free-clutter-overview-wrist.mp4) |
| 运动目标抓取 | 图像位姿跟踪、预测接触位置、移动中夹取并插装 | [运动目标](docs/videos/model-free-conveyor-overview-wrist.mp4) |
| 自动恢复关闭对照 | 同样的夹具扰动，接触保护触发后停止 | [失败对照](docs/videos/model-free-no-recovery-overview-wrist.mp4) |

视频直接保存在仓库中，含同步腕部视角。代码入口为
`scripts/run_model_free_task.py --task assembly|clutter|conveyor`；
可直接使用 [RGB-D 重建模型包](assets/reconstructed/README.md)。
模型来源、环境、完整命令、夹具定位、力保护和有限场景的实测证据见
[MODEL_FREE_TASKS.md](docs/MODEL_FREE_TASKS.md)。
这里的 model-free 仍需要标定参考图；夹具几何与标记安装关系已知。

## 分支扩展：6D 位姿引导的定向入槽

`feat/6d-pose-insertion` 接续 `v1.0.0`：沿用缺角料块，从带 roll/pitch 的
倾斜料架取件，使用官方 FoundationPose 的完整旋转搜索和三维抓取变换，
校正朝向后放入匹配浅槽。颜色只提供前景 mask，验收包括三维姿态、位置、
实际槽底支撑和五秒稳定性。提供 `yaw-only` 对照及物理验收正/负例。
录制时增加 `--record-view both` 可同步保存全景和腕部视角。
这是独立分支任务，尚未发布新版本标签。

```bash
python scripts/run_pose_insertion.py --layout 1 \
  --output artifacts/pose_insertion_01 --record --viewer
```

运行条件、倾斜范围、接触设置、完整/简化姿态对照及实测范围见
[POSE_INSERTION.md](docs/POSE_INSERTION.md)。

演示视频已随仓库提供（H.264 MP4，点击查看或下载）：

- [全景＋腕部同步演示](docs/videos/pose-insertion-overview-wrist.mp4)
- [独立腕部视角](docs/videos/pose-insertion-wrist.mp4)
- [完整 6D 位姿全景演示](docs/videos/pose-insertion-full.mp4)
- [yaw-only 落座失败对照](docs/videos/pose-insertion-yaw-only-failure.mp4)

场景、时长与文件校验信息见 [视频说明](docs/videos/README.md)。

## 运行视觉码垛

在已有环境的 WSL 项目目录运行：

```bash
conda activate foundationpose
python -u scripts/run_palletizing.py \
  --output "artifacts/pallet_$(date +%Y%m%d_%H%M%S)" --record --viewer
```

使用默认相机的估计标定样例。`--layout 1` 验证另一组位置和朝向；新机器先按安装说明配置依赖。平顶料块为 80×50×40 mm，打印四份，文件在 `assets/palletizing`。已完成两组完整视觉试验，各 4/4；完整指标、层间支撑判据和复现标定命令见 [PALLETIZING.md](docs/PALLETIZING.md)。

## Project 1 实现情况

| 课程任务 | 当前实现与证据 |
|---|---|
| Task 1：技术选型 | 采用 MuJoCo、OpenCV 和 FoundationPose Model-based；文献比较、方案选择和实验设计见 [课程对应说明](docs/PROJECT1_PALLETIZING.md)，来源和许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。最终展示由小组整理。 |
| Task 2：虚拟相机内参标定 | 1280 × 960 固定 RGB-D 相机；从渲染棋盘角点估计内参，以留出图像和重投影误差评价。 |
| Task 3：相机—机器人标定 | 固定 eye-to-hand 配置；估计相机到机器人安装坐标的变换，并独立验证误差。 |
| Task 4：物体定位 | 从 RGB 图像生成颜色分割 mask；覆盖异形工件、锤子、球体和螺母，并记录多物体场景的 mask IoU。 |
| Task 5：位姿估计 | RGB-D、mask 与已知 CAD 输入 FoundationPose；将相机坐标下的物体位姿变换到机器人安装坐标，并评价位置、方向及几何对称性。 |
| Task 6：机器人操作 | 根据估计位姿和 CAD 抓取关系执行离线 IK、载荷碰撞检查、朝向对齐与物理抓放；码垛增加指定下层接触力、质心支撑余量、层高及五秒稳定性验收。 |

## 三工件扩展与打印交接（2026-11-06）

同一场景中同时存在绿色双斜角工件、橙色斜肩棱柱和紫色渐缩切角块。完整视觉流程在一次固定布局中完成连续 3/3 抓放，三件分别放入托盘内的目标位置。[运行方法与实测范围](docs/MULTI_OBJECT.md) · [视频](docs/media/multi-object-pick-place.mp4)。

三个模型的毫米制 STL、米制 OBJ 和尺寸清单已放在 `assets/printable`。[3D 打印及真机交接说明](docs/PRINTING.md) 说明单位、原点和实物测量。

## 球体、带孔件与扫描工具

新增独立的 `--collection diverse` 场景：真实扫描锤子、红球和中空六角螺母在同一次视觉场景中连续抓放 3/3；十字螺丝刀另外提供模型预览和打印副本，尚未验证抓取。[来源、运行和实测范围](docs/OBJECT_LIBRARY.md) · [四物件预览](docs/media/object-library-preview.png) · [抓放录像](docs/media/diverse-object-pick-place.mp4)。

新增打印文件位于 `assets/printable_library`。扫描工具来自 Google Scanned Objects 的 MuJoCo 转换库，以原尺寸 50% 导入；来源、许可和文件哈希随资产保存。旧三工件场景和原打印导出目录继续保留。

## 开始运行

先在 WSL 或 Linux 中克隆。

```bash
cd ~/projects
git clone https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place.git
cd ma6216-ur5e-vision-pick-place
```

新机器先按 [SETUP.md](docs/SETUP.md) 下载机器人模型和安装环境。模型、FoundationPose 源码及网络权重单独获取，路径可由环境变量配置。

已有环境和模型的组员可以先自检。

```bash
conda activate foundationpose
python scripts/check_setup.py --vision
```

完整视觉试验包含重新标定和绿色工件抓放。成功标定后才执行下一步。

```bash
RUN="artifacts/demo_$(date +%Y%m%d_%H%M%S)"
python -u scripts/run_camera_calibration.py --output "$RUN/calibration" && python -u scripts/run_front_pick_place.py   --calibration "$RUN/calibration/estimated"   --output "$RUN/pick_place" --record --viewer
```

在无窗口终端运行时可去掉 `--viewer`。结果写入本轮 `summary.json`、`motion/samples.csv` 和 `motion/physical_pick_place.mp4`。每轮选择新输出目录。增加 `--xy .44 -.19 --yaw-deg 15` 可以改变工件摆放，`--target cube` 使用红方块。

仓库提供 `demo_data/calibration/estimated` 下的估计参数，匹配默认相机，用于快速复现。修改相机后重新执行标定。命令省略 `--calibration` 时默认使用该样例。

CPU 机器可按安装说明运行 `--ground-truth` 物理对照，它会明确记录该控制来源。完整视觉演示需要可工作的 FoundationPose CUDA 环境。

## 代码地图

| 位置 | 用途 |
|---|---|
| `scripts/run_front_pick_place.py` | 单物体视觉抓放入口，支持绿色工件与红方块 |
| `scripts/run_multi_pick_place.py` | 三工件与多种类物品的连续视觉抓放 |
| `scripts/run_palletizing.py`、`src/ma6216/palletizing.py` | 四料块码垛、层位、抓取关系、带载规划与支撑验收 |
| `scripts/check_palletizing.py`、`export_pallet_blocks.py` | 悬空负例/物理支撑检查、料块打印和感知模型导出 |
| `scripts/preview_object_library.py` | 包含螺丝刀的四物件待机预览 |
| `scripts/run_camera_calibration.py` | 棋盘格采图、标定和独立评价 |
| `scripts/run_foundationpose.py` | 对保存的 RGB-D、mask 和网格执行注册或跟踪 |
| `src/ma6216/workcell.py`、`scene.py` | 工作站、相机和标定板 |
| `src/ma6216/workpiece.py` | 绿色工件几何、米制 OBJ 和 mask |
| `src/ma6216/parts.py`、`object_library.py`、`multi_object.py` | 多物体几何、碰撞模型、抓取配置及场景 |
| `scripts/export_workpieces.py`、`export_library_objects.py` | 米制感知网格和毫米制打印文件导出 |
| `src/ma6216/foundationpose.py`、`vision.py` | 官方推理适配、观测和坐标链 |
| `src/ma6216/direct_route.py`、`motion.py` | 离线 IK、路径检查和物理执行 |
| `scripts/check_setup.py` | 仿真或视觉环境自检 |
| `scripts/capture_vision_dataset.py`、`replay_vision_trials.py`、`evaluate_vision.py` | 批量采集、对照和评价 |
| `docs/results/` | 小型实测摘要及指标定义 |

## 实验记录

以下是 2026-11-04 至 2026-11-06 在开发机执行得到的结果，样本和评价范围按行列出。

| 试验 | 实测结果 |
|---|---|
| 相机内参 | 19 张有效训练图，4 张有效留出图，留出每图平均 RMSE 0.050 px |
| 相机外参 | 5 张训练、5 张独立验证图，固定外参复验 RMSE 0.074 px，参考误差 4.25 mm / 0.122° |
| 绿色工件单物体抓放 | 两种摆放 2/2，位姿误差 4.12–4.32 mm / 0.56–0.91°，落盘中心误差 0.25–0.82 mm |
| 绿色、橙色、紫色三工件 | 一次固定布局的连续视觉抓放 3/3；最终槽位 XY 误差分别为 1.288、1.000、1.098 mm |
| 锤子、球体、带孔螺母 | 一次固定布局的连续视觉抓放 3/3；最终槽位 XY 误差分别为 2.500、2.225、0.713 mm |
| 四料块视觉码垛 | 两种布局各 4/4，整垛 2/2；名义槽位 XY 误差 1.15–5.37 mm，五秒最大漂移 0.16 mm |

每次抓取前从 RGB-D 图像估计目标位姿，执行过程中监测关节误差和接触；多物体场景在两次抓取之间重新观测剩余目标。当前采用已知 CAD、受控颜色和预先定义的抓取部位，部分模型使用近似直立或平放先验。球体不报告唯一朝向，螺母按 60° 对称性评价。上述结果的适用范围和失败记录见 [MULTI_OBJECT.md](docs/MULTI_OBJECT.md)、[OBJECT_LIBRARY.md](docs/OBJECT_LIBRARY.md) 及 [实测摘要](docs/results/)。

十字螺丝刀目前仅验证模型预览和打印文件导出。真机相机标定、TCP、坐标和控制接口需要由硬件组实测适配；仓库中的质量、摩擦和软接触参数为仿真假设。

## 小组开发

组员为各自任务创建分支，通过 Pull Request 互相检查。提交源码、说明和小型结果摘要。每轮原始 RGB-D、录屏、权重、外部仓库和本地环境写入 Git 忽略目录。仓库选取了抓放场景截图、演示视频和实测摘要，便于在安装环境前了解项目结果。

第三方来源和许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。FoundationPose 官方源码、预训练权重与 Menagerie 机器人模型按 [SETUP.md](docs/SETUP.md) 单独获取，本仓库的适配代码在运行时调用这些依赖。自有代码的对外开源许可由小组确认。
