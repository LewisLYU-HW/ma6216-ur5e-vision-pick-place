# Task 2 / Task 3：腕部内参与手眼标定

最终采图种子 621610。内参和手眼估计只读取 RGB 图像、棋盘尺寸、机器人关节正运动学；相机真值单独保存在评价文件，估计器不读取。使用与工具任务相同的腕部安装、80° 视场及 1280×960 分辨率。

独立真值评价：手眼平移误差 **0.852 mm**，旋转 **0.0227°**；fx/fy 相对误差 **0.206% / 0.198%**。

| 图集 | 采图数 | 有效图 | 平均重投影 RMSE/px | 最大/px |
|---|---:|---:|---:|---:|
| intrinsic_train | 40 | 24 | 0.04037 | 0.25143 |
| intrinsic_validation | 10 | 8 | 0.02177 | 0.03272 |
| hand_eye_train | 43 | 24 | 0.06135 | 0.21931 |
| hand_eye_validation | 20 | 10 | 0.05497 | 0.16039 |

内参验证冻结 K，仅为每张留出图拟合棋盘相对位姿；手眼验证同时冻结 K、相机安装变换 X 和静止棋盘世界位姿 Y，**不为验证图重新拟合棋盘位姿**。这是两种不同的验证，不能把单张 PnP 残差冒充整条坐标链误差。

## 估计过程

1. 真实渲染棋盘，检测角点和洋红色原点标记。以平面单应验证标记与网格关系，拒绝整格错位和不完整棋盘。所有拒绝图仍保留。
2. 仅 intrinsic_train 图用于 OpenCV calibrateCamera。虚拟相机是无畸变针孔，因此畸变系数固定为零；内参不以仿真 K 初始化。
3. 由 hand_eye_train 图的 PnP 与机器人 FK 组成 Gᵢ X Cᵢ = Y，解相对运动 AX=XB。旋转用对数向量 SVD，平移用线性最小二乘，再仅在训练图上联合细化 X、Y 的像素残差。
4. 保留 hand_eye_validation 做冻结坐标链的重投影验证，最后才读取相机真值计算毫米／角度误差。

原理和坐标约定参见 [OpenCV hand-eye 文档](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html)。本机 OpenCV 5.0 没有导出 calibrateHandEye，故本项目在 NumPy/SciPy 中实现上述 AX=XB 求解；没有更换视觉网络。

## 数据和复现

[训练角点示例](examples/intrinsic_train.jpg) · [独立手眼验证角点示例](examples/hand_eye_validation.jpg) · [仅用仓库图像与FK的重算验证](reproduction_validation.json)。重算内参最大差异小于4×10⁻⁹，手眼矩阵最大差异小于5×10⁻¹¹。

[全部图像与 FK](data/observations.json) · [全部估计与逐图指标](estimated/calibration.json) · [独立误差](evaluation.json) · [采图与估计源码哈希](source_sha256.json)。原点质量门槛为 3 px，网格单应 RMSE 门槛为 0.25 px；只依赖图像，不按仿真误差挑选图像。

```bash
MUJOCO_GL=egl .venv/bin/python scripts/run_wrist_calibration.py \
  --estimate-only docs/results/wrist-calibration-v1/data \
  --output artifacts/wrist_reestimate_new
```

重新采图省略 --estimate-only，默认种子 621610。采图通过设置独立静态机器人配置完成，棋盘固定；这不是机械臂连续运动演示。

正常任务从 demo_data/calibration/wrist/estimated 加载参数，通过当前机器人 FK 传播相机位姿；不读取仿真相机安装参数。缺少文件或留出验证不合格时明确失败，绝不自动退回理想标定。--ideal-wrist-diagnostic 仅供明确标注的历史诊断。

## 开发记录与范围

初始采图尝试受夹爪与原场景托盘遮挡；之后使用专用标定工位。开发种子 621609 还暴露了部分棋盘整格错认，导致未经质量检查的手眼误差约 12 mm。图像标记校验修复后冻结方法，再使用上述新种子 621610 做最终验证；未根据相机真值优化 X 或替换最终结果。开发原始数据保存在本机 artifacts/wrist_calibration_v1 至 v4_qualitycheck。

这是单次独立标定实验，图像数量不等于独立重复标定次数。机器人 FK、棋盘尺寸及刚性安装为理想仿真假设，未验证实际机器人弹性或关节测量噪声。参考物体扫描的相机标定仍是独立的理想合成假设。固定相机原有标定证据见 [calibration.json](../calibration.json)。
