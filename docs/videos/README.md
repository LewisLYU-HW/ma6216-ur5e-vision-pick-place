# 任务演示视频

以下均基于已实际运行的 MuJoCo 仿真。历史演示为运行时录像，新统一评测视频由原试验保存的 25 Hz 物理状态回放；保留完整过程，没有把失败片段剪成成功片段。视频使用 H.264 / yuv420p MP4，并设置 faststart。
点击文件链接可在 GitHub 查看或下载；下载到本地后可用 VLC 打开。
录像按仿真时间采样；静态任务的推理和离线规划等待不等于录像时长。

## 完整连续任务：四个物体、四个阶段

**[全景＋腕部](complete-workshop/overview-wrist.mp4)** · **[独立腕部](complete-workshop/wrist.mp4)** · [视频来源与时间点](complete-workshop/README.md)

扫描锤子归位 → 运动螺丝刀抓取、倾斜插架 → 安装独立工具架、释放后重新定位 → 扳手松爪换抓、穿孔挂放。整段来自同一次视觉运行，四个物体始终保留在同一物理场景中。分屏为 1920×720，独立腕部为 960×720，均为 25 fps。

[复现命令](../COMPLETE_WORKSHOP.md) · [原始轨迹与验收](../results/complete-workshop/README.md)。这是固定布局的完整演示，不能当作多次试验的成功率。

## 工具架单项演示：动作修复版

[全景、独立腕部和失败对照](rack-revision-v2/README.md) · [修订后 40 次评测](../results/rack-revision-v2/README.md) · [动作修复说明](../RACK_MOTION_REVISION.md)

主视频：**[seed 202 全景＋腕部](rack-revision-v2/rack__full__none__202.mp4)** · [同次运行的独立腕部](rack-revision-v2/rack__full__none__202__wrist.mp4)，保留约 114 秒全过程。

新版调整抓姿衔接、释放后的撤离距离和关节速度前馈，修复装架后的大幅绕行与反复停顿。视频保留完整仿真时长；成功和失败均来自原始试验轨迹，旧版文件继续保留在下方。

## 历史 240 次评测：工具架自装配、失败与配对对照

| 入口 | 内容 |
|---|---|
| [旧版工具架全景＋腕部](evaluation-v1/rack__full__none__101.mp4) | seed 101；末态通过验收，但有绕行和停顿，不再作为当前主演示 |
| [同次运行的独立腕部](evaluation-v1/rack__full__none__101__wrist.mp4) | 观察支架插装、近景复测和扳手穿孔过程 |
| [6 条失败与同种子完整方法对照](evaluation-v1/README.md) | 包含完整系统失败；每个选中消融案例均附同种子的完整方法，不预设对照成功 |
| [完整统计报告](../results/evaluation-v1/README.md) | 六类任务、每配置 10 次、置信区间和全部指标 |

这组视频只回放原状态，不重新运行推理或物理试验。其来源、帧数、时长与 SHA-256 见独立的 [评测视频清单](evaluation-v1/manifest.json)，对应原始轨迹保存在 [replay_inputs](../results/evaluation-v1/replay_inputs/)。成功视频不代表该配置全部成功。

## 原三工具任务：固定挂钩

| 视频 | 内容 |
|---|---|
| [三工具流程：全景＋腕部](workshop-overview-wrist.mp4) | 扫描锤子归位、运动螺丝刀抓取与倾斜插架、扳手松爪换抓与穿孔挂放；使用固定挂钩，不包含装架 |
| [同次运行：独立腕部](workshop-wrist.mp4) | 保留完整时长，近距离观察夹持、姿态调整、插入和释放 |

使用真实扫描纹理与官方 FoundationPose few-shot Model-free 重建；深度背景分割、固定和腕部 RGB-D 估计共同驱动操作。
三色轴显示最新视觉位姿，夹持期间结合机器人 FK 传播；没有叠加物体真值作为跟踪结果。
分屏分辨率 1920×720，独立腕部 960×720。固定场景 seed 0 的结果见 [workshop.json](../results/workshop.json)，复现与假设见 [WORKSHOP.md](../WORKSHOP.md)。

## 原有 Model-free 三任务

| 视频 | 内容 |
|---|---|
| [装配恢复：全景＋腕部](model-free-assembly-overview-wrist.mp4) | 工件近景重定位，夹具移位后触发力保护，重新观察并在第二次完成插装 |
| [遮挡重抓：全景＋腕部](model-free-clutter-overview-wrist.mp4) | 移走障碍物、侧抓翻转、支架松爪、换抓姿、定向插装 |
| [运动目标：全景＋腕部](model-free-conveyor-overview-wrist.mp4) | RGB-D 跟踪、接触位置预测、送料台运动中夹取、腕部校正后插装 |
| [关闭恢复的失败对照](model-free-no-recovery-overview-wrist.mp4) | 与装配成功视频相同的初始布局和扰动，第一次接触保护后停止 |

三任务的腕部图像参与实际定位，均使用参考 RGB-D 的官方 Neural Object Field
重建模型；未把仿真 CAD 传给工件估计器。夹具采用 RGB-D 标记定位。
实测数字及每次视觉估计的误差见 [model-free-tasks.json](../results/model-free-tasks.json)，
输入假设、复现和限制见 [MODEL_FREE_TASKS.md](../MODEL_FREE_TASKS.md)。

## 原 Model-based 定向入浅槽对照

| 视频 | 内容 |
|---|---|
| [全景＋腕部](pose-insertion-overview-wrist.mp4) | 同一次完整视觉运行，左全景、右腕部 |
| [独立腕部](pose-insertion-wrist.mp4) | 上一段运行的腕部画面 |
| [完整 6D 全景](pose-insertion-full.mp4) | 倾斜取件、定向落座，实际验收通过 |
| [yaw-only 失败](pose-insertion-yaw-only-failure.mp4) | 丢弃 roll/pitch 后，物体卡在槽边，实际验收失败 |

以上四段均为原布局 3；使用官方 FoundationPose Model-based、固定 RGB-D 估计及相同
物理验收。腕部相机在这组原录像中仅用于观察。

以下历史视频的时长、分辨率、SHA-256 以及原始运行路径记录在
[manifest.json](manifest.json)。感知误差与物理结果见
[pose-insertion.json](../results/pose-insertion.json) 和
[wrist-camera.json](../results/wrist-camera.json)。
