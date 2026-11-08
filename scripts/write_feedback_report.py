"""Report measured three-way visual-feedback comparisons without pooling versions."""

import argparse
from collections import Counter
import json
from pathlib import Path

from write_benchmark_report import estimate, rate, brief_failure
from ma6216.evaluation import wilson_interval

TASKS = {"complete": "四阶段完整流程", "insert": "螺丝刀插架", "hang": "扳手换抓挂放", "rack": "支架安装与挂放"}
MODES = {"open_loop": "无执行期纠偏", "staged": "分阶段纠偏", "iterative": "迭代视觉闭环"}
OBJECTS = {"hammer": "锤子归位", "screwdriver": "螺丝刀插架", "rack_frame": "支架安装", "spanner": "扳手挂放"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    folder = args.results
    summary = json.loads((folder / "summary.json").read_text())
    protocol = json.loads((folder / "protocol.json").read_text())
    if not summary["complete"]:
        raise RuntimeError("Do not publish an incomplete evaluation as final results")
    config = protocol["config"]
    groups = summary["groups"]
    reports = [json.loads(path.read_text()) for path in sorted((folder / "trials").glob("*.json"))]
    index = {(g["task"], g["method"], g["disturbance"]): g for g in groups}
    modes = list(MODES)
    lines = []

    def add(text=""):
        lines.extend([text, ""])

    def table(headers, rows):
        lines.extend(["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"])
        for row in rows:
            lines.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in row) + " |")
        lines.append("")

    def label(group):
        return [TASKS[group["task"]], MODES[group["method"]], "无" if group["disturbance"] == "none" else "对准脉冲"]

    def metric(group, key, digits=2):
        return estimate(group["metrics"].get(key), digits)

    add("# 三种视觉反馈方式：配对评测结果")
    add(f"已完成 **{summary['n_trials']} 次**，{len(config['tasks'])} 类任务 × 3 种反馈模式 × 2 种环境 × 每配置 {len(config['seeds'])} 次。"
        f"种子 {config['seeds'][0]}–{config['seeds'][-1]}，初始物理状态配对哈希已验证。开发运行和历史 240／40 次结果均未混入本轮。")
    add(f"控制提交 `{protocol['git_parent']}`，协议时间 `{protocol['created_utc']}`；{protocol['runtime']['parallel_trials']} 路 CPU 仿真共享串行 GPU 推理。"
        "[冻结协议](protocol.json) · [全部试验 CSV](trials.csv) · [逐观测位姿](pose_observations.csv) · [原始摘要](trials/) · [反馈方法](../../VISUAL_FEEDBACK.md) · [原轨迹视频](../../videos/visual-feedback-v1/README.md)。")
    add("`open_loop` 保留初始定位和运动抓取前的预测，但关闭抓取后／释放后的视觉纠偏；`staged` 使用关键阶段复测；`iterative` 再加入对准后的重复观察、限幅纠偏与目标观测质量检查。所有配置保留同样的关节控制、真实接触、力限和最终验收。这是内部反馈模块对比，不是外部位姿算法排名。")
    add("## 任务成功率")
    add("各格为成功数／试验数、成功率及 Wilson 95% 区间。所有有效失败均保留，包括尚未到达反馈或扰动阶段的试验。")
    rows = []
    for task, spec in config["tasks"].items():
        for condition in ("none", spec["disturbance"]):
            row = [TASKS[task], "无" if condition == "none" else "对准脉冲"]
            for mode in modes:
                g = index[task, mode, condition]
                row.append(rate(g["successes"], g["n_trials"], g["success_ci95"]))
            rows.append(row)
    table(["任务", "扰动", *MODES.values()], rows)
    add("![任务成功率与 Wilson 95% 区间](figures/success_rates.png)")
    add("## 完整流程的阶段验收")
    add("以下是阶段完成当时的验收，分母仍为全部 10 次；括号给出实际进入该阶段的次数。整条任务还须在最后重新验收此前归位的物体，不能用某个阶段通过代替整链成功。")
    rows = []
    for condition in ("none", config["tasks"]["complete"]["disturbance"]):
        for obj, title in OBJECTS.items():
            row = [title, "无" if condition == "none" else "对准脉冲"]
            for mode in modes:
                g = index["complete", mode, condition]
                stage = g["phase_success"].get(obj, {"successes": 0, "entered": 0, "n_trials": g["n_trials"], "ci95": wilson_interval(0, g["n_trials"])})
                row.append(rate(stage["successes"], stage["n_trials"], stage["ci95"]) + f"；到达 {stage['entered']}")
            rows.append(row)
    table(["阶段", "扰动", *MODES.values()], rows)
    add("## 6D 位姿预测")
    add("使用各目标的第一次固定相机观察，先按试验汇总，再计算 bootstrap 95% 区间；通过率要求该任务所有初始目标都在 5 mm／5° 内。相同模型和初始输入的读数相同是预期行为，闭环的影响在后续对准和任务结果中体现。")
    table(["任务", "模式", "扰动", "平移/mm", "旋转/°", "ADD/mm", "ADD-S/mm", "5 mm／5° 通过率"], [
        label(g) + [metric(g, "pose_initial_raw_translation_error_mm"), metric(g, "pose_initial_raw_rotation_error_deg"),
                    metric(g, "pose_initial_raw_add_mm"), metric(g, "pose_initial_raw_adds_mm"),
                    rate(g["initial_pose_accuracy"]["raw"]["passed_trials"], g["n_trials"], g["initial_pose_accuracy"]["raw"]["ci95"])] for g in groups])
    add("## 实际对准误差：反馈前后")
    add("使用独立仿真真值计算物体与真实安装目标的偏差，只用于评估，不反馈给控制器。每行只包含到达该对准阶段的试验，n 必须与任务成功率分母区分；不同模式到达的样本可能不同，不将这张条件性诊断表当作总体因果比较。开环和分阶段模式在这个检查点不增加迭代动作，因此前后值相同。")
    rows = []
    for g in groups:
        for obj in ("screwdriver", "rack_frame", "spanner"):
            key = f"alignment_{obj}_before_translation_error_mm"
            stat = g["metrics"].get(key)
            if not stat:
                continue
            rows.append(label(g) + [OBJECTS[obj], stat["n_trials"], metric(g, key),
                        metric(g, f"alignment_{obj}_after_translation_error_mm"),
                        metric(g, f"alignment_{obj}_before_rotation_error_deg"),
                        metric(g, f"alignment_{obj}_after_rotation_error_deg")])
    table(["任务", "模式", "扰动", "阶段", "n", "前/mm", "后/mm", "前/°", "后/°"], rows)
    add("每次视觉残差、独立几何误差、被拒绝的目标更新、实际修正次数及收敛状态保存在逐试验摘要的 `visual_servo` 中。视觉残差下降不保证真实误差同步下降。")
    add("## 标定误差")
    calibration = summary["calibration"]
    ext = calibration["fixed_extrinsic"]
    add(f"固定相机使用同一套冻结标定：外参平移 **{ext['translation_error_mm']:.3f} mm**，旋转 **{ext['rotation_error_deg']:.3f}°**。"
        f"焦距相对误差 fx/fy 为 {100*calibration['focal_relative_error'][0]:.3f}%／{100*calibration['focal_relative_error'][1]:.3f}%。腕部手眼为理想仿真安装，独立实测误差为 **N/A**。重复使用这一标定不算多次独立标定实验。")
    table(["标定图集", "图像数", "平均重投影 RMSE/px", "最大 RMSE/px"], [
        [name, values["count"], f"{values['mean_rmse_px']:.4f}", f"{values['max_rmse_px']:.4f}"]
        for name, values in calibration["checkerboard_reprojection"].items()])
    add("## 执行精度")
    add("实际 TCP 与计划关节参考 FK 比较，每次试验先求轨迹 RMSE，再汇总均值及区间；终点误差按完成移动求均值。提前失败造成的缺测明确保留样本量。最终各物体的插入深度、轴线偏差、孔偏差、支撑接触与速度见 `terminal_outcomes_evaluation_only` 和 CSV 的 `final_*` 字段。")
    table(["任务", "模式", "扰动", "TCP RMSE/mm", "TCP RMSE/°", "终点均值/mm", "终点均值/°"], [
        label(g) + [metric(g, key) for key in ("tcp_tracking_translation_mm_rmse", "tcp_tracking_rotation_deg_rmse", "move_endpoint_translation_mm_mean", "move_endpoint_rotation_deg_mean")] for g in groups])
    add("## 频率、延迟和反馈代价")
    add("500 Hz 为仿真控制步频，日志 50 Hz，回放 25 fps；不是视觉闭环频率。新反馈观测固定推进 0.15 s 仿真时间，运动抓取的初始观察推进 1.0 s。实际推理／排队／规划期间仍存在暂停，以下墙钟指标包含共享资源等待，不代表独占硬件或真机实时性能。")
    table(["任务", "模式", "扰动", "总墙钟/s", "仿真时长/s", "反馈观察次数", "修正步数", "反馈更新/墙钟 s", "循环墙钟/s"], [
        label(g) + [metric(g, key, digits) for key, digits in (("wall_seconds", 1), ("simulation_seconds", 1), ("feedback_observations", 1), ("feedback_corrections", 1), ("feedback_updates_per_wall_second", 3), ("feedback_cycle_wall_seconds", 3))] for g in groups])
    table(["任务", "模式", "扰动", "网络注册/s", "网络跟踪/s", "深度配准/s", "全部位姿调用/墙钟 s"], [
        label(g) + [metric(g, key, 3) for key in ("register_latency_seconds", "track_latency_seconds", "depth_refinement_latency_seconds", "pose_calls_per_wall_second_including_waits")] for g in groups])
    add("## 配对差异与扰动鲁棒性")
    add("方法比较和扰动比较分别进行 Holm 校正。差值区间来自 Bonferroni 调整的精确二项边际区间，另给同种子配对胜／负及精确 McNemar p 值。小样本和宽区间不能证明方法普遍优越。")

    def pair_rows(items, disturbance=False):
        for item in items:
            lo, hi = item["conservative_ci95"]
            first = [TASKS[item["task"]], MODES[item["method"]], "有扰动 − 无扰动"] if disturbance else [TASKS[item["task"]], item["disturbance"], MODES[item["a"]] + " − " + MODES[item["b"]]]
            yield first + [f"{100*item['success_difference']:+.0f} [{100*lo:.1f}, {100*hi:.1f}]", f"{item['a_only_success']}/{item['b_only_success']}", f"{item['exact_mcnemar_p_unadjusted']:.4f}", f"{item['exact_mcnemar_p_holm_within_family']:.4f}"]
    table(["任务", "环境", "方法差", "差值/百分点 [95% CI]", "胜/负", "p", "Holm p"], pair_rows(summary["paired_module_comparisons"]))
    add("![同种子成功率差及保守区间](figures/paired_differences.png)")
    table(["任务", "模式", "环境差", "差值/百分点 [95% CI]", "胜/负", "p", "Holm p"], pair_rows(summary["dynamic_robustness"], True))
    rows = []
    for g in groups:
        if g["disturbance"] == "none":
            continue
        subset = [r for r in reports if (r["task"], r["method"], r["disturbance"]) == (g["task"], g["method"], g["disturbance"])]
        for obj in ("screwdriver", "rack_frame", "spanner"):
            delivered = sum(any(e["event"] == "external_alignment_impulse_started" and e.get("object_id") == obj for e in r["execution"]["events"]) for r in subset)
            if obj not in {"insert": ("screwdriver",), "hang": ("spanner",), "rack": ("rack_frame", "spanner"), "complete": ("screwdriver", "rack_frame", "spanner")}[g["task"]]:
                continue
            recovered = sum(any(s["object_id"] == obj and s.get("visual_recovery_simulation_seconds") is not None for s in r.get("visual_servo", [])) for r in subset)
            rows.append(label(g) + [OBJECTS[obj], f"{delivered}/{g['n_trials']}", recovered if g["method"] == "iterative" else "N/A", metric(g, f"feedback_{obj}_visual_recovery_simulation_seconds", 3)])
    table(["任务", "模式", "扰动", "阶段", "实际送达", "视觉确认收敛数", "收敛耗时/仿真 s"], rows)
    add("视觉收敛是控制器判断；真正恢复还须最终任务验收通过。完整流程后段未被送达扰动的情况不会伪称经历了该扰动。")
    add("## 失败记录与原轨迹视频")
    add("按协议预先规定的顺序选择失败，不以最有利案例替换。每个对照失败附上相同任务、环境和种子的迭代模式回放，无论其成功还是失败；它们不增加统计样本。")
    table(["原始试验", "停止阶段", "原因"], [[f"[{d['trial']}](../../videos/visual-feedback-v1/{d['trial']}.mp4)", d["last_stage"], brief_failure(d["error"])] for d in summary["failure_demos"]])
    failures = Counter((r["task"], r["method"], r.get("last_stage")) for r in reports if not r["success"])
    table(["任务", "模式", "停止阶段", "次数"], [[TASKS[t], MODES[m], stage, n] for (t, m, stage), n in sorted(failures.items())])
    add("## 数据与适用范围")
    add("每个配置只包含有限布局扰动的 10 个仿真种子，不是十种真实环境。物体参考来自 RGB-D 重建；固定夹具属于已测量工位，深度与腕部手眼仍为理想仿真。几何、接触和速度真值用于独立统计、验收和安全停机，不生成视觉纠偏目标。完整任务保留 10 秒悬挂稳定窗口，独立挂放／工具架任务沿用 4 秒；不跨任务合并成功率。")
    add("[证据清单](evidence_manifest.json)包含所有摘要、日志与轨迹的校验值，所选原轨迹在 `replay_inputs/`；完整 RGB-D 在本机源目录的无损归档中。历史报告保持不变。")
    (folder / "README.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
