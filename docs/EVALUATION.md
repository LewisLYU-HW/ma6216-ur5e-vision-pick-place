# 六类任务统一评测

本评测比较具名模块消融，不预设完整系统一定优于基线，也不将消融称为竞争性外部算法。正式结果使用冻结代码后的新种子，开发调试运行不混入统计。每个配置 10 次，完整矩阵为 **6 类任务 × 2 种方法 × 2 种环境 × 10 = 240 次**。

本轮已完成：[完整报告与图表](results/evaluation-v1/README.md) · [240 次逐试验数据](results/evaluation-v1/trials.csv) · [失败及配对视频](videos/evaluation-v1/README.md)。

[交付检查记录](results/evaluation-v1/validation.json)包含 23 项通过的回归检查日志，以及 11 段视频的完整解码、帧数、时长与校验值。可分别运行 `scripts/check_model_free_tasks.py`、`scripts/check_workshop.py` 和 `scripts/check_evaluation.py` 复查代码。

## 任务与对照

| 任务 | 基线替换 | 扰动环境 |
|---|---|---|
| 异形件装配恢复 `assembly` | `no_recovery`：接触限力停止后不重定位重试 | 第一次插入时底座移动 12、4 mm 并偏航 7° |
| 遮挡清除、换抓、装配 `clutter` | `yaw_only`：保留平移和 yaw，删除预测的 roll/pitch | 提起工件后施加规定的力/力矩脉冲 |
| 运动工件抓取、装配 `conveyor` | `no_prediction`：以最近一次观测位姿代替接触时刻预测 | 同上 |
| 螺丝刀插架 `insert` | `no_wrist`：关闭腕部物体/底座重定位与持物关系纠偏 | 提起螺丝刀后施加脉冲 |
| 扳手换抓、挂放 `hang` | `no_wrist` | 第一次提起扳手后施加脉冲 |
| 工具架自装配、承重挂放 `rack` | `no_wrist` | 提起独立支架后施加脉冲 |

每类均含无扰动环境。脉冲是世界坐标系下 `[1.5, 0, 0] N` 与 `[0, 0.03, 0] N·m`，持续 0.12 s，在目标第一次 `LIFT_SETTLE` 时触发。未到达触发阶段的失败仍计入任务成功率，另记 `disturbance_delivered=false`，不伪称经历了扰动。控制器不会收到扰动位姿。所有方法保留相同的碰撞、双侧夹持、力限和最终物理验收。

`yaw_only` 是 2.5D 位姿消融，原始 FoundationPose 预测仍完整存档。`no_recovery` 在无接触异常时可能与完整方法相同，这是对照设计的一部分。各方法不能只保存失败或只报告最有利的种子。

新支架在腕部观测后加入局部 point-to-plane ICP，用测得的深度与参考重建表面纠正 FoundationPose 残差；使用可见面筛选、6 mm 对应距离及稳健权重，并限制相对初始化的修正范围。该过程不读模拟物体位姿。原始网络输出、实际送入控制器的位姿、两者的误差和 ICP 耗时分别保存。`no_wrist` 同时失去该腕部深度纠偏，所比较的是整个腕部观测模块。

## 指标定义

- **任务成功率**：以释放后的几何位置、方向、真实承重接触、无夹爪支撑和静止稳定性判定。工具架任务还必须在挂上扳手后再次通过支架稳定性检查。报告每组成功数/10 和 Wilson 95% 区间。
- **6DOF 位姿误差**：平移欧氏误差 mm、SO(3) 测地角误差 °、5 mm/5° 联合阈值通过率、ADD 与 ADD-S。ADD 使用同一重建表面的固定采样点；ADD-S 另报告，不替代有方向要求的任务验收。辅助尺度阈值为重建包围盒对角线的 10%，不是标准真实物体直径。
- **可比的感知读数**：主要结果使用每次试验目标物体的第一张固定相机图像。准确率要求该任务所有初始目标均在 5 mm/5° 内，缺失预测算未通过，按试验报告 Wilson 95% 区间；CSV 中逐观测阈值平均值仅作描述。全部后续观测另外存 CSV，属于执行过程诊断；关闭腕部观测后观测数量不同，不能将这两组所有帧直接当成同分布样本。
- **标定误差**：固定相机内参相对误差、主点像素误差、外参 mm/°、原标定训练/验证图的重投影误差。标定文件在评测前冻结并计算 SHA-256。腕部手眼为理想仿真安装，独立标定误差记为不可用，不能声称测得 0。
- **执行精度**：以实际 TCP 对比执行器关节指令的正运动学，记录 50 Hz 轨迹误差与每次移动稳定后的终点误差；另列最终工件装配/插入/挂放误差。指令跟踪误差、感知误差、任务最终误差分别报告。
- **频率与耗时**：500 Hz 是仿真控制步频，50 Hz 是日志采样率，25 fps 是轨迹回放率。另测实际墙钟控制步吞吐、实时因子、注册/跟踪耗时、包括等待的位姿调用频率。系统使用间歇视觉更新，不能把 500 Hz 写成视觉闭环频率。
- **动态鲁棒性**：同一组种子的有/无扰动成功率及其变化，并记录扰动是否实际送达。运动抓取的配对评测使用固定 **1.0 s 仿真感知延迟**，实际 GPU 推理时间独立报告。普通交互演示未指定该参数时继续在实际推理等待期间运行物理仿真。

连续指标先按试验汇总，再对试验均值做 10,000 次 bootstrap；不会用同一轨迹的几千个相关帧虚增样本量。缺失测量保留样本量，失败不会从成功率分母剔除。方法差异列出配对胜/负、探索性精确 McNemar 检验及保守区间。10 次试验即使全成功，Wilson 区间下限也只有约 72.2%，不足以证明普遍优越性。

方法比较与扰动比较各自作为一组检验，另列 Holm 校正后的 p 值。固定相机只有一套离线标定解，不把 240 次重复使用它当作 240 次独立标定。静态观察的推理和离线规划等待期间暂停仿真；本评测不代表持续实时运行的真机控制。并行试验的墙钟吞吐包含共享硬件资源等待。

## 复现

配置见 [`configs/evaluation_v1.json`](../configs/evaluation_v1.json)，种子为 100–109。需先按 [Model-free 文档](MODEL_FREE_TASKS.md) 准备原仿真环境和官方 FoundationPose 环境。

这是有限范围的布局测试：原装配任务初始 roll/pitch 分别抖动 ±2°、yaw ±4°；原三个任务的夹具平面位置抖动 ±5 mm。工具工作站的上料平面位置抖动 ±4 mm。遮挡与运动任务的目标初始朝向固定；不是十种物体或十种独立真实环境。每个种子四种配置的初始物理状态 SHA-256 必须一致，汇总脚本会检查配对条件。

```bash
# 终端 1：串行共享 GPU 模型；多个试验只并行执行 CPU 仿真
FP_PYTHON=/path/to/foundationpose/env/bin/python
MUJOCO_GL=egl PYOPENGL_PLATFORM=egl OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python scripts/serve_pose_pool.py \
  --socket /tmp/ma6216-pose.sock \
  --python "$FP_PYTHON" \
  --output artifacts/pose_pool_new

# 终端 2：目录已存在时，仅续跑尚未完成的配置；控制源码变化会拒绝续跑
FP_PYTHON=/path/to/foundationpose/env/bin/python
MA6216_POSE_SOCKET=/tmp/ma6216-pose.sock .venv/bin/python scripts/run_benchmark.py \
  --jobs 8 --foundationpose-python "$FP_PYTHON" --output artifacts/evaluation_new

.venv/bin/python scripts/summarize_benchmark.py \
  --source artifacts/evaluation_new --output docs/results/evaluation_new

.venv/bin/python scripts/package_benchmark_evidence.py \
  --source artifacts/evaluation_new --results docs/results/evaluation_new
.venv/bin/python scripts/write_benchmark_report.py --results docs/results/evaluation_new
# 绘图所用 Python 需要 matplotlib；不要求与仿真环境相同
"$FP_PYTHON" scripts/plot_benchmark.py --results docs/results/evaluation_new
```

也可不启动共享进程，以 `--jobs 1` 使用每次试验独立的 GPU 进程。共享推理保留每个试验独立的跟踪历史和固定随机数初始化；不会在不同种子间传递位姿。

每次试验保留 `summary.json`、RGB-D、推理请求/回复、动作与接触事件、50 Hz 测量和 25 Hz 压缩物理状态。GPU/进程基础设施异常不伪装成算法失败；不完整试验会阻止最终报告。

本轮遇到一次并行纹理缓存读到空 PNG 的初始化异常，发生在控制器和任务执行创建之前。修复仅改为完整编码后原子替换文件，两张纹理的字节 SHA-256 前后一致。此前 70 次有效试验全部保留，仅该未初始化试验补跑；控制策略、几何、阈值、种子均未更改。原协议、异常尝试和修复版本通过 `protocol.json` 的 `source_amendments` 及 `infrastructure_incidents/` 完整记录。该情况不能当作方法失败，也不能静默删除。

证据打包脚本保存全部试验摘要、控制台日志和原始记录校验值；选中录像的原始轨迹同时放入 `replay_inputs/`，无需推理即可离线回放。其余完整 RGB-D 与轨迹保留在本机原始评测目录。成功工具架视频固定取无扰动完整系统的最低成功种子，失败视频使用下述预定规则。

## 失败录像

预先固定最多 6 条：按配置任务顺序，完整方法取前两个出现失败的任务，消融方法取前四个；各任务先选无扰动，再选有扰动，选择最小失败种子。其余失败仍保留日志与轨迹。录像使用原试验状态回放，不重新运行一遍后替换结果。

每条选中消融失败录像另外附上**相同任务、扰动和种子的完整方法录像**，无论完整方法成功还是失败都保留。它们是已有试验的配对回放，不增加或替换统计样本。

```bash
MUJOCO_GL=egl PYOPENGL_PLATFORM=egl .venv/bin/python scripts/replay_trial.py \
  --trial artifacts/evaluation_new/trials/任务__方法__环境__种子 \
  --output artifacts/replay_new --export docs/videos/failure-example.mp4
```

评测范围仍是合成 RGB-D、预先采集的校准参考扫描、已知工位区域与夹具设计、理想腕部手眼安装。这里的 Model-free 是官方参考图像重建流程：不向物体位姿估计和持物碰撞规划提供物体 CAD；不是无需参考扫描的零样本方案。

仿真几何、接触和速度真值用于阶段/终态验收与安全停机；不达标可以结束试验，但不会把真值位姿反馈给网络或生成运动纠偏目标。该评测不验证真机上的验收传感器与安全检测实现。
