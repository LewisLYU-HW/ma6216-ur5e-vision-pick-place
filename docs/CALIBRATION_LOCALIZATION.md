# Project 1：Task 2、3、4 补充实现

本轮补齐当前工具任务的腕部内参、手眼标定，以及四种工具的独立定位评估。正常任务默认使用估计标定，旧的48次反馈评测保留原来的理想腕部标定条件。

| 课程要求 | 当前实现和证据 |
|---|---|
| Task 2 虚拟相机内参 | 固定相机原有棋盘估计；新增腕部24张有效训练图、8张独立验证图，验证平均重投影误差0.02177 px。模拟器 K 仅用于评价。 |
| Task 3 相机—机器人变换 | 固定相机原有坐标对应标定；新增腕部 AX=XB 手眼标定及训练图重投影细化，24张有效训练图、10张独立验证图。手眼误差0.852 mm／0.0227°，冻结坐标链验证重投影0.05497 px。 |
| Task 4 视觉定位 | 当前四工具深度前景分割，10种布局种子×5类条件，共50场景、200次查询。记录 IoU、Precision、Recall、定位率、目标缺失误检率、区间和失败图片。预测完成后才用仿真标签评价。 |

[腕部标定完整证据](results/wrist-calibration-v1/README.md) · [四工具定位报告](results/workshop-localization-v1/README.md) · [固定相机原有证据](results/calibration.json)。

新估计标定已接入正常控制。无扰动、有扰动两次 seed400 完整任务均通过最终四物体验收，有扰动例额外30秒静置仍通过；[接入记录与录像](results/calibrated-workshop-v1/README.md)单独发布，不计入旧48次成功率。

## 相机到机器人坐标

固定相机：`world_T_object = world_T_camera_estimated @ camera_T_object`。

腕部相机：`world_T_object = world_T_gripper_FK @ gripper_T_camera_estimated @ camera_T_object`。

`world` 是机器人安装原点的规划坐标；Menagerie 的 `base` body 相对其绕 Z 旋转 π，固定相机样例同时提供 `base_body_T_camera.txt`。腕部手眼的手坐标明确为 `gripper_base`，不能把它直接当作 TCP／夹持点坐标。

手眼采图中棋盘固定、机械臂采取不同静态姿态。估计器只接收图像、棋盘尺寸和 FK，不接收棋盘世界真值或相机真值。先从图像做 PnP，再解 `G_i X C_i = Y`；X 和 Y 均未知。验证图不参加拟合，整条坐标链验证不逐图重拟合 Y。

原点标记与棋盘的单应几何校验排除整格错认。运行时还要求手眼留出图平均误差≤0.5 px、最大≤1 px；缺文件或未通过时明确报错，不回退到仿真参数。

## 运行与复现

```bash
# 重新渲染、估计并独立评价；输出目录必须是新的。
MUJOCO_GL=egl .venv/bin/python scripts/run_wrist_calibration.py \
  --seed 621610 --output artifacts/wrist_calibration_new

# 只用仓库里的图像和 FK 重新估计，不读取相机真值文件。
MUJOCO_GL=egl .venv/bin/python scripts/run_wrist_calibration.py \
  --estimate-only docs/results/wrist-calibration-v1/data \
  --output artifacts/wrist_reestimate_new

# 当前四工具的固定相机定位专项。
MUJOCO_GL=egl .venv/bin/python scripts/evaluate_workshop_localization.py \
  --output artifacts/localization_new

# 在现有 GPU 环境下运行带新标定的完整工具流程。
MUJOCO_GL=egl .venv/bin/python scripts/run_workshop.py \
  --task complete --visual-feedback iterative --seed 400 \
  --feedback-delay 0.15 --sensor-delay 1.0 --trace \
  --foundationpose-python /path/to/foundationpose/python \
  --output artifacts/calibrated_complete_new
```

正常入口默认加载 `demo_data/calibration/wrist/estimated`；自行重标定时传入 `--wrist-calibration 新目录/estimated`。`--ideal-wrist-diagnostic` 仅用于明确标记的历史理想标定诊断，不能计为这次 Task 2/3 的估计标定证据。原48次报告须使用其冻结提交复现，不能把当前代码的新输出混入旧报告。

## 已发现的局限

定位器依赖预先定义的取件工位，不承担任意类别识别。按实际任务逐种子采集配对空背景后，正常场景平均 IoU 为0.887；部分遮挡、深度噪声条件分别为0.810、0.810。测试中的160次有目标查询均达到预定 IoU≥0.5，40次目标缺失查询均未误检，但每工具／条件只有10次，不能外推为任意场景可靠。

开发评测曾误用统一空背景，支架与扳手的支撑结构差异造成误检。该设置已纠正，分割算法与阈值未改变；旧记录作为[背景失配故障诊断](results/workshop-localization-v1/background_mismatch_diagnostic/README.md)单独保留，不混入主统计。

相机和机器人 FK 为理想仿真成像／运动学模型，参考物体扫描仍使用理想合成标定。本轮手眼指标来自一次标定实验；50个场景观测不是50次机械操作，也不等于50次独立标定。完整任务中的腕部 mask 评价另行记录在 `perception[].localization_evaluation_only`，不与固定相机专项混为一组。

相关检查：`scripts/check_calibration_localization.py` 覆盖 AX=XB 变换方向、激励不足拒绝、运行时不读相机真值、错位棋盘拒绝，以及空目标／错误分割计分。
