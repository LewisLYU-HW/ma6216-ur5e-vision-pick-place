# 工具架自装配与承重挂放

`--task rack` 把工作站原来固定的挂钩换成一个可抓取的独立 L 形支架。机器人需要先装好它，再把扳手挂上去；安装结果会成为后续动作的真实障碍物和承重部件。

## 操作过程

1. 固定 RGB-D 相机定位横放的支架、扳手和底座标记。
2. 夹起支架，使用腕部 RGB-D 纠正持物关系；从横放转到竖直，按完整 6D 变换对准非对称插口。
3. 以 2 mm 插入步长、7 N 接触力增量保护插入，实际松爪并等待稳定。
4. 重新观察装好的支架，将其重建表面加入后续碰撞规划。
5. 夹起扳手，放到两根轨道上，实际释放、重新观察、换抓。
6. 调整扳手孔平面，缓慢穿过新挂钩，再释放并检查扳手和支架的稳定性。

物体位姿来自官方 FoundationPose 的参考图像重建流程。支架的局部深度配准使用测量点云和重建表面，原始网络结果另存。装后支架与同图夹具标记的相对位姿用于消除共享外参误差；夹具的最新腕部观测提供全局定位。

自由转向的规划为装后支架保留 20 mm 间距，慢速接近保留 4 mm。所持扳手也参与间距检查。关节跟踪偏差超过 0.010 rad 时暂停推进当前路径，等待执行器追上指令；依据关节编码器，不读物体真值。这会增加动作时长，实际耗时与误差均进入评测。

## 运行与录像

```bash
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
FP_PYTHON=/path/to/foundationpose/env/bin/python

.venv/bin/python scripts/preview_workshop.py --rack-assembly \
  --output artifacts/rack_preview

.venv/bin/python scripts/run_workshop.py --task rack --trace --record \
  --foundationpose-python "$FP_PYTHON" --output artifacts/rack_new

xdg-open artifacts/rack_new/video/overview_wrist.mp4
```

交互预览加 `--viewer`，需要桌面显示。输出目录必须是新目录。`--ground-truth` 仅供明确标记的机械诊断，不能进入视觉评测。

`--trace` 保存原试验的 25 Hz 状态，可用 [`replay_trial.py`](../scripts/replay_trial.py) 输出全景与腕部 H.264 视频。回放不重新推理、不重新运行物理试验；不能将回放过程中的状态写入当成控制器搬运物体。

## 几何与验收

支架总质量假设为 0.15 kg，扳手为 0.10 kg。支架榫头截面约 24×18 mm，带非对称切角，插入段长 36 mm，插口边界间隙 1.5 mm；立柱和挂钩完全通过接触保持，没有焊接到基座，也没有抓取附件约束。

支架验收要求位置误差 <4 mm、方向误差 <8°、底部间隙绝对值 <2 mm、槽壁侵入不超过 0.7 mm、接触法向力合计 >0.2 N，以及无夹爪接触和足够小的线/角速度。挂上扳手后再次验收支架。扳手还须通过孔的位置、孔平面方向、挂钩承重接触和松爪稳定性检查；仅靠近挂钩、浮在空中或靠在立柱上都不算成功。

支架重建包见 [`assets/reconstructed/workshop/rack_frame`](../assets/reconstructed/workshop/rack_frame)：24 组 480×480 RGB-D、官方 Neural Object Field 1500 步、0.8 mm 提取分辨率。它不是直接复制的仿真 CAD，也不是打印模型。插口、工位和参考操作坐标系由任务定义。

质量分配、指垫摩擦、接触柔顺和理想深度属于仿真假设，尚未经实物标定。接触法向力合计可能包含侧壁力，不能直接解释为竖直载荷。全部成功率、误差、频率和失败样例按 [统一评测协议](EVALUATION.md) 汇总。
