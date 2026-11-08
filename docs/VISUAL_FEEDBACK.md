# 6D 视觉反馈与配对评测

在螺丝刀插架、独立支架安装、扳手穿孔之前，新增离散的位姿视觉伺服：**重新观察 → 计算完整 SE(3) 误差 → 限幅修正 → 再观察**。它使用官方 FoundationPose 和 RGB-D 重建表面；未更换位姿网络，也不以仿真物体位姿生成纠偏动作。

[48 次完整评测与全部指标](results/visual-feedback-v1/README.md) · [完整视频、腕部与失败对照](videos/visual-feedback-v1/README.md)。本轮未证明迭代闭环优于关键阶段反馈，所有失败和宽置信区间均保留。

## 三种可独立复现的反馈模式

`scripts/run_workshop.py --visual-feedback ...` 与已有 `--method` 模块消融分开。新反馈对比均使用 `--method full`，不能混入 `yaw_only` 等额外变化。默认 `legacy` 继续保留既有入口。

| 模式 | 抓起后的腕部纠偏 | 释放后支架／扳手重定位 | 对准后的重复观察与修正 |
|---|---|---|---|
| `open_loop` | 关闭 | 关闭，使用计划放置位姿 | 关闭 |
| `staged` | 开启 | 开启 | 关闭 |
| `iterative` | 开启 | 开启 | 开启 |

这里的开环仅指**物体操作期间不采用新的视觉纠偏**。三组均保留初始物体与底座定位、运动螺丝刀抓取前的三次观测及速度预测、关节位置反馈、双侧真实夹持、碰撞检查和接触力保护。因此 `open_loop` 不是关闭机械臂关节控制，也不是关闭相机。

`open_loop` 在完整场景中还关闭安装前的支架复测、扳手初次拾取前的额外复测，以及松爪换抓后的复测；这些都改为使用已有初始估计或计划放置位姿。旧 `no_wrist` 仍保留部分重新定位，不能与这个新开关混为一谈。

所有新模式使用相同的估计器、重建模型、轨迹规划、夹爪、接触保护与最终验收。新协议把完整演示已有的螺丝刀局部深度纠偏也用于独立 `insert` 的腕部观察。`staged` 与 `iterative` 的差别是新增的迭代反馈模块及其观测接受检查；不能把本轮 `staged` 的结果当作旧版报告的重新计算。

## 反馈发生的位置

| 阶段 | 反馈目标 | 执行边界 |
|---|---|---|
| 螺丝刀 | 完整工具坐标系与倾斜套筒对齐 | 接触插入前的预对准位姿 |
| 支架 | 重建榫头与底座对齐 | 插入前 60 mm 的预对准位姿 |
| 扳手 | 环孔平面与已观测挂钩对齐 | 穿孔前的预对准位姿 |

锤子归位和运动抓取保留原流程，不声称这两个阶段新增了迭代视觉伺服。接触插入仍使用既有分段运动与 7 N 力变化保护；新模块不是接触阻抗控制，也没有实现任意失败后的整条任务重启。

控制器从腕部图像估计物体位姿，以拍摄时的机器人 FK 更新夹爪／物体相对关系，再根据当前 FK 计算纠偏目标，避免把观察等待期间的机器人运动误认为物体滑动。默认增益 0.65，每步 TCP 平移最多 4 mm、旋转最多 2°；视觉误差达到 1.5 mm 和 1.5° 后，要求连续两次观察确认。最多 8 次修正，初始偏差超出 25 mm／15° 或不收敛则明确失败，所有保护保持启用。

装好的支架在扳手靠近时可能被遮挡。迭代重定位必须通过深度配准检查（至少 120 个内点、平面 RMSE 不超过 1.5 mm），并与最近可靠位姿相差不超过 8 mm／5°；否则记录被拒绝的估计，继续使用最近可靠目标。固定挂架的腕部标记不可见时也保留既有目标，不能把缓存目标称为每帧都观测到。此策略针对稳定支架，不覆盖目标任意大幅移动。

## 时间与误差的含义

- 500 Hz 是仿真物理／关节控制步频，执行日志为 50 Hz，回放为 25 fps。
- 反馈观察使用固定 **0.15 s 仿真延迟**，期间物理会推进；移动目标初始观测使用 **1.0 s 仿真延迟**。实际 GPU 推理、排队、深度配准与规划的墙钟耗时独立记录。等待期间仍存在仿真暂停，不能称为硬件实时视觉控制。
- `visual_servo[].observations` 记录每次拍摄时刻、使用时刻、视觉残差、候选修正幅度、循环墙钟时间和仿真时间。反馈观测频率按完成估计的观察数除以该反馈阶段墙钟耗时计算，包含随后被安全范围检查拒绝的估计；它不是实际动作修正频率，也不用网络单次推理速度替代。达到误差阈值时不执行候选修正，实际完成次数另记为 `corrections`。
- `before_evaluation_only`、`after_evaluation_only` 以仿真真值独立计算实际对准误差；这些数值不会进入反馈决策。视觉残差下降不一定表示真实几何误差下降，两者分开报告。
- 扰动恢复时间仅对实际送达扰动、且视觉收敛的阶段有定义，从脉冲开始计到确认收敛；它不能替代最终物理成功率。

对准诊断比较物体参考坐标系：`T_goal_true = T_mount_true @ inv(T_mount_visual) @ T_goal_visual`，再与真实物体位姿比较。它替换安装基座／支架的视觉变换，保留重建特征定义的目标关系，不是最终孔隙或插入深度的测量；后者由最终物理验收另行记录。

## 正式矩阵与统计

[冻结配置](../configs/visual_feedback_48.json)：`complete` 四阶段完整任务 × 三种反馈模式 × 无扰动／对准扰动 × 每配置 8 次，共 **48 次**，使用新种子 **400–407**。开发种子 0 及所有调试尝试不进入统计。三个模式在每个任务／种子下的初始物理状态哈希必须一致。

按组员要求将新评测缩减至约 50 次，集中比较完整流程，仍记录锤子、螺丝刀、支架、扳手各阶段的到达次数与验收结果；这些是整链中的阶段统计，不是四套独立任务试验。原 `visual_feedback_v1` 的 240 次计划已中止派发，启动过的试验和原协议单独保留，不选择其中的结果混入新统计。缩减只改变评测配置，不修改控制器。

对准扰动 `alignment_impulse` 在名义对准完成时施加世界坐标力 `[1.5, 0, 0] N` 和力矩 `[0, 0.03, 0] N·m`，持续 0.12 s；它在分阶段复测之后、迭代反馈之前发生。完整流程三个适用阶段各施加一次。环境只施力，不传递真实位姿、偏移量，不瞬移物体。未到达某阶段的失败保留，并明确该扰动未送达。

统计包括整条任务／分项任务成功率及 Wilson 95% 区间，完整流程的阶段即时验收与到达次数，初始 6D 位姿误差和 5 mm／5° 通过率、ADD／ADD-S，固定相机标定误差，TCP 轨迹／终点误差、最终物体误差，耗时和实际更新频率，以及有／无扰动变化。连续指标先按试验汇总，再做 10,000 次 bootstrap；不把一条轨迹的多帧作为独立试验。

对准前后指标只存在于实际到达该阶段的试验，必须附带样本量；不把未到达阶段记成零误差，也不以该条件性诊断替代整条任务成功率。完整流程早期阶段通过不等于最后仍保持成功，整条任务仍须通过最终所有物体的重新验收。

本轮比较反馈模块的整体效果，未增加“同样等待时间但不看图像”的第四组。观察等待会推进物理过程，零修正阶段的误差变化也可能来自自然静置；不能把所有前后误差下降都归因于纠偏动作。

主要配对比较为 `iterative` 对 `open_loop`、`iterative` 对 `staged`，报告保守差值区间、精确 McNemar 检验及同一检验族内 Holm 校正。有／无扰动比较单独组成检验族。每格只有 8 次，适合课程作业中的初步对比，不能预设新增反馈一定改善所有任务，也不能保证统计显著。

## 运行

```bash
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
FP_PYTHON=/path/to/foundationpose/env/bin/python
.venv/bin/python scripts/run_workshop.py --task complete \
  --visual-feedback iterative --disturbance alignment_impulse \
  --feedback-delay 0.15 --sensor-delay 1.0 --trace --seed 0 \
  --foundationpose-python "$FP_PYTHON" --output artifacts/feedback_development_new
```

正式运行使用 [统一评测文档](EVALUATION.md) 中的 GPU 服务，将 `run_benchmark.py` 配置改为：

```bash
MA6216_POSE_SOCKET=/tmp/ma6216-feedback.sock .venv/bin/python scripts/run_benchmark.py \
  --config configs/visual_feedback_48.json --jobs 8 --timeout 2400 \
  --foundationpose-python "$FP_PYTHON" --output artifacts/visual_feedback_48
.venv/bin/python scripts/summarize_benchmark.py \
  --source artifacts/visual_feedback_48 --output docs/results/visual-feedback-v1
.venv/bin/python scripts/package_benchmark_evidence.py \
  --source artifacts/visual_feedback_48 --results docs/results/visual-feedback-v1
.venv/bin/python scripts/write_feedback_report.py --results docs/results/visual-feedback-v1
```

图表导出与核对见[绘图说明](VISUAL_FEEDBACK_FIGURES.md)。视频按 `evidence_manifest.json` 中的 `replay_inputs` 回放，使用 `scripts/replay_trial.py`；完整成功轨迹另外传入 `--export-wrist`。这些步骤读取原始记录，不产生新的统计试验。

控制源码变更会阻止续跑，不能用调试后的代码替换正式失败。正式运行结束后逐文件校验并无损压缩 RGB-D 输入，保留本机原始轨迹；在对应试验目录运行 `tar -xzf observations.tar.gz` 可还原原路径。所选视频必须直接回放原试验状态，不重新执行后替换结果。

历史 [240 次模块消融](results/evaluation-v1/README.md)、[40 次工具架复测](results/rack-revision-v2/README.md) 和[固定布局完整演示](results/complete-workshop/README.md) 保留各自版本和统计边界。
