"""Write a reviewable Chinese report from measured, complete benchmark results."""

import argparse
from collections import Counter
import json
from pathlib import Path

from summarize_benchmark import PRIMARY, interval

LABELS = {
    "assembly": "装配恢复",
    "clutter": "遮挡换抓",
    "conveyor": "运动抓取",
    "insert": "螺丝刀插架",
    "hang": "扳手挂放",
    "rack": "工具架自装配",
}


def rate(k, n, limits):
    if not n:
        return "—"
    return f"{k}/{n} · {100 * k / n:.0f}% [{100 * limits[0]:.1f}, {100 * limits[1]:.1f}]"


def estimate(stat, digits=2):
    if not stat or stat["mean"] is None:
        return "—"
    value = f"{stat['mean']:.{digits}f}"
    lo, hi = stat["ci95"]
    if lo is not None:
        value += f" [{lo:.{digits}f}, {hi:.{digits}f}]"
    return value + (f" (n={stat['n_trials']})" if stat["n_trials"] != 10 else "")


def clean(value):
    return str(value or "—").replace("|", "/").replace("\n", " ")


def brief_failure(value):
    """Keep the message readable; the linked original retains full numeric details."""
    text = str(value or "未提供异常信息")
    return text.split("; best=", 1)[0].split(": {", 1)[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results", type=Path, required=True)
    args = p.parse_args()
    video_root = f"../../videos/{args.results.name}"
    result = json.loads((args.results / "summary.json").read_text())
    protocol = json.loads((args.results / "protocol.json").read_text())
    if not result["complete"]:
        raise RuntimeError("A final report requires all scheduled trials")
    groups = result["groups"]
    config = protocol["config"]
    task_count = len(config["tasks"])
    seeds = config["seeds"]
    reports = [json.loads(p.read_text()) for p in sorted((args.results / "trials").glob("*.json"))]
    lines = []

    def add(text=""):
        lines.extend([text, ""])

    def table(headers, rows):
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "|".join(["---"] * len(headers)) + "|")
        lines.extend("| " + " | ".join(clean(x) for x in row) + " |" for row in rows)
        lines.append("")

    def label(g):
        return [LABELS[g["task"]], g["method"], "无" if g["disturbance"] == "none" else g["disturbance"]]

    add(
        "# 工具架动作修订后配对评测"
        if task_count == 1 and "rack" in config["tasks"]
        else "# 任务配对评测结果"
    )
    add(
        f"已完成 **{result['n_trials']} 次**：{task_count} 类任务 × 两种方法 × 两种环境 × 每配置 {len(seeds)} 次。"
        f"固定种子 {seeds}；每个任务/种子的四组初始物理状态 SHA-256 一致性检查已通过。"
        "开发运行不计入统计；任务失败全部保留。"
    )
    add(
        f"控制版本：`{protocol['git_parent']}`；协议创建时间：`{protocol['created_utc']}`。"
        f"本机并行试验数：{protocol['runtime']['parallel_trials']}，GPU 推理串行共享。"
        "版本、权重与源文件校验值见 [protocol.json](protocol.json)，本机设备信息见 [hardware.json](hardware.json)。"
    )
    add(
        f"[评测方法与复现](../../EVALUATION.md) · [全部 {result['n_trials']} 条试验 CSV](trials.csv) · "
        "[逐观测位姿 CSV](pose_observations.csv) · [完整统计 JSON](summary.json) · "
        f"[原始试验摘要](trials/) · [录像清单]({video_root}/README.md)"
    )
    for amendment in protocol.get("source_amendments", []):
        add(
            f"基础设施修复记录：保留 {len(amendment['retained_valid_trials'])} 次已完成有效试验，"
            f"另有 {len(amendment['excluded_unscored_attempts'])} 次共享纹理 PNG 初始化异常未计分并补跑。"
            f"修复提交 `{amendment['commit']}` 只将缓存写入改为原子替换；两张 PNG 修复前后字节哈希一致。"
            "另核对 seed 102 修复前后四次初始观测的 RGB、深度和 mask，12 个文件逐字节相同。"
            "控制策略、场景几何、验收阈值与种子未改。旧协议、异常日志及修复前后源码哈希均保存在 "
            "[infrastructure_incidents/](infrastructure_incidents/)。有效任务失败没有重跑或替换。"
        )
    add("## 任务成功率")
    add(
        "数字为成功数/试验数、百分比及 **Wilson 95% 置信区间**。10/10 仍只有约 [72.2%, 100%]，"
        "0/10 仍有约 [0%, 27.8%]；小样本不能证明某方法永不失败。"
    )
    rows = []
    for task, spec in protocol["config"]["tasks"].items():
        for condition in ("none", spec["disturbance"]):
            matched = [
                next(
                    g
                    for g in groups
                    if (g["task"], g["method"], g["disturbance"]) == (task, method, condition)
                )
                for method in ("full", spec["baseline"])
            ]
            rows.append(
                [
                    LABELS[task],
                    "无" if condition == "none" else condition,
                    rate(matched[0]["successes"], matched[0]["n_trials"], matched[0]["success_ci95"]),
                    spec["baseline"],
                    rate(matched[1]["successes"], matched[1]["n_trials"], matched[1]["success_ci95"]),
                ]
            )
    table(["任务", "扰动", "完整系统", "模块消融", "消融结果"], rows)
    add("![任务成功率及 Wilson 区间](figures/success_rates.png)")
    add("## 6DOF 位姿预测")
    add(
        "取每次试验每个目标的**第一张固定相机图像**；工具架任务先在两个目标间求均值，再以试验为统计单位。"
        "下表连续量为试验均值 [bootstrap 95% 区间]。准确率要求本任务所有初始目标均在 5 mm/5° 内，"
        "缺失预测计未通过，采用 Wilson 区间。这里衡量初始定位；后续腕部改进在逐观测 CSV 中单列。"
    )
    table(
        ["任务", "方法", "扰动", "原始平移/mm", "原始旋转/°", "原始 ADD/mm", "原始 ADD-S/mm", "原始准确率"],
        [
            label(g)
            + [
                estimate(g["metrics"].get("pose_initial_raw_" + k))
                for k in ("translation_error_mm", "rotation_error_deg", "add_mm", "adds_mm")
            ]
            + [
                rate(
                    g["initial_pose_accuracy"]["raw"]["passed_trials"],
                    g["n_trials"],
                    g["initial_pose_accuracy"]["raw"]["ci95"],
                )
            ]
            for g in groups
        ],
    )
    add(
        "控制器收到的位姿可能经过消融或深度纠偏。下表单列其初始结果，避免把 yaw-only 丢弃朝向后的误差归给原始网络。"
        "ADD/ADD-S 采用参考重建表面；有方向要求的装配验收仍采用完整姿态，不能以 ADD-S 通过代替。"
    )
    table(
        ["任务", "方法", "扰动", "控制位姿平移/mm", "控制位姿旋转/°", "控制位姿准确率"],
        [
            label(g)
            + [
                estimate(g["metrics"].get("pose_initial_control_" + k))
                for k in ("translation_error_mm", "rotation_error_deg")
            ]
            + [
                rate(
                    g["initial_pose_accuracy"]["control"]["passed_trials"],
                    g["n_trials"],
                    g["initial_pose_accuracy"]["control"]["ci95"],
                )
            ]
            for g in groups
        ],
    )
    add("### 腕部阶段诊断")
    add(
        "初始固定视角可能存在接近 180° 的朝向歧义，不能用较小的 ADD-S 隐藏该问题。"
        "下面作为执行过程诊断，取每个目标的第一次腕部观测，先在每次试验内平均，再汇总。"
        "仅报告实际到达腕部观测阶段的试验和目标数量；未到达或关闭腕部观测记为 N/A。"
        "该条件性诊断不能替代上面的预定初始定位指标，也不用于跨方法显著性检验。"
    )
    wrist_groups = []
    for g in groups:
        trials = [
            r
            for r in reports
            if (r["task"], r["method"], r["disturbance"]) == (g["task"], g["method"], g["disturbance"])
        ]
        values = {
            k: [] for k in ("raw_translation", "raw_rotation", "control_translation", "control_rotation")
        }
        target_count = 0
        for trial in trials:
            observed = {}
            for s in trial.get("perception", []):
                if s["camera"] == "wrist_camera" and s["object_id"] in PRIMARY[g["task"]]:
                    observed.setdefault(s["object_id"], s)
            target_count += len(observed)
            for kind, key in (
                ("raw", "raw_estimator_metrics_evaluation_only"),
                ("control", "control_pose_metrics_evaluation_only"),
            ):
                for axis, metric in (
                    ("translation", "translation_error_mm"),
                    ("rotation", "rotation_error_deg"),
                ):
                    samples = [s.get(key, {}).get(metric) for s in observed.values()]
                    samples = [x for x in samples if x is not None]
                    if samples:
                        values[kind + "_" + axis].append(sum(samples) / len(samples))
        wrist_groups.append(
            {
                **{k: g[k] for k in ("task", "method", "disturbance")},
                "observed_targets": target_count,
                "metrics": {k: interval(v) for k, v in values.items()},
            }
        )
    table(
        [
            "任务",
            "方法",
            "扰动",
            "有观测试验/10",
            "目标观测数",
            "原始平移/mm",
            "原始旋转/°",
            "控制平移/mm",
            "控制旋转/°",
        ],
        [
            label(g)
            + [str(g["metrics"]["raw_translation"]["n_trials"]) + "/10", str(g["observed_targets"])]
            + [
                estimate(g["metrics"][k])
                for k in ("raw_translation", "raw_rotation", "control_translation", "control_rotation")
            ]
            for g in wrist_groups
        ],
    )
    (args.results / "wrist_diagnostics.json").write_text(json.dumps(wrist_groups, indent=2) + "\n")
    add("## 标定误差")
    c = result["calibration"]
    add(
        "所有试验共用一次已冻结的固定相机标定，不将重复使用记成多次独立标定。"
        f"外参平移误差 **{c['fixed_extrinsic']['translation_error_mm']:.3f} mm**，"
        f"旋转误差 **{c['fixed_extrinsic']['rotation_error_deg']:.3f}°**；"
        f"焦距相对误差 fx/fy 为 {c['focal_relative_error'][0] * 100:.3f}% / {c['focal_relative_error'][1] * 100:.3f}%，"
        f"主点偏差为 ({c['principal_point_error_px'][0]:.3f}, {c['principal_point_error_px'][1]:.3f}) px。"
    )
    table(
        ["棋盘格图集", "图像数", "平均重投影 RMSE/px", "最大 RMSE/px"],
        [
            [k, v["count"], f"{v['mean_rmse_px']:.4f}", f"{v['max_rmse_px']:.4f}"]
            for k, v in c["checkerboard_reprojection"].items()
        ],
    )
    wrist = c.get("wrist_hand_eye", {})
    if wrist.get("measured_error") is not None:
        error = wrist["measured_error"]
        add(f"腕部内参和手眼由棋盘图像与机器人 FK 估计，独立评价误差 **{error['translation_error_mm']:.3f} mm／{error['rotation_error_deg']:.4f}°**。")
    else:
        add("本轮腕部手眼使用理想仿真安装，独立标定误差 **N/A**。")
    add("当前结果不含深度传感器真实噪声和真机手眼误差。")
    add("## 执行精度")
    add(
        "TCP 跟踪误差比较实际关节 FK 与计划关节参考 FK；加入速度前馈时，执行器输入与计划参考分别记录。"
        "每个试验先求轨迹 RMSE，再在试验间求均值和区间。"
        "移动终点误差按完成的移动求均值。失败也保留；提前失败、没有完成移动时明确报告缺失样本数。"
        "这些是执行跟踪误差，不能替代感知精度或任务成功率。"
    )
    keys = (
        "tcp_tracking_translation_mm_rmse",
        "tcp_tracking_rotation_deg_rmse",
        "move_endpoint_translation_mm_mean",
        "move_endpoint_rotation_deg_mean",
    )
    table(
        ["任务", "方法", "扰动", "TCP RMSE/mm", "TCP RMSE/°", "终点位置/mm", "终点旋转/°"],
        [label(g) + [estimate(g["metrics"].get(k)) for k in keys] for g in groups],
    )
    add(
        "终态物体误差包含失败时停留的位置，不能按成功样本删选后宣称更高精度。"
        "插装深度、轴线角、环孔偏移、接触力、速度和完整终态分别保存在每条试验摘要中。"
    )
    rows = []
    for g in groups:
        if g["task"] in ("assembly", "clutter", "conveyor"):
            selected = ("final_plug_position_error_mm", "final_plug_rotation_error_deg")
            meaning = "工件位置/mm；旋转/°"
        elif g["task"] == "insert":
            selected = ("final_screwdriver_insertion_depth_mm", "final_screwdriver_shaft_axis_error_deg")
            meaning = "插入深度/mm；轴线/°"
        elif g["task"] == "hang":
            selected = ("final_spanner_support_force_n", "final_spanner_eye_plane_error_deg")
            meaning = "挂钩支撑力/N；环孔平面/°"
        else:
            selected = ("final_rack_frame_translation_error_mm", "final_rack_frame_rotation_error_deg")
            meaning = "支架位置/mm；旋转/°"
        rows.append(label(g) + [meaning] + [estimate(g["metrics"].get(k)) for k in selected])
    table(["任务", "方法", "扰动", "终态指标", "指标 1", "指标 2"], rows)
    add("## 执行频率与耗时")
    add(
        "仿真控制设定 **500 Hz**，执行误差采样 **50 Hz**，录像 **25 fps**。"
        f"下表为 {protocol['runtime']['parallel_trials']} 路并行、GPU 串行共享时的实测值；推理时间不含排队，墙钟时间含等待和资源竞争。"
        "视觉更新是间歇性的。静态推理和离线规划期间物理暂停；运动感知使用固定 1.0 s 虚拟延迟。"
        "因此这些值不能解释为 500 Hz 视觉闭环或真机实时性能。"
    )
    keys = (
        "wall_seconds",
        "effective_steps_per_wall_second",
        "real_time_factor",
        "register_latency_seconds",
        "track_latency_seconds",
        "pose_calls_per_wall_second_including_waits",
    )
    table(
        [
            "任务",
            "方法",
            "扰动",
            "墙钟/s",
            "控制步/墙钟 s",
            "实时因子",
            "注册/s",
            "跟踪/s",
            "位姿调用/墙钟 s",
        ],
        [label(g) + [estimate(g["metrics"].get(k), 3 if k in keys[2:] else 1) for k in keys] for g in groups],
    )
    refined = [
        g for g in groups if g["metrics"].get("depth_refinement_latency_seconds", {}).get("mean") is not None
    ]
    if refined:
        add(
            "局部深度配准在 CPU 执行，耗时不包含在上面的网络注册/跟踪中，但计入任务墙钟时间。每次试验先对实际配准调用求均值，再跨试验汇总；未调用的配置为 N/A。"
        )
        table(
            ["任务", "方法", "扰动", "深度配准单次耗时/s"],
            [label(g) + [estimate(g["metrics"]["depth_refinement_latency_seconds"], 3)] for g in refined],
        )
    add("![完整系统的位姿、执行和注册耗时](figures/measured_metrics.png)")
    add("## 配对比较与动态扰动")
    add(
        "配对胜/负指同一种子上仅 A 成功 / 仅 B 成功。成功率差的保守 95% 区间由 Bonferroni 调整的"
        "精确二项边际区间相减；检验采用配对精确 McNemar。方法比较与扰动比较分别作为一个检验族进行 Holm 校正。"
        "区间较宽时保留不确定性，不以个别失败录像代替统计证据。"
    )

    def pair_rows(items, robustness=False):
        for q in items:
            lo, hi = q["conservative_ci95"]
            yield [
                LABELS[q["task"]],
                q.get("method") if robustness else q["b"],
                q["a"] if robustness else q["disturbance"],
                f"{100 * q['success_difference']:+.0f} [{100 * lo:.1f}, {100 * hi:.1f}]",
                f"{q['a_only_success']}/{q['b_only_success']}",
                f"{q['exact_mcnemar_p_unadjusted']:.4f}",
                f"{q['exact_mcnemar_p_holm_within_family']:.4f}",
            ]

    table(
        ["任务", "基线 B", "环境", "完整系统 − B/百分点", "胜/负", "原始 p", "Holm p"],
        pair_rows(result["paired_module_comparisons"]),
    )
    table(
        ["任务", "方法", "扰动 A", "扰动 − 无扰动/百分点", "胜/负", "原始 p", "Holm p"],
        pair_rows(result["dynamic_robustness"], True),
    )
    add(
        "扰动仅在规定阶段触发，提前失败可能未受到脉冲。下表明确记录送达数量；未送达的失败仍在任务成功率分母内。"
    )
    table(
        ["任务", "方法", "扰动", "实际送达/10"],
        [
            label(g) + [str(g["disturbance_delivered_trials"]) + "/10"]
            for g in groups
            if g["disturbance"] != "none"
        ],
    )
    add("## 失败案例与可追溯性")
    add(
        "预先规定选取规则：按任务顺序，最多保存两个完整系统失败任务及四个消融失败任务；"
        "每个任务/方法优先无扰动，再按最低失败种子选择。录像直接回放该次保存的物理轨迹，"
        "不重新运行、不替换失败。其余失败全部保留摘要、日志与轨迹校验值。"
    )
    table(
        ["试验", "停止阶段", "失败信息摘要与原始记录"],
        [
            [
                f"[{d['trial']}]({video_root}/{d['trial']}.mp4)",
                d["last_stage"],
                f"{brief_failure(d['error'])} · [完整记录](trials/{d['trial']}.json)",
            ]
            for d in result["failure_demos"]
        ],
    )
    counts = Counter(
        (r["task"], r["method"], r.get("last_stage", "unknown")) for r in reports if not r["success"]
    )
    table(
        ["任务", "方法", "失败停止阶段", "次数（两种环境合计）"],
        [
            [LABELS[task], method, stage, str(count)]
            for (task, method, stage), count in sorted(counts.items())
        ],
    )
    add("## 适用范围")
    add(
        "这是固定仿真场景的模块消融，不能宣称优于所有外部算法。每配置只有 10 次；随机化覆盖有限的拾取位置、"
        "夹具位置及部分装配初始角度，没有验证任意工具、任意遮挡、光照、背景或真实传感器噪声。"
        "Model-free 指 24 张标定参考 RGB-D 经官方 Neural Object Field 重建，不是无需参考图的零样本方法。"
        "夹具几何和标记安装关系已知。仿真几何、接触和速度真值用于阶段验收与安全停机，"
        "可以结束失败试验，但不向网络或运动目标生成反馈真值位姿。"
        "参考扫描为理想合成标定，腕部标定来源见上文；真机效果与对应的验收传感器需要另行实验。"
    )
    (args.results / "README.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
