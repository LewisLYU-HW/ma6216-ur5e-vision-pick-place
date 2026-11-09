# 腕部估计标定

`estimated/` 来自 RGB 棋盘图与 `gripper_base` 正运动学，采用独立内参训练／验证和手眼训练／验证划分。完整113张采图、拒绝记录、源代码快照和误差见 [腕部标定证据](../../../docs/results/wrist-calibration-v1/README.md)。

- `cam_K.txt`：1280×960 图像的估计针孔内参。
- `gripper_T_camera.txt`：OpenCV 相机坐标到 `gripper_base`，单位米。
- `distortion.txt`：该无畸变虚拟相机的固定零畸变系数。
- `calibration.json`：来源哈希、图像质量检查、所有逐图结果和独立验证。

机器人相机位姿由 `world_T_gripper_FK @ gripper_T_camera` 得到。相机视场、分辨率或安装方式改变后必须重标定；不能直接复用此样例。运行时不从 MuJoCo 的相机参数取得 K 或手眼变换。
