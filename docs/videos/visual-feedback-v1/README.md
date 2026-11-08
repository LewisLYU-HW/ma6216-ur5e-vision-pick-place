# 统一评测：原始轨迹视频

这些视频来自正式试验保存的 25 Hz 物理状态，没有重新跑一次后替换结果。每段都保留原始仿真时长，左侧全景、右侧腕部；选中的成功运行另外提供独立腕部视频。静态推理与离线规划等待不计入仿真视频时长。

[完整评测报告](../../results/visual-feedback-v1/README.md) · [视频、原始轨迹与摘要校验值](manifest.json)

反馈阶段叠加的 `VISION residual` 是视觉估计与目标之间的残差，不是独立真值测得的定位精度。达到 1.5 mm／1.5° 视觉阈值不保证真实误差也低于该值；两种误差及被拒绝的观察分别保存在 [逐次闭环观测 CSV](../../results/visual-feedback-v1/visual_feedback_observations.csv)。

## 四阶段完整视觉闭环

采用无扰动迭代视觉闭环中最低成功种子：`complete__iterative__none__400`。

[完整全景＋腕部](complete__iterative__none__400.mp4) · [独立腕部](complete__iterative__none__400__wrist.mp4)

## 预定规则选出的失败案例

| 试验视频 | 停止阶段 | 原始数值与失败原因 |
|---|---|---|
| [complete__iterative__none__401](complete__iterative__none__401.mp4) | CLOSE_GRIPPER | [原始摘要](../../results/visual-feedback-v1/trials/complete__iterative__none__401.json) |
| [complete__open_loop__none__400](complete__open_loop__none__400.mp4) | RETRACT_DRIVER_SETTLE | [原始摘要](../../results/visual-feedback-v1/trials/complete__open_loop__none__400.json) |
| [complete__staged__none__401](complete__staged__none__401.mp4) | CLOSE_GRIPPER | [原始摘要](../../results/visual-feedback-v1/trials/complete__staged__none__401.json) |

## 同种子的迭代视觉闭环对照

每个选中对照案例均附相同任务、扰动和种子的迭代视觉闭环；无论成功还是失败都保留。

| 对照失败视频 | 迭代视觉闭环视频 | 迭代视觉闭环结果 |
|---|---|---|
| [complete__open_loop__none__400](complete__open_loop__none__400.mp4) | [complete__iterative__none__400](complete__iterative__none__400.mp4) | 成功 |
| [complete__staged__none__401](complete__staged__none__401.mp4) | [complete__iterative__none__401](complete__iterative__none__401.mp4) | 失败 |

## 本地回放与查看

下载 MP4 后使用 `xdg-open 文件名.mp4` 或 VLC；MP4 是视频文件，不能直接当 shell 命令执行。

原始选中轨迹在 [replay_inputs/](../../results/visual-feedback-v1/replay_inputs/)；安装仿真环境后可用 `scripts/replay_trial.py --trial ... --output 新目录 --export 新文件.mp4` 重新渲染，无需 FoundationPose 推理环境。失败轨迹不会因为回放而改变验收结果。
