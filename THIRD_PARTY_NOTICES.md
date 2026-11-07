# 第三方来源与许可记录

本项目连接外部机器人模型和位姿估计实现。上游仓库和权重由使用者按各自许可单独获取。本清单记录当前使用来源，许可原文以对应上游提交为准。本项目没有替小组选择统一的对外开源许可证。

| 来源 | 在本项目中的用途 | 已核对的许可与版本 |
|---|---|---|
| [MuJoCo](https://github.com/google-deepmind/mujoco) | 场景、相机渲染、接触动力学与关节执行 | 当前使用 Python 包 3.17.0。许可见上游仓库。 |
| [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) | UR5e 与 Robotiq 2F-85 模型 | 当前提交 `fb36886b3023db08c198264e1e9956ab202c3e3b`。模型分别有自己的许可。 |
| `universal_robots_ur5e` | 机械臂 MJCF、网格、关节和执行器 | 本地模型 README 标注 **BSD-3-Clause**，见该目录 `LICENSE`。 |
| `robotiq_2f85` | 夹爪 MJCF、网格与指垫接触 | 本地模型 README 标注 **BSD-2-Clause**，见该目录 `LICENSE`。 |
| [FoundationPose](https://github.com/NVlabs/FoundationPose) | Model-based / few-shot Model-free RGB-D 6D 位姿估计、跟踪与 Neural Object Field 重建 | 当前提交 `a1b694b83e633c2cb6115b9063d940a687759392`。README 标注 **NVIDIA Source Code License**，实际 `LICENSE` 含 non-commercial 使用限制及保留许可和归属声明的要求。权重遵从上游发布条款。 |
| [ros2_vision_grasp](https://github.com/Cyanat-qt/ros2_vision_grasp) | 阶段组织、轨迹执行与物理验收的设计参考 | 当前实现自行调用 MuJoCo；参考项目的 ROS 2/MoveIt 2 软件栈未作为本项目运行依赖。 |

本项目的绿色斜角工件由项目中的参数化几何生成，物理模型与导出 OBJ 使用同一组三角面。若以后加入其他 CAD、网格、纹理、数据或第三方代码，应同时记录其来源与适用许可。原课程材料、个人交接记录和下载权重不属于仓库源码分发清单。

码垛使用的 80×50×40 mm 平顶单角切边料块同样由本项目参数化生成，定义在 `src/ma6216/palletizing.py`。感知、碰撞和打印导出使用同一几何，未为码垛新增外部 CAD 或训练网络。

`assets/reconstructed` 是新增三任务中，从本项目合成 RGB-D 参考图调用官方
FoundationPose / BundleSDF Neural Object Field 得到的表面与纹理；记录了参考图哈希、
重建参数和来源提交。它们不是从模拟物体 CAD 直接导出的感知模型。
外部源码、CUDA 扩展和官方预训练权重仍不随仓库分发。

## 新增扫描工具（2026-11-06）

本仓库现在包含 [Google Scanned Objects 的 MuJoCo 转换库](https://github.com/kevinzakka/mujoco_scanned_objects/tree/6ff8d275cebfd5b47e49685e3cfbe64b20e49a3c) 中的 `Cole_Hardware_Hammer_Black` 和 `Craftsman_Grip_Screwdriver_Phillips_Cushion`。原始数据归属 Google Scanned Objects / Laura Downs 等，MuJoCo 转换归属 Kevin Zakka。该转换库声明：OBJ/PNG 为 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)，XML 为 MIT；MIT 原文保存在 [assets/library/gso/LICENSE](assets/library/gso/LICENSE)。这不是本项目自行建模的工具，也不是 Google 官方维护的 MuJoCo 转换库。

原始 71 个文件及来源哈希清单在 `assets/library/gso`。本项目派生模型缩小至 50%、以包围盒中心重设原点，并为颜色分割使用哑光颜色；打印副本合并纹理接缝的重合顶点、转为毫米并把底面平移至 Z=0。这些修改不改变原件文件。打印 OBJ/STL 的许可沿用源扫描资产的 CC BY 4.0，请交接时保留本归属说明及来源链接。球体与六角螺母为本项目参数化几何。

- Laura Downs et al. *Google Scanned Objects: A High-Quality Dataset of 3D Scanned Household Items*. 2022. [论文](https://arxiv.org/abs/2204.11918)
- Kevin Zakka. *Scanned Objects MuJoCo Models*. 2022. [仓库](https://github.com/kevinzakka/mujoco_scanned_objects)

论文引用可在项目技术展示中使用。

- Bowen Wen, Wei Yang, Jan Kautz, Stan Birchfield. *FoundationPose: Unified 6D Pose Estimation and Tracking of Novel Objects*. CVPR 2024. [论文](https://openaccess.thecvf.com/content/CVPR2024/html/Wen_FoundationPose_Unified_6D_Pose_Estimation_and_Tracking_of_Novel_Objects_CVPR_2024_paper.html)
- Bowen Wen, Jonathan Tremblay, Valts Blukis, Stephen Tyree, Thomas Müller, Alex Evans, Dieter Fox, Jan Kautz, Stan Birchfield. *BundleSDF: Neural 6-DoF Tracking and 3D Reconstruction of Unknown Objects*. CVPR 2023. [上游引用信息](https://github.com/NVlabs/FoundationPose/tree/a1b694b83e633c2cb6115b9063d940a687759392#bibtex)
- Zhengyou Zhang. *A Flexible New Technique for Camera Calibration*. IEEE TPAMI, 2000. [作者机构资料](https://www.microsoft.com/en-us/research/project/a-flexible-new-technique-for-camera-calibration-2/publications/)
