# 统一评测：原始轨迹视频

这些视频来自正式试验保存的 25 Hz 物理状态，没有重新跑一次后替换结果。每段都保留原始仿真时长，左侧全景、右侧腕部；工具架成功运行另外提供独立腕部视频。静态推理与离线规划等待不计入仿真视频时长。

[完整评测报告](../../results/evaluation-v1/README.md) · [视频、原始轨迹与摘要校验值](manifest.json)

## 工具架自装配与承重

采用无扰动完整方法中最低成功种子：`rack__full__none__101`。

[完整全景＋腕部](rack__full__none__101.mp4) · [独立腕部](rack__full__none__101__wrist.mp4)

## 预定规则选出的失败案例

| 试验视频 | 停止阶段 | 原始数值与失败原因 |
|---|---|---|
| [insert__full__none__100](insert__full__none__100.mp4) | RETRACT_DRIVER_SETTLE | [原始摘要](../../results/evaluation-v1/trials/insert__full__none__100.json) |
| [hang__full__none__105](hang__full__none__105.mp4) | CHECK_HANG_STABILITY | [原始摘要](../../results/evaluation-v1/trials/hang__full__none__105.json) |
| [assembly__no_recovery__fixture_shift__100](assembly__no_recovery__fixture_shift__100.mp4) | INSERT_1 | [原始摘要](../../results/evaluation-v1/trials/assembly__no_recovery__fixture_shift__100.json) |
| [clutter__yaw_only__none__100](clutter__yaw_only__none__100.mp4) | SETTLE | [原始摘要](../../results/evaluation-v1/trials/clutter__yaw_only__none__100.json) |
| [conveyor__no_prediction__none__100](conveyor__no_prediction__none__100.mp4) | CLOSE_GRIPPER | [原始摘要](../../results/evaluation-v1/trials/conveyor__no_prediction__none__100.json) |
| [insert__no_wrist__none__100](insert__no_wrist__none__100.mp4) | RETRACT_DRIVER_SETTLE | [原始摘要](../../results/evaluation-v1/trials/insert__no_wrist__none__100.json) |

## 同种子的完整方法对照

每个选中消融案例均附相同任务、扰动和种子的完整方法；无论成功还是失败都保留。

| 消融失败视频 | 完整方法视频 | 完整方法结果 |
|---|---|---|
| [assembly__no_recovery__fixture_shift__100](assembly__no_recovery__fixture_shift__100.mp4) | [assembly__full__fixture_shift__100](assembly__full__fixture_shift__100.mp4) | 成功 |
| [clutter__yaw_only__none__100](clutter__yaw_only__none__100.mp4) | [clutter__full__none__100](clutter__full__none__100.mp4) | 成功 |
| [conveyor__no_prediction__none__100](conveyor__no_prediction__none__100.mp4) | [conveyor__full__none__100](conveyor__full__none__100.mp4) | 成功 |
| [insert__no_wrist__none__100](insert__no_wrist__none__100.mp4) | [insert__full__none__100](insert__full__none__100.mp4) | 失败 |

## 本地回放与查看

下载 MP4 后使用 `xdg-open 文件名.mp4` 或 VLC；MP4 是视频文件，不能直接当 shell 命令执行。

原始选中轨迹在 [replay_inputs/](../../results/evaluation-v1/replay_inputs/)；安装仿真环境后可用 `scripts/replay_trial.py --trial ... --output 新目录 --export 新文件.mp4` 重新渲染，无需 FoundationPose 推理环境。失败轨迹不会因为回放而改变验收结果。
