# MA6216 · Model-free 6D 维修工具工作站

**分支：`feat/model-free-manipulation`** · UR5e + Robotiq 2F-85 · MuJoCo · 官方 FoundationPose

本分支接续小组原有抓放与码垛仿真，新增带真实扫描纹理的**维修工具工作站**：锤子归位、移动螺丝刀抓取与倾斜插架、扳手换抓与穿孔挂放，以及**先装好工具架、再挂上扳手承重**的多阶段任务。
先从标定 RGB-D 参考图重建工具，再用官方 FoundationPose 估计 **6D pose（三维位置＋三维朝向）**，驱动实际接触下的夹持、转向、插入和悬挂。新工作站采用深度背景分割，无需给工具涂分割色。
原有的视觉装配恢复、遮挡换抓和运动目标抓取任务继续保留。

[48 次闭环评测](docs/results/visual-feedback-v1/README.md) · [视觉反馈方法](docs/VISUAL_FEEDBACK.md) · [完整连续任务](docs/COMPLETE_WORKSHOP.md) · [演示视频](docs/videos/README.md) · [工具架自装配](docs/RACK_ASSEMBLY.md) · [统一评测](docs/EVALUATION.md) · [安装](docs/SETUP.md) · [小组 PR #3](https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/pull/3)

## Final Project：估计标定版本的 48 次复测与英文汇报

**[课程 Task 1–6 与 Bonus 交付总览](docs/FINAL_PROJECT.md)** · **[全英文 PPT／PDF／讲稿](docs/presentation/README.md)** · [英文文献与技术选型](docs/LITERATURE_AND_SELECTION.md) · [新版本完整指标报告](docs/results/visual-feedback-calibrated-v1/README.md) · [新版本完整及失败录像](docs/videos/visual-feedback-calibrated-v1/README.md)

使用图像估计的腕部内参与手眼变换，重新完成 **48 次**四阶段完整流程：三种反馈模式 × 有／无对准扰动 × 每配置 8 次。沿用种子 400–407，属于配对复测，不称为新的留出测试；全部失败保留。

| 模式 | 无扰动 | 有对准扰动 |
|---|---:|---:|
| 无执行期视觉纠偏 | 0/8 | 0/8 |
| 关键阶段反馈 | 3/8 | 2/8 |
| 迭代视觉闭环 | 3/8 | 3/8 |

四项方法比较的 Holm 校正 p 均为 1.0；当前小样本不能证明优越或等效。报告包含置信区间、阶段到达与验收、6D 位姿、标定、执行误差、观测频率和扰动恢复。主要瓶颈仍为初始抓取与规划；有扰动阶段反馈另有一次扳手接近挂架时失去双侧夹持的失败。完整演示与统计分开解释。

英文汇报已重做为学术汇报版：22 页可编辑 PPT（21 页正文＋1 页参考文献），按研究问题、方法、实验设计、结果和局限组织；含 12 组处理后的科学证据图、48 处实际图像子图和 1 幅统计图。附 PDF、英文讲稿及可编辑 PDF／SVG 图版，正文约 12–15 分钟，新版直接覆盖原文件。文献候选与项目实际运行的内部对照明确区分，未声称做过外部位姿算法排名。以下旧版报告和视频保持其原始条件，不与这次数据混合。

## 腕部估计标定与定位专项评估

已补齐课程 Task 2/3 的腕部图像标定：内参独立验证重投影 **0.02177 px**，手眼误差 **0.852 mm／0.0227°**，冻结整条坐标链的验证重投影 **0.05497 px**。正常工具任务默认加载估计参数并通过机器人 FK 传播，不再直接读取仿真腕部相机内参或安装变换。

Task 4 对当前四工具完成 **50个场景观测、200次定位查询**，覆盖正常、位置与朝向变化、遮挡、深度噪声和目标缺失。正常场景平均 mask IoU **0.887**；160次有目标查询均达到预定 IoU≥0.5，40次目标缺失查询均未误检，保留每组10次的置信区间。另单独保留背景失配的开发故障和失败图片，不混入正常流程统计。

**[Task 2/3/4 实现、坐标链与运行](docs/CALIBRATION_LOCALIZATION.md)** · [腕部标定原始图像与指标](docs/results/wrist-calibration-v1/README.md) · [工具定位指标、全部 mask 与失败案例](docs/results/workshop-localization-v1/README.md)

新标定接入后的无扰动／有扰动两次完整任务均通过，属于开发回归，不作为成功率估计。[接入记录与新录像](docs/results/calibrated-workshop-v1/README.md)。

以下48次视觉反馈结果属于此前的理想腕部标定版本，保持原始数据和冻结提交；不能当成使用本轮估计标定后的成功率。

## 6D 视觉反馈：此前48次配对评测

新增独立的 `--visual-feedback open_loop/staged/iterative` 开关，对比无执行期视觉纠偏、关键阶段纠偏、以及接近插口／挂钩时的重复观察和限幅修正。保留相同的关节控制与接触保护，单独记录视觉残差、实际几何误差和反馈耗时；对遮挡造成的支架估计跳变执行质量检查。[反馈流程、统计协议与复现](docs/VISUAL_FEEDBACK.md)。

按约 50 次的规模完成 **48 次正式评测**：完整四阶段任务 × 三种模式 × 有／无对准扰动 × 每配置 8 次，种子 400–407 配对，失败全部留在分母。

| 模式 | 无扰动：成功数及 Wilson 95% CI | 对准扰动：成功数及 Wilson 95% CI |
|---|---|---|
| 无执行期视觉纠偏 | 0/8；0.0%–32.4% | 0/8；0.0%–32.4% |
| 关键阶段反馈 | 3/8；13.7%–69.4% | 3/8；13.7%–69.4% |
| 迭代视觉闭环 | 2/8；7.1%–59.1% | 3/8；13.7%–69.4% |

**新增迭代闭环没有显示出高于关键阶段反馈的整链成功率**，四项方法比较的 Holm 校正 p 均为 1.0；小样本不能证明优越或等效。每配置均有 4 次运动螺丝刀抓取接触保护失败和 1 次锤子取件规划失败，这些发生在新增对准闭环之前。迭代模式另有一次挂放后速度未达稳定阈值的失败，未放宽验收。

**[正式试验的完整全景＋腕部](docs/videos/visual-feedback-v1/complete__iterative__none__400.mp4)** · **[同次独立腕部](docs/videos/visual-feedback-v1/complete__iterative__none__400__wrist.mp4)** · [3 条失败与同种子对照](docs/videos/visual-feedback-v1/README.md)

完整视频来自最低成功种子 400 的原始连续轨迹，包含锤子归位、运动螺丝刀抓取与倾斜插架、独立支架安装和扳手松爪换抓／穿孔挂放。画面中的 `VISION residual` 是视觉残差，不能当作真实定位精度。

[独立复核](docs/results/visual-feedback-v1/hero_motion_audit.json)在保存的 25 Hz 快照中未发现非预期机器人穿透或最终松爪后夹爪继续承重；额外静置 30 秒，四个物体仍全部通过验收。该复核不改变正式试验判定。

[全部指标与置信区间](docs/results/visual-feedback-v1/README.md)包括阶段到达／成功率、6D 位姿、标定、执行误差、真实对准误差、观测频率及扰动恢复；[逐次闭环 CSV](docs/results/visual-feedback-v1/visual_feedback_observations.csv)可核对视觉与真实误差。原先中止计划中的 16 次试验单独存档，不混入本轮，历史报告也保持原版本。

## 历史完整演示：阶段反馈、固定布局

**[完整全景＋腕部视频](docs/videos/complete-workshop/overview-wrist.mp4)** · **[同次运行的独立腕部](docs/videos/complete-workshop/wrist.mp4)** · [运行与验收记录](docs/results/complete-workshop/README.md)

扫描锤子归位 → 运动螺丝刀抓取与倾斜插架 → 安装独立工具架并重新定位 → 扳手松爪换抓、穿孔挂放。四个物体从开始就处于同一个场景，依次操作，前面已归位的工具留在原位。

![完整场景：锤子、运动螺丝刀、独立支架和扳手](docs/media/complete-workshop-overview.png)

使用 `--task complete` 运行，详见 [完整任务复现](docs/COMPLETE_WORKSHOP.md)。录像约 **3 分 14 秒**，来自同一次视觉运行的连续状态，保留四阶段及挂放后的 10 秒稳定等待。四件物体均通过最终验收和额外 30 秒静置复核。它是固定布局演示，不计入下面两轮独立评测的成功率。

## 独立工具架任务与 40 次复测

![横放的独立支架、带孔扳手与待装底座](docs/media/rack-assembly-overview.png)

`--task rack` 将固定挂钩换成可抓取的独立支架。机器人从横放姿态取起支架，腕部 RGB-D 复测后转为竖直，对准非对称插口并插入；松爪确认落座，再重新观察支架、换抓扳手，将环孔穿过新挂钩，最后检查两者的承重和稳定性。

6D pose 同时用于支架朝向、插口对齐、夹持关系纠偏和扳手孔平面转向。装好的支架成为下一阶段的真实碰撞障碍与承重部件。支架没有固定到基座；搬运和悬挂靠实际接触完成。

```bash
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
FP_PYTHON=/path/to/foundationpose/env/bin/python
python scripts/run_workshop.py --task rack --record --trace \
  --foundationpose-python "$FP_PYTHON" --output artifacts/rack_new
```

[任务流程、尺寸和验收](docs/RACK_ASSEMBLY.md) · [修复后的全景＋腕部](docs/videos/rack-revision-v2/rack__full__none__202.mp4) · [独立腕部](docs/videos/rack-revision-v2/rack__full__none__202__wrist.mp4) · [动作修复说明](docs/RACK_MOTION_REVISION.md)

装架后的大幅绕行和反复停顿已修正：衔接两次扳手抓姿、增加释放后的撤离距离，并补偿位置执行器的速度滞后。修改后用新种子 200–209 另做工具架 **40 次配对评测**，每配置仍为 10 次；[新版完整指标及置信区间](docs/results/rack-revision-v2/README.md)单独报告。当前仍有部分布局抓取规划失败，以及规定等待时间内摆动未降至验收阈值的情况，全部计入失败。

新版完整方法无扰动 **3/10**（95% CI **10.8%–60.3%**）、有扰动 **2/10**（**5.7%–51.0%**）；关闭腕部观测均 **0/10**（**0%–27.8%**）。配对差异未达显著，不能宣称架构全面优越或成功率提高。[当前失败与同种子对照](docs/videos/rack-revision-v2/README.md)同时包含完整方法自身的失败。

## 历史：240 次统一评测与失败案例

以下对应工具架动作修复前的版本：六类任务 × 完整方法/模块消融 × 无扰动/规定扰动 × 每配置 10 次，使用相同种子 100–109 配对。每格为成功数/10；**全部置信区间、位姿误差、标定误差、执行精度、频率及动态扰动结果**见 [首轮完整报告](docs/results/evaluation-v1/README.md)。旧版工具架数据不混入新版统计。

| 任务 | 完整：无扰动 | 完整：有扰动 | 基线 | 基线：无扰动 | 基线：有扰动 |
|---|---|---|---|---|---|
| 装配恢复 | 10/10 | 10/10 | 关闭恢复 | 10/10 | 0/10 |
| 遮挡换抓 | 10/10 | 10/10 | 仅平移＋yaw | 0/10 | 0/10 |
| 运动抓取 | 10/10 | 10/10 | 关闭运动预测 | 0/10 | 0/10 |
| 螺丝刀插架 | 5/10 | 5/10 | 关闭腕部观测 | 4/10 | 4/10 |
| 扳手挂放 | 9/10 | 10/10 | 关闭腕部观测 | 2/10 | 1/10 |
| 工具架自装配 | 7/10 | 7/10 | 关闭腕部观测 | 0/10 | 0/10 |

工具架 7/10 的 Wilson 95% 区间为 **39.7%–89.2%**；0/10 为 **0%–27.8%**。本轮支持部分模块在这些场景中的作用，但不能据此宣称整体架构全面优越：插架差异不明确，工具架及无扰动挂放的配对差异也未达到本轮 Holm 校正后的 0.05 门槛。

![六类任务成功率与 95% 区间](docs/results/evaluation-v1/figures/success_rates.png)

[6 条失败录像与同种子完整方法对照](docs/videos/evaluation-v1/README.md) · [240 条原始摘要与 CSV](docs/results/evaluation-v1/) · [评测协议与复现](docs/EVALUATION.md)

视频回放原试验保存的物理状态，不重新运行后替换失败；选中的原始轨迹也已随仓库保存。旧版主视频 seed 101 的最终承重验收通过，但过程中存在绕行与停顿，现作为历史记录保留。新版主视频入口见上方，成功演示不代表每次运行都成功。

## 新场景：维修工具归位

![维修工作台：扫描锤子与螺丝刀、带孔扳手、送料台、换抓架和倾斜套筒](docs/media/workshop-overview.png)

| 步骤 | 机器人操作 | 6D pose 的作用 |
|---|---|---|
| 锤子归位 | 从台面夹起扫描锤子，转向后放在停放架上 | 依据估计的工具坐标系构造抓取和放置关系 |
| 运动螺丝刀插架 | 跟踪 3 mm/s 送料台上的螺丝刀，在运动时抓取，腕部复测后插入倾斜 8° 的套筒 | 重建轴线和尖端、接触位置预测、完整姿态变换与插入对齐 |
| 扳手换抓挂放 | 放上两根支撑轨，实际松爪、重新观察与换抓，转为竖直后将环孔穿过挂钩 | 从重建表面找孔，调整孔平面与挂钩轴线，再释放并验证稳定支撑 |

[完整全景＋腕部视频](docs/videos/workshop-overview-wrist.mp4) · [独立腕部视频](docs/videos/workshop-wrist.mp4) · [复现、尺寸和限制](docs/WORKSHOP.md) · [实验结果](docs/results/workshop.json)

使用已配置的仿真环境与 FoundationPose GPU 环境：

```bash
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
FP_PYTHON=/path/to/foundationpose/env/bin/python
python scripts/run_workshop.py --task all --record \
  --foundationpose-python "$FP_PYTHON" \
  --output "artifacts/workshop_$(date +%Y%m%d_%H%M%S)"
```

此前 seed 0 完整视觉演示通过：螺丝刀插入 **36.41 mm**、轴线误差 **2.83°**；扳手松爪后由挂钩稳定承载。
完整录像 **121.4 秒**。这些历史数字来自固定配置演示，单独保留，不混入新的统一评测。

![螺丝刀插架并松爪后的全景与腕部画面](docs/media/workshop-insertion.png)

`--task insert` / `--task hang` 可分别运行；`python scripts/preview_workshop.py --viewer` 打开交互场景。
每件工具的参考重建模型与纹理已放进仓库，运行任务无需重新训练。完整安装见下方“组员快速开始”。

## 原有三个任务与视频

| 任务 | 机器人做什么 | 6D pose 用在哪里 | 全景＋腕部录像 |
|---|---|---|---|
| **装配与恢复** `assembly` | 从倾斜料架取件；夹具移位后触发接触保护，撤退、重定位并重试 | 完整抓取变换、腕部朝向校正、工件与夹具的相对位姿 | [观看视频](docs/videos/model-free-assembly-overview-wrist.mp4) |
| **遮挡与重抓** `clutter` | 搬走障碍物；侧抓平躺工件，翻转放上支架，松爪后换抓姿并插装 | 识别平躺姿态、构造侧抓关系、翻转与重新抓取 | [观看视频](docs/videos/model-free-clutter-overview-wrist.mp4) |
| **运动目标抓取** `conveyor` | 连续观察送料台上的工件，预测接触位置，在台面运动时夹取并插装 | 带时间戳的位姿跟踪、速度估计、接触时刻预测和腕部校正 | [观看视频](docs/videos/model-free-conveyor-overview-wrist.mp4) |

另有 [关闭自动恢复的失败对照](docs/videos/model-free-no-recovery-overview-wrist.mp4)：相同初始场景和夹具扰动，第一次接触保护后停止。
四段 H.264 视频均直接保存在仓库中；点击可查看或下载。每段左侧为全景，右侧为腕部视角。

![遮挡任务中，机器人将翻转后的工件放上重抓支架；左全景、右腕部](docs/media/model-free-regrasp.png)

上图取自已验证的遮挡重抓录像，展示放上支架、准备松爪换抓姿的阶段。

## 本分支增加了什么

| 原项目基础 | 本分支扩展 |
|---|---|
| RGB-D、颜色 mask、已知工件 CAD 输入 FoundationPose | 标定参考 RGB-D → 官方 Neural Object Field → 重建表面，无需输入工件 CAD |
| 固定相机定位后抓放、码垛 | 固定相机初定位＋腕部近景重定位，校正夹持关系与朝向歧义 |
| 预先定义的静态放置目标 | 夹具移位后的接触保护与重试、支架换抓姿、运动目标预测抓取 |
| 物理抓放及支撑验收 | 分别记录感知误差与最终落座误差，并提供恢复关闭对照 |

机械臂、夹爪、标定与基础抓放来自原项目；本分支接入并调用官方 FoundationPose，重建与位姿网络的来源见 [第三方说明](THIRD_PARTY_NOTICES.md)。
原阶段的功能、课程任务对应关系和实验记录见 [原项目总览](docs/BASELINE_PROJECT.md)。

## 系统流程与 Model-free 的含义

```mermaid
flowchart LR
  R[标定参考 RGB-D] --> N[官方 Neural Object Field]
  N --> M[重建表面与纹理]
  C[固定相机 / 腕部 RGB-D] --> P[官方 FoundationPose]
  M --> P
  P --> T[工件完整 6D 位姿]
  F[RGB-D ArUco 夹具定位] --> A[抓取变换与碰撞规划]
  T --> A
  A --> E[关节执行器与物理夹持]
  E --> W[腕部观察与接触监控]
  W --> P
  W --> A
```

这里采用 FoundationPose 的 **few-shot model-free** 路线：每件工件使用 24 张参考 RGB-D、mask 和扫描相机标定，先重建，再调用官方 `register()` / `track_one()`。
工件感知与碰撞规划使用 [仓库内的重建模型包](assets/reconstructed/README.md)，可以直接复现任务；也可按 [重建说明](docs/MODEL_FREE_TASKS.md)自行生成模型。

夹具几何、标记安装关系和操作坐标系由任务定义。参考扫描采用理想合成标定；固定任务相机和腕部相机现在均使用棋盘图像估计标定，腕部相机再结合机器人 FK 更新世界位姿。此前评测使用的理想腕部假设在对应历史报告中保留。
工件由摩擦和双侧指垫接触保持，操作期间不通过写物体位置实现搬运。

## 历史单次演示结果

以下为本工作站 **seed 0 的三个完整视觉演示及一个失败对照**。位置与角度误差指松爪、稳定后的物理落座结果，视觉估计误差单独记录。

| 场景 | 验收结果 | 最终位置误差 | 最终角度误差 | 关键观测 |
|---|---|---|---|---|
| 装配与恢复 | 第二次插装成功 | 0.19 mm | 0.35° | 首次约 8 N 力增量触发保护，腕部重定位后重试 |
| 部分遮挡与重抓 | 成功 | 2.88 mm | 0.39° | 清障后前景像素 4478 → 5360；完成三次实际夹持 |
| 运动目标抓取 | 成功 | 0.54 mm | 0.43° | 视觉速度约 3.99 mm/s，送料设定为 4 mm/s |
| 关闭自动恢复 | 预期失败 | — | — | 首次保护后停止，无第二次插装 |

三个成功运行均通过槽底支撑和松爪后稳定性验收；7 项回归检查通过。数据与视频对应关系见 [结果摘要](docs/results/model-free-tasks.json) 和 [视频校验清单](docs/videos/manifest.json)。
这些历史结果仅覆盖列出的单次仿真场景；遮挡示例的最小槽壁余量约 0.01 mm。新的有限布局测试见上方统一评测；广泛随机场景、硬实时或真机效果仍未验证。

## 组员快速开始

首次下载时直接指定本分支：

```bash
git clone --branch feat/model-free-manipulation https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place.git
cd ma6216-ur5e-vision-pick-place
```

已有本地仓库时，在仓库目录切换：

```bash
git fetch origin
git switch feat/model-free-manipulation
git pull --ff-only
```

先按 [SETUP.md](docs/SETUP.md) 配置仿真环境、Menagerie 机器人模型、官方 FoundationPose 与权重。
下面的 `python` 使用仿真环境，`FP_PYTHON` **需替换为你已配置的 FoundationPose 环境的 Python 路径**；两个环境可以分开。
默认官方源码目录为 `third_party/FoundationPose`，其他位置用 `--foundationpose-repository` 指定。使用附带模型包运行任务无需重新训练重建模型。

```bash
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl
FP_PYTHON=/path/to/foundationpose/env/bin/python
RUN_DIR="artifacts/model_free_$(date +%Y%m%d_%H%M%S)"

python scripts/run_model_free_task.py --task assembly \
  --plug-model assets/reconstructed/plug \
  --foundationpose-python "$FP_PYTHON" \
  --output "$RUN_DIR/assembly" --record

python scripts/run_model_free_task.py --task clutter \
  --plug-model assets/reconstructed/plug --blocker-model assets/reconstructed/blocker \
  --foundationpose-python "$FP_PYTHON" \
  --output "$RUN_DIR/clutter" --record

python scripts/run_model_free_task.py --task conveyor --belt-speed .004 \
  --plug-model assets/reconstructed/plug \
  --foundationpose-python "$FP_PYTHON" \
  --output "$RUN_DIR/conveyor" --record
```

每个任务输出 `summary.json`、RGB-D 观测、推理记录、运动日志及 `video/overview_wrist.mp4`。
在 Linux 打开录屏或运行回归检查：

```bash
xdg-open "$RUN_DIR/assembly/video/overview_wrist.mp4"
python scripts/check_model_free_tasks.py
```

`--disable-recovery` 用于恢复关闭对照；`--ground-truth` 是明确标记的物理控制诊断，不计作视觉结果。每次运行选择新输出目录。
详细环境版本、重建命令、传感器与验收判据见 [MODEL_FREE_TASKS.md](docs/MODEL_FREE_TASKS.md)。

## 从哪里读代码

| 文件 | 职责 |
|---|---|
| [run_workshop.py](scripts/run_workshop.py) / [workshop_scene.py](src/ma6216/workshop_scene.py) | 维修工作台的任务流程、工具架、送料台和物理道具 |
| [workshop_control.py](src/ma6216/workshop_control.py) / [workshop_perception.py](src/ma6216/workshop_perception.py) | 重建工具特征、保孔碰撞分片、深度前景与双视角录像 |
| [run_model_free_task.py](scripts/run_model_free_task.py) | 三任务的观测、抓取、重抓、恢复和验收流程 |
| [capture_model_free_references.py](scripts/capture_model_free_references.py)、[reconstruct_neural_object.py](scripts/reconstruct_neural_object.py) | 参考图采集与官方 Neural Object Field 重建 |
| [serve_model_free_pose.py](scripts/serve_model_free_pose.py) | 独立 GPU 进程，调用官方位姿注册和跟踪 |
| [task_perception.py](src/ma6216/task_perception.py)、[online_pose.py](src/ma6216/online_pose.py) | RGB-D、腕部相机、夹具定位、时间戳与运动预测 |
| [task_control.py](src/ma6216/task_control.py) | 抓取变换、IK、碰撞检查、力保护与物理执行 |
| [advanced_scene.py](src/ma6216/advanced_scene.py) | 三个工作场景、重抓支架、夹具扰动和移动送料台 |
| [check_model_free_tasks.py](scripts/check_model_free_tasks.py) | 模型来源、预测时间戳、抓取方向与物理验收的回归检查 |
| [run_benchmark.py](scripts/run_benchmark.py) / [evaluation.py](src/ma6216/evaluation.py) | 配对种子、扰动、原始测量与执行时间记录 |
| [summarize_benchmark.py](scripts/summarize_benchmark.py) / [write_benchmark_report.py](scripts/write_benchmark_report.py) | 置信区间、配对比较、完整中文报告 |
| [replay_trial.py](scripts/replay_trial.py) / [index_benchmark_videos.py](scripts/index_benchmark_videos.py) | 原始轨迹回放、视频元数据与来源校验 |

## 其他文档与历史阶段

| 入口 | 内容 |
|---|---|
| [工具架自装配](docs/RACK_ASSEMBLY.md) / [统一评测](docs/EVALUATION.md) | 多阶段装配承重、模块消融、置信区间与失败轨迹 |
| [详细复现](docs/MODEL_FREE_TASKS.md) / [历史实测数据](docs/results/model-free-tasks.json) | 三类 Model-free 任务的方法、命令、假设和单次验证记录 |
| [视频目录](docs/videos/README.md) | 三项新任务、恢复失败对照及原定向入槽录像 |
| [原项目总览](docs/BASELINE_PROJECT.md) / [版本选择](docs/VERSIONS.md) | v0.2 三工件、v0.3 多物品、v1.0 视觉码垛及课程任务对应关系 |
| [6D 定向入槽](docs/POSE_INSERTION.md) | 本分支继承的 Model-based 倾斜抓取与 yaw-only 对照 |
| [安装](docs/SETUP.md) / [小组协作](docs/TEAM_WORKFLOW.md) / [第三方来源](THIRD_PARTY_NOTICES.md) | 环境、分支与提交流程、官方依赖和资产来源 |

代码与演示位于小组原仓库的 `feat/model-free-manipulation` 分支，对应 [草稿 PR #3](https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/pull/3)。
