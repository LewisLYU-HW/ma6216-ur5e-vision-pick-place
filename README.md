# MA6216 Project 1 · UR5e 视觉引导机器人操作

## 长时程仿真演示

[![点击播放四阶段长时程仿真，含全景与腕部视角](https://raw.githubusercontent.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/feat/model-free-manipulation/docs/presentation/media/complete_task_poster.jpg)][长时程视频]

**[播放四阶段演示（8 倍速，约 24 秒）][长时程视频]** · [完整录像][完整录像] · [独立腕部视角][腕部录像]

同一场景连续完成四步：锤子归位 → 抓取移动螺丝刀并插入倾斜套筒 → 安装工具架 → 扳手换抓并挂放。录像展示一次完整成功运行。

## 项目简介

项目面向工业工作台上的抓取、搬运、码垛和装配。仿真在 MuJoCo 中使用 UR5e、Robotiq 2F-85 夹爪和 RGB-D 相机。系统先完成相机标定、目标分割与 6D 位姿估计，再把视觉结果变换到机器人坐标系，用逆运动学、碰撞检查和接触保护执行操作。

- **基础抓放和码垛**使用官方 FoundationPose 的基于模型方法，以已知 CAD 网格和 RGB-D 观测估计物体位姿。[FoundationPose 接入说明](docs/FOUNDATIONPOSE_INTEGRATION.md)
- **长时程工具任务**使用从参考 RGB-D 重建的工具表面。在插装和挂放等接触前阶段，主方法采用迭代位姿视觉伺服（Iterative PBVS），用腕部相机重复估计位姿、计算 SE(3) 误差并限幅修正。[视觉反馈与对照设计][视觉反馈]
- **真机验证**覆盖桌面抓放和码垛。固定相机提供抓取位姿，腕部相机在下降前细调 XY，抓取朝向保持固定。[真机代码与快速复现][真机复现]

## 任务与复现入口

| 任务 | 代码位置 | 复现与演示 |
| --- | --- | --- |
| 单工件抓放 | `main` | [环境与运行说明](docs/SETUP.md) |
| 三工件与多种物品抓放 | `main` | [三工件](docs/MULTI_OBJECT.md) · [多种类物品](docs/OBJECT_LIBRARY.md) · [抓放录像](docs/media/diverse-object-pick-place.mp4) |
| 四料块、两列两层码垛 | `main` / [v1.0.0](https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/releases/tag/v1.0.0) | [码垛复现](docs/PALLETIZING.md) · [码垛录像](docs/media/palletizing.mp4) |
| 倾斜取件与定向入槽 | `feat/6d-pose-insertion` | [倾斜入槽复现][倾斜入槽] |
| 四阶段连续任务及反馈对照 | `feat/model-free-manipulation` | [任务复现][连续任务] · [反馈实验][视觉反馈] |
| 真机抓放与码垛 | Fork 的 `feat/real-robot-deployment` | [真机复现][真机复现] |

### 快速运行视觉码垛

在 Linux 或 WSL 中克隆仓库，先按[安装指南](docs/SETUP.md)配置 MuJoCo 模型和 FoundationPose CUDA 环境。官方源码与预训练权重按指南单独获取。

```bash
git clone https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place.git
cd ma6216-ur5e-vision-pick-place
conda activate foundationpose
python scripts/check_setup.py --vision
python -u scripts/run_palletizing.py \
  --output "artifacts/pallet_$(date +%Y%m%d_%H%M%S)" --record --viewer
```

默认读取随仓库提供的估计标定参数。更换相机后需重新标定，无窗口运行时去掉 `--viewer`。四阶段仿真请切换到 `feat/model-free-manipulation`，按[反馈实验说明][视觉反馈]运行 `scripts/run_workshop.py --task complete --visual-feedback iterative`。

## 实验与资料

- **基础仿真**的固定相机内参留出重投影 RMSE 为 0.050 px。四料块视觉码垛完成 8/8 次放置，两种布局均通过整垛验收，最终槽位 XY 误差为 1.15–5.37 mm。[基础实测记录](docs/results/) · [码垛验收判据](docs/PALLETIZING.md)
- **长时程仿真**对比执行期开环、关键阶段反馈和迭代 PBVS，分别测试无扰动和预对准脉冲扰动，每种组合 8 次。逐次结果、成功判据和置信区间见[公开评测记录][长时程评测]。
- **真机**提供部署与可行性演示，复现需使用现场实测的相机外参、TCP 和工作台配置。[真机复现][真机复现]

[课程任务与选型](docs/PROJECT1_PALLETIZING.md) · [课程交付总览][项目总览] · [版本与打印资产](docs/VERSIONS.md) · [小组协作](docs/TEAM_WORKFLOW.md) · [第三方来源与许可](THIRD_PARTY_NOTICES.md)

[长时程视频]: https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/blob/feat/model-free-manipulation/docs/presentation/media/complete_task_with_timeline.mp4
[完整录像]: https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/blob/feat/model-free-manipulation/docs/videos/visual-feedback-calibrated-v1/complete__iterative__none__400.mp4
[腕部录像]: https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/blob/feat/model-free-manipulation/docs/videos/visual-feedback-calibrated-v1/complete__iterative__none__400__wrist.mp4
[视觉反馈]: https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/blob/feat/model-free-manipulation/docs/VISUAL_FEEDBACK.md
[连续任务]: https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/blob/feat/model-free-manipulation/docs/COMPLETE_WORKSHOP.md
[长时程评测]: https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/blob/feat/model-free-manipulation/docs/results/visual-feedback-calibrated-v1/README.md
[项目总览]: https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/blob/feat/model-free-manipulation/docs/FINAL_PROJECT.md
[倾斜入槽]: https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/blob/feat/6d-pose-insertion/docs/POSE_INSERTION.md
[真机复现]: https://github.com/zihangmu00/ma6216-ur5e-vision-pick-place/blob/feat/real-robot-deployment/real_deployment/README.md
