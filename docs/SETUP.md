# 安装与复现

本项目有两条运行路线。物理对照可在普通 CPU 环境中执行。完整视觉路线还调用外部 FoundationPose 仓库及其 CUDA 依赖和权重。

已有机器的版本与运行结果见 [DEPENDENCIES.md](DEPENDENCIES.md)。以下新机器安装命令是按这些依赖整理的配置步骤，尚未在所有组员的硬件上逐一验证。

## 1. 拉取本仓库与模型

先按 [TEAM_WORKFLOW.md](TEAM_WORKFLOW.md) 拉取小组仓库，并在仓库根目录执行以下命令。第一次安装时，`third_party/mujoco_menagerie` 应是尚不存在的新目录。

```bash
mkdir -p third_party
git clone https://github.com/google-deepmind/mujoco_menagerie.git third_party/mujoco_menagerie
git -C third_party/mujoco_menagerie checkout fb36886b3023db08c198264e1e9956ab202c3e3b
export MA6216_MENAGERIE_DIR="$PWD/third_party/mujoco_menagerie"
```

Menagerie 提供 UR5e 和 Robotiq 2F-85 的 MJCF、外观网格和接触几何。固定提交有助于让组员使用同一版模型。下载路径由各人本地维护，生成文件和外部仓库放在 Git 忽略目录中。

## 2. 先跑物理对照

新建一个 Python 3.11 环境，安装本项目的仿真依赖。下面使用本机已验证的 Python 小版本。

```bash
conda create -n ma6216-sim python=3.11.17 pip
conda activate ma6216-sim
python -m pip install -r requirements-sim.txt
python scripts/check_setup.py --simulation-only
python -u scripts/run_front_pick_place.py \
  --ground-truth --output "artifacts/physical_$(date +%Y%m%d_%H%M%S)"
```

这轮用仿真物体位置作为明确标注的控制对照，验证模型、离线 IK、路径碰撞检查和物理夹持。它不加载 FoundationPose。控制台应最终输出 `"success": true`，结果写在本轮目录的 `summary.json`。运行命令默认无窗口，增加 `--viewer` 或 `--record` 时还需要可用的 OpenGL 显示或渲染环境。WSL 用户通常可使用 WSLg。

本项目直接使用 Python 和 MuJoCo，不依赖 ROS 2 或 MoveIt 2。

## 3. 准备 FoundationPose

已有可运行 FoundationPose 环境的组员，优先使用该环境并设置它的源码路径。

```bash
conda activate foundationpose
export MA6216_FOUNDATIONPOSE_DIR="$HOME/projects/FoundationPose"
python scripts/check_setup.py --vision
```

新机器可以把源码放在本仓库的 `third_party` 下。

```bash
git clone https://github.com/NVlabs/FoundationPose.git third_party/FoundationPose
git -C third_party/FoundationPose checkout a1b694b83e633c2cb6115b9063d940a687759392
export MA6216_FOUNDATIONPOSE_DIR="$PWD/third_party/FoundationPose"
```

按该提交的[官方安装说明](https://github.com/NVlabs/FoundationPose/tree/a1b694b83e633c2cb6115b9063d940a687759392)配置 Docker 或 Conda。需验证 PyTorch CUDA、PyTorch3D、NVDiffRast 和 `mycpp` 扩展。本项目所用 Model-based 路线不需要先搭建 Model-free 的 NeRF 重建流程。

从[官方权重入口](https://drive.google.com/drive/folders/1DFezOAD0oD1BblsXVxqDsl8fj0qzB82i?usp=sharing)下载并放到 FoundationPose 仓库，检查下列文件存在。

```text
weights/2023-10-28-18-33-37/model_best.pth
weights/2024-01-11-20-02-45/model_best.pth
```

权重按上游许可单独下载。GPU 环境安装完成后，也需能导入 MuJoCo。本机通过已有 `mujoco-env` 的包路径复用 MuJoCo，两个 Python 均为 3.11.17。新机器也可在配置好的 GPU 环境中安装 `mujoco==3.17.0`，再运行环境检查。`requirements-sim.txt` 面向新建的纯仿真环境，已有可工作的 GPU 环境应先检查缺项，再决定安装。

## 4. 重新标定并跑视觉抓放

下面的两条命令使用同一轮输出目录。第一步渲染棋盘格并估计内外参，第二步用这些估计参数完成绿色工件抓放。

```bash
conda activate foundationpose
python scripts/check_setup.py --vision
RUN="artifacts/vision_$(date +%Y%m%d_%H%M%S)"
python -u scripts/run_camera_calibration.py --output "$RUN/calibration" && \
python -u scripts/run_front_pick_place.py \
  --calibration "$RUN/calibration/estimated" \
  --output "$RUN/demo" --record
```

FoundationPose 的进度保存在本轮 `demo/foundationpose.log`。最终检查 `demo/summary.json` 的 `success` 和 `status`，并播放 `demo/motion/physical_pick_place.mp4`。`--viewer` 可显示实时窗口，窗口会在采图、推理和规划完成后打开。

`--xy .44 -.19 --yaw-deg 15` 对应第二组已验证工件摆放。`--target cube` 使用红方块。每轮用新输出目录，保留失败日志用于比较。

## 5. 常见问题

| 现象 | 检查方式 |
|---|---|
| 找不到 Menagerie | 检查 `MA6216_MENAGERIE_DIR` 下是否有 `universal_robots_ur5e/scene.xml` 和 `robotiq_2f85/2f85.xml`。 |
| 找不到 FoundationPose | 检查 `MA6216_FOUNDATIONPOSE_DIR/estimater.py`，官方文件名含 `estimater`。 |
| CUDA 不可用或扩展导入失败 | 在 GPU 环境运行 `python scripts/check_setup.py --vision`，按该机器的驱动、PyTorch/CUDA 组合修复官方依赖。 |
| 找不到 `cam_K.txt` | 确认标定步骤成功，且 `--calibration` 指向本轮 `calibration/estimated`。 |
| `FileExistsError` | 输出目录已被占用，为下一轮指定新目录。 |
| 只有 `success: false` | 查看对应 `summary.json` 的 `error`、`motion/result.json` 和 `foundationpose.log`，在 Issue 中附上文本和运行命令。 |
