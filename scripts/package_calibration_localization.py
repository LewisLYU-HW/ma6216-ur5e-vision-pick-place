"""Publish independently reproducible Task 2/3/4 evidence without replacing old results."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def copy(source, destination):
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def publish_wrist(source, output):
    output.mkdir(parents=True, exist_ok=False)
    for name in ("data", "estimated", "evaluation.json", "evaluation_only_camera_truth.json", "source_snapshot", "source_sha256.json"):
        copy(source / name, output / name)
    c, e = read(output / "estimated/calibration.json"), read(output / "evaluation.json")
    assert e["calibration_frozen_before_gt_evaluation"] and not c["input_gt_camera_used"]
    for name, sha in c["source_sha256"].items():
        assert hashlib.sha256((output / "data" / name).read_bytes()).hexdigest() == sha, name
    for name, sha in read(output / "source_sha256.json").items():
        assert hashlib.sha256((output / "source_snapshot" / name).read_bytes()).hexdigest() == sha, name
    error = e["gripper_T_camera_error"]
    lines = ["# Task 2 / Task 3：腕部内参与手眼标定", "",
        "最终采图种子 621610。内参和手眼估计只读取 RGB 图像、棋盘尺寸、机器人关节正运动学；相机真值单独保存在评价文件，估计器不读取。使用与工具任务相同的腕部安装、80° 视场及 1280×960 分辨率。", "",
        f"独立真值评价：手眼平移误差 **{error['translation_error_mm']:.3f} mm**，旋转 **{error['rotation_error_deg']:.4f}°**；fx/fy 相对误差 **{e['focal_relative_error'][0]*100:.3f}% / {e['focal_relative_error'][1]*100:.3f}%**。", "",
        "| 图集 | 采图数 | 有效图 | 平均重投影 RMSE/px | 最大/px |",
        "|---|---:|---:|---:|---:|"]
    for name, v in c["splits"].items():
        lines.append(f"| {name} | {v['attempted']} | {v['detected']} | {v['mean_rmse_px']:.5f} | {v['max_rmse_px']:.5f} |")
    lines += ["", "内参验证冻结 K，仅为每张留出图拟合棋盘相对位姿；手眼验证同时冻结 K、相机安装变换 X 和静止棋盘世界位姿 Y，**不为验证图重新拟合棋盘位姿**。这是两种不同的验证，不能把单张 PnP 残差冒充整条坐标链误差。", "",
        "## 估计过程", "",
        "1. 真实渲染棋盘，检测角点和洋红色原点标记。以平面单应验证标记与网格关系，拒绝整格错位和不完整棋盘。所有拒绝图仍保留。",
        "2. 仅 intrinsic_train 图用于 OpenCV calibrateCamera。虚拟相机是无畸变针孔，因此畸变系数固定为零；内参不以仿真 K 初始化。",
        "3. 由 hand_eye_train 图的 PnP 与机器人 FK 组成 Gᵢ X Cᵢ = Y，解相对运动 AX=XB。旋转用对数向量 SVD，平移用线性最小二乘，再仅在训练图上联合细化 X、Y 的像素残差。",
        "4. 保留 hand_eye_validation 做冻结坐标链的重投影验证，最后才读取相机真值计算毫米／角度误差。",
        "", "原理和坐标约定参见 [OpenCV hand-eye 文档](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html)。本机 OpenCV 5.0 没有导出 calibrateHandEye，故本项目在 NumPy/SciPy 中实现上述 AX=XB 求解；没有更换视觉网络。", "",
        "## 数据和复现", "",
        "[全部图像与 FK](data/observations.json) · [全部估计与逐图指标](estimated/calibration.json) · [独立误差](evaluation.json) · [采图与估计源码哈希](source_sha256.json)。原点质量门槛为 3 px，网格单应 RMSE 门槛为 0.25 px；只依赖图像，不按仿真误差挑选图像。", "",
        "```bash", "MUJOCO_GL=egl .venv/bin/python scripts/run_wrist_calibration.py \\",
        "  --estimate-only docs/results/wrist-calibration-v1/data \\", "  --output artifacts/wrist_reestimate_new", "```", "",
        "重新采图省略 --estimate-only，默认种子 621610。采图通过设置独立静态机器人配置完成，棋盘固定；这不是机械臂连续运动演示。", "",
        "正常任务从 demo_data/calibration/wrist/estimated 加载参数，通过当前机器人 FK 传播相机位姿；不读取仿真相机安装参数。缺少文件或留出验证不合格时明确失败，绝不自动退回理想标定。--ideal-wrist-diagnostic 仅供明确标注的历史诊断。", "",
        "## 开发记录与范围", "",
        "初始采图尝试受夹爪与原场景托盘遮挡；之后使用专用标定工位。开发种子 621609 还暴露了部分棋盘整格错认，导致未经质量检查的手眼误差约 12 mm。图像标记校验修复后冻结方法，再使用上述新种子 621610 做最终验证；未根据相机真值优化 X 或替换最终结果。开发原始数据保存在本机 artifacts/wrist_calibration_v1 至 v4_qualitycheck。", "",
        "这是单次独立标定实验，图像数量不等于独立重复标定次数。机器人 FK、棋盘尺寸及刚性安装为理想仿真假设，未验证实际机器人弹性或关节测量噪声。参考物体扫描的相机标定仍是独立的理想合成假设。固定相机原有标定证据见 [calibration.json](../calibration.json)。", ""]
    (output / "README.md").write_text("\n".join(lines))


def publish_localization(source, output):
    output.mkdir(parents=True, exist_ok=False)
    for name in ("summary.json", "protocol.json", "observations.csv", "examples", "source_snapshot"):
        copy(source / name, output / name)
    for scene in sorted((source / "scenes").iterdir()):
        for name in [*scene.glob("*_prediction.png"), *scene.glob("*_truth_evaluation_only.png"),
                     scene / "evaluation_only_object_poses.json"]:
            copy(name, output / "masks" / scene.name / name.name)
    s = read(output / "summary.json")
    p = read(output / "protocol.json")
    for name, sha in p["source_sha256"].items():
        assert hashlib.sha256((output / "source_snapshot" / name).read_bytes()).hexdigest() == sha, name
    labels = {"nominal": "正常布局", "position_orientation": "位置与朝向变化", "partial_occlusion": "部分遮挡", "depth_noise": "深度噪声与缺测", "target_absent": "目标缺失"}
    lines = ["# Task 4：当前四工具的视觉定位专项评估", "",
        "10 个配对种子（500–509）× 5 种条件 = **50 个场景观测、200 次工具查询**。这是感知专项，不是新增50次机械操作。固定相机使用棋盘估计参数，定位调用当前 depth_region_mask：空工位深度差分、已知取件区域、最大连通域。没有为了本轮结果调整阈值或换算法。", "",
        "先保存所有预测 mask，随后才渲染仿真可见物体标签计算指标。标签、物体 ID 和真值位姿不进入定位算法。工具身份由已知工位关联，不是任意类别识别。", "",
        "## 分割与定位结果", "",
        "| 条件 | 工具 | IoU 均值 | Precision | Recall | IoU≥0.5 定位数/10 | Wilson 95% CI |",
        "|---|---|---:|---:|---:|---:|---|"]
    for g in s["groups"]:
        if g["condition"] == "target_absent":
            continue
        ci = g["wilson95"]
        lines.append(f"| {labels[g['condition']]} | {g['object']} | {g['iou_mean']:.3f} | {g['precision_mean']:.3f} | {g['recall_mean']:.3f} | {g['count']}/10 | {ci[0]*100:.1f}%–{ci[1]*100:.1f}% |")
    lines += ["", "定位成功要求真值可见区域及预测区域均至少40像素，并且可见 mask IoU≥0.5。未检出、选错连通域和遮挡失败全部保留。IoU 是分割质量，不代表 6D 位姿精度或操作成功率。", "",
        "| 条件 | 四工具平均 IoU | 按场景 bootstrap 95% CI |", "|---|---:|---|"]
    for a in s["scene_level_aggregates"]:
        ci = a["bootstrap95"]
        lines.append(f"| {labels[a['condition']]} | {a['mean_iou']:.3f} | {ci[0]:.3f}–{ci[1]:.3f} |")
    lines += ["", "每个场景先平均四工具，再按10个场景 bootstrap 10000次；不把同一图像的四工具或像素当作40个／百万个独立实验。", "",
        "## 目标不存在时的误检", "", "| 工具查询 | 错误返回前景/10 | Wilson 95% CI |", "|---|---:|---|"]
    for g in s["groups"]:
        if g["condition"] != "target_absent":
            continue
        ci = g["wilson95"]
        lines.append(f"| {g['object']} | {g['count']}/10 | {ci[0]*100:.1f}%–{ci[1]*100:.1f}% |")
    lines += ["", "目标缺失时 IoU 为 N/A，单独统计误检；不会把两张空 mask 记成100%定位成功。每个种子使用与实际任务一致的配对空工位背景，不把固定支撑结构的布局变化误算成该方法的正常场景误检。", "",
        "## 条件与失败案例", "",
        "位置变化为 XY ±10 mm、yaw ±20°后静置0.5 s。部分遮挡使用实际渲染的50×50 mm不接触屏片，四工具平均剩余可见面积约67%–77%；分割评价针对剩余可见表面，不要求恢复遮挡背面。噪声条件加入 σ=2 mm 深度噪声及2%缺测，空工位参考不变。对象移除后保留支撑结构，检验实际误检。", "",
        "如出现定位失败，按种子顺序保留每类条件／工具的首个失败；正常样例单独标记。绿为预测与真值交集，红为误分区域，蓝为漏分区域。", ""]
    for item in s["examples"]:
        lines.append(f"- [{'失败' if item['failed'] else '正常样例'}：{labels[item['condition']]} / {item['object']} / seed {item['seed']}]({item['path']})")
    lines += ["", f"[全部200行结果](observations.csv) · [全部预测／真值 mask](masks/) · [汇总与案例选择](summary.json) · [冻结条件及源码哈希](protocol.json)。原始50组 RGB、深度保存在本机 artifacts/{source.name}/scenes；每行记录输入深度哈希。发布包保留源码快照、400张二值 mask 和失败图片，可直接独立复算全部像素指标。", "",
        "```bash", "MUJOCO_GL=egl .venv/bin/python scripts/evaluate_workshop_localization.py \\", "  --output artifacts/localization_repeat_new", "```", "",
        "此专项覆盖固定相机初始拾取定位；腕部跟踪 ROI 的逐次 mask 指标由新完整任务中的 localization_evaluation_only 另行记录，不能把本表泛化为腕部定位或任意混杂堆料的性能。", "",
        "开发版曾误用一张 seed-0 空工位背景，但支撑结构会随种子改变，与生产流程不一致；已纠正为逐种子配对。旧输出保留在 artifacts/workshop_localization_v2，未混入本报告。此修正没有改变分割算法、种子或通过阈值。", ""]
    (output / "README.md").write_text("\n".join(lines))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wrist-run", type=Path, required=True)
    p.add_argument("--localization-run", type=Path, required=True)
    args = p.parse_args()
    publish_wrist(args.wrist_run, ROOT / "docs/results/wrist-calibration-v1")
    publish_localization(args.localization_run, ROOT / "docs/results/workshop-localization-v1")
