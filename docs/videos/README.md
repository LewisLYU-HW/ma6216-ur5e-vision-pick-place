# 任务演示视频

以下为已实际运行的 MuJoCo 仿真录像，按原帧率、完整时长转码为 H.264 / yuv420p
MP4，并设置 faststart。没有加速、删帧或把失败片段剪成成功片段。
点击文件链接可在 GitHub 查看或下载；下载到本地后可用 VLC 打开。

| 视频 | 内容 |
|---|---|
| [全景＋腕部](pose-insertion-overview-wrist.mp4) | 同一次完整视觉运行，左全景、右腕部 |
| [独立腕部](pose-insertion-wrist.mp4) | 上一段运行的腕部画面 |
| [完整 6D 全景](pose-insertion-full.mp4) | 倾斜取件、定向落座，实际验收通过 |
| [yaw-only 失败](pose-insertion-yaw-only-failure.mp4) | 丢弃 roll/pitch 后，物体卡在槽边，实际验收失败 |

均为布局 3；使用官方 FoundationPose Model-based、固定 RGB-D 估计及相同
物理验收。腕部相机在这些录像中仅用于观察。Model-free 和三个新任务的录像
将在各自验证后另行添加，不能用本目录现有视频代表这些功能已经完成。

各视频的时长、分辨率、SHA-256 以及原始运行路径记录在
[manifest.json](manifest.json)。感知误差与物理结果见
[pose-insertion.json](../results/pose-insertion.json) 和
[wrist-camera.json](../results/wrist-camera.json)。
