# 依赖与已验证版本

下面记录的是原运行机器上于 2026-11-06 只读检查得到的版本。它是已运行组合的记录，新机器仍需按 GPU、驱动和编译工具链验证兼容性。

| 项目 | 已验证值 |
|---|---|
| 平台 | Windows 11 + WSL2，Ubuntu 24.04 |
| GPU | NVIDIA GeForce RTX 5060 Laptop GPU，8 GiB VRAM |
| 两个原 Conda 环境 | `foundationpose`、`mujoco-env` |
| Python | 两者均为 3.11.17 |
| MuJoCo | 3.17.0，安装在原 `mujoco-env` |
| NumPy | 2.4.6 |
| SciPy | 1.17.1 |
| OpenCV | `opencv-python` 分发版 5.0.0.93，`cv2.__version__` 为 5.0.0 |
| trimesh | 5.2.0 |
| PyTorch | 2.7.1+cu128 |
| torchvision | 0.22.1+cu128 |
| PyTorch CUDA runtime | 12.8，CUDA 可用 |
| Pillow | 13.0.0 |
| Menagerie 提交 | `fb36886b3023db08c198264e1e9956ab202c3e3b` |
| FoundationPose 提交 | `a1b694b83e633c2cb6115b9063d940a687759392` |

`requirements-sim.txt` 固定当前入口的直接仿真依赖。完整视觉环境还需要 PyTorch3D、NVDiffRast、Open3D、Warp 和原生 `mycpp` 等 FoundationPose 依赖，它们的安装以对应官方仓库提交为准。本仓库不把已配置 Conda 环境或编译后的二进制扩展作为依赖分发方式。

## 路径配置

| 环境变量 | 指向的内容 |
|---|---|
| `MA6216_MENAGERIE_DIR` | Menagerie 仓库根目录，内含 UR5e 和 Robotiq 模型目录。 |
| `MA6216_FOUNDATIONPOSE_DIR` | FoundationPose 仓库根目录，内含 `estimater.py` 与 `weights/`。 |
| `MA6216_MUJOCO_PYTHONPATH` | 可选，已有兼容 Python 的 MuJoCo `site-packages` 目录。新环境直接安装 MuJoCo 时可省略。 |

项目支持本仓库下的 `third_party` 布置。现有机器可继续使用 `~/mujoco/mujoco_menagerie` 和 `~/projects/FoundationPose`，避免重复下载。自行设置的环境变量仅影响当前终端，可以按个人习惯写入本地 shell 配置。

## 记录新实验

记录仓库提交、外部模型提交、Python 和主要包版本、GPU，以及执行命令。绿色工件当前使用基于已知水平桌面的直立先验搜索位姿，验收范围是固定相机、静止目标的已测场景。旧红方块的 6/6 与绿色工件的 2/2 属于不同实验组。
