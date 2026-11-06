# 斜角工件与前向抓放

新版使用绿色双斜面的凸工件，外形约 74 × 40 × 44 mm。MuJoCo 物理模型和 FoundationPose 使用同一组三角几何，输出目录下 `observation/mesh/workpiece.obj` 是导出的米制网格。工件两侧的平行面用于双指夹持。颜色分割从 RGB 计算目标 mask。FoundationPose 在估计相机外参与工件直立放在水平桌面的约束下，搜索覆盖 360° 的 24 个初始朝向，再用 RGB-D 精修和评分。实际摆放角仅用于初始化和误差评价。

在 WSL 终端运行以下命令。`--viewer` 打开实时 MuJoCo 窗口，`--record` 同时生成录屏。

```bash
cd ~/projects/ma6216-ur5e-vision-pick-place
conda activate foundationpose
RUN="artifacts/front_demo_$(date +%Y%m%d_%H%M%S)"
python -u scripts/run_front_pick_place.py --output "$RUN" --record --viewer
```

加上 `--xy .44 -.19 --yaw-deg 15` 可复跑已验证的第二组摆放。`--target cube` 在新路线中使用原红方块。原路线仍可通过 `scripts/run_vision_pick_place.py` 运行。`--output` 为每轮实验指定新目录。

## 路径和桌面布局

旧路线的搬运端点采用不同逆运动学分支。实测肩关节在搬运时转动约 169°，腕部第二关节转动约 180°。在原桌面布局中，所测试的同分支托盘上方姿态会让上臂与桌面相交约 33 mm。

新版保留桌高、相机、托盘和抓取区的世界坐标，将桌面靠基座一侧沿世界 X 从 0.14 m 退至 0.26 m，远边仍为 0.86 m。仿真从经过碰撞检查的桌前待机姿态开始。末端接近抓取点、垂直下降和抬升，在 0.56 m 计划高度沿桌面横移，最后垂直下降和撤离。笛卡尔路径按不超过 15 mm 的间隔求解相邻关节姿态，并检查关节段、机器人和携带工件的碰撞。

## 实测对照

旧、新路线用同一红方块的初始摆放和同一份保存的视觉估计，两者均通过物理验收。启动姿态和桌面布局分别采用各自的方案。执行时间从各自的待机状态开始计，包含仿真动作与停稳时间。

| 搬运指标 | 旧路线 | 前向路线 |
|---|---:|---:|
| 实测 TCP 路程 | 2.954 m | 0.367 m |
| TCP 顶视最大直线偏差 | 874 mm | 2.64 mm |
| TCP 高度变化范围 | 531 mm | 2.04 mm |
| 肩关节累计转动 | 168.89° | 40.25° |
| 腕部第二关节累计转动 | 179.99° | 0.026° |
| 仿真动作时间 | 40.68 s | 20.98 s |

两组绿色工件端到端试验均通过。默认位置为 `(0.46, -0.18)` m、0°，变位试验为 `(0.44, -0.19)` m、15°。平移误差为 4.12 / 4.32 mm，旋转误差为 0.56° / 0.91°。两次均抬升约 156 mm，搬运期间双指始终保持有载对向接触，最终所有网格顶点位于托盘内部，落点距托盘中心 0.82 / 0.25 mm。此处验证覆盖两个已测试的静止摆放。

- 仓库内 `docs/results/route-comparison.json` 和 `docs/media/transfer-top-view.png` 保存原路线对照摘要。
- `docs/media/green-workpiece-pick-place.mp4` 是第一组完整试验录屏。
- `docs/results/workpiece-front.json` 保存两组工件的数值结果。

可用 `python scripts/probe_direct_route.py --output "artifacts/compare_$(date +%Y%m%d_%H%M%S)"` 重新运行两种路线。默认输入是 `demo_data/reference_cube_world_pose.txt` 中保存的红方块视觉估计，两轮使用相同物体初始位置。
