# 固定相机的估计标定样例

`estimated/` 包含默认 1280 × 960 固定相机的估计内参与外参，取自本项目 2026-11-04 的棋盘格标定。估计函数只使用渲染图像检测到的角点、棋盘格尺寸和已知的板安装坐标。

- `cam_K.txt` 是 OpenCV 针孔内参矩阵。
- `world_T_camera.txt` 把 OpenCV 相机坐标转换到机械臂安装原点的世界对齐规划坐标。
- `base_body_T_camera.txt` 对应 Menagerie `base` body 坐标，该 body 相对世界绕 Z 旋转 π。
- `distortion.txt` 为无镜头畸变虚拟相机的零畸变参数。

样例与 `scene.py` 中的默认相机相匹配。改变相机位置、视场角、分辨率或装配方式后，应重新标定。完整重新采集的命令见 [安装说明](../../docs/SETUP.md)。
