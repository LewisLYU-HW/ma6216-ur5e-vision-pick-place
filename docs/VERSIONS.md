# 阶段版本与组员复现

同一个公开仓库保存抓放与码垛的各个阶段。`main` 为最新整合代码；分支用于调试，版本标签用于固定复现，GitHub Release 提供版本说明和打印文件下载。

| 阶段 | 固定标签 | 对应开发分支 | 内容 |
|---|---|---|---|
| 三工件 | [v0.2.0](https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/releases/tag/v0.2.0) | `feat/multi-object-pick-place` | 绿色双斜角、橙色斜肩、紫色渐缩工件；一次连续视觉场景 3/3 |
| 多种类物品 | [v0.3.0](https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/releases/tag/v0.3.0) | `feat/diverse-object-library` | 锤子、球、带孔螺母；一次连续视觉场景 3/3；螺丝刀仅预览/打印 |
| 视觉码垛 | [v0.4.0](https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place/releases/tag/v0.4.0) | `feat/palletizing` | 四料块、两列两层；两组视觉试验各 4/4，包含层间支撑与稳定性验收 |

`v0.2.0` 固定在原提交 `8c165f8`。`v0.3.0` 保留 `ef04a4a` 的仿真功能，并补充版本交接说明。`v0.4.0` 加入视觉码垛，保留旧入口。这些标签不随后续开发移动；原 `v0.1.0` 也保留。

## 1. 为什么自动抓放中没有绿色螺丝刀

`run_multi_pick_place.py --collection diverse` 只加载并搬运已验证的三件：紫色锤子、红色球、黄色螺母。绿色螺丝刀属于模型库，已验证载入和导出，还没有验证抓取，不会出现在这个自动抓放场景里。

要同时查看四件物品，在 v0.3.0 或更新代码中运行：

```bash
conda activate foundationpose
python scripts/preview_object_library.py \
  --output "artifacts/library_preview_$(date +%Y%m%d_%H%M%S)" --viewer
```

该入口保持机械臂待机，不执行抓放；关闭窗口结束。截图里的三物件自动场景与文档里的四物件预览是两个入口。

## 2. 新组员复现三工件版本

公开仓库克隆无需登录。分别建立目录，能同时保留两版代码，避免频繁切换覆盖文件：

```bash
mkdir -p ~/projects
cd ~/projects
git clone --branch v0.2.0 --depth 1 \
  https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place.git \
  ma6216-workpieces-v0.2.0
cd ma6216-workpieces-v0.2.0
conda activate foundationpose
python scripts/check_setup.py --vision
python -u scripts/run_multi_pick_place.py \
  --output "artifacts/workpieces_$(date +%Y%m%d_%H%M%S)" --record --viewer
```

此旧版本没有 `--collection` 参数，直接使用上面入口。打印文件位于 `assets/printable`，三件尺寸分别为 74×40×44、64×38×42、68×42×48 mm。

## 3. 新组员复现多种类版本

```bash
cd ~/projects
git clone --branch v0.3.0 --depth 1 \
  https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place.git \
  ma6216-diverse-v0.3.0
cd ma6216-diverse-v0.3.0
conda activate foundationpose
python scripts/check_setup.py --vision
python -u scripts/run_multi_pick_place.py --collection diverse \
  --output "artifacts/diverse_$(date +%Y%m%d_%H%M%S)" --record --viewer
```

新机器先按各版本的 [SETUP.md](SETUP.md) 获取 Menagerie、FoundationPose 及权重，配置兼容的环境和本机路径。克隆源码不会复制开发者的 Conda 环境、显卡驱动或权重。完整视觉流程需要 CUDA；加 `--ground-truth` 只做明确标注的物理对照，不能当作视觉验证。

`--viewer` 打开实时窗口；无窗口环境去掉这个参数，每轮使用新输出目录。最新版也可用 `--collection workpieces` 运行旧类型场景，但若需要严格复现旧阶段，请选固定标签 v0.2.0。

## 4. 新组员复现码垛版本

```bash
cd ~/projects
git clone --branch v0.4.0 --depth 1 \
  https://github.com/LewisLYU-HW/ma6216-ur5e-vision-pick-place.git \
  ma6216-palletizing-v0.4.0
cd ma6216-palletizing-v0.4.0
conda activate foundationpose
python scripts/check_setup.py --vision
python -u scripts/run_palletizing.py \
  --output "artifacts/pallet_$(date +%Y%m%d_%H%M%S)" --record --viewer
```

`--layout 1` 使用位置和角度扰动，`--ground-truth` 为跳过视觉的明确物理对照。码垛模型、标定重跑、验收和实测范围见 [PALLETIZING.md](PALLETIZING.md)。

## 5. 已经克隆仓库的组员

先保存自己的修改，再获取分支和标签：

```bash
git status
git fetch origin --tags
```

只运行固定版可以使用 `git switch --detach v0.2.0` 或 `git switch --detach v0.3.0`。Git 的 detached HEAD 提示是因为标签固定指向一个提交；准备修改时，先从该版本创建自己的分支：

```bash
git switch -c feat/yourname-workpiece-testing v0.2.0
# 或者：git switch -c feat/yourname-tool-testing v0.3.0
```

公开仓库允许所有人拉取；直接推送仍需协作者权限，也可以 Fork 后提交 Pull Request。不要重打同名标签或强制推送覆盖其他组员的提交。

## 6. 打印与真机交接

- v0.2.0：`assets/printable` 中的 STL/OBJ；Release 附带三工件打印压缩包。
- v0.3.0：另外提供 `assets/printable_library`；Release 附带球、螺母、锤子和螺丝刀的打印压缩包。
- v0.4.0：另外提供 `assets/palletizing`；打印四份 80×50×40 mm 平顶料块，Release 附带模型压缩包。
- `*_print_mm.stl` 用于毫米制切片；`*_model_m.obj` 用于米制感知。两个扫描工具为原尺寸的 50%，STL 不带颜色，需核对清单尺寸。
- 各版本都是仿真项目和物体交接资源，尚不包含可直接运行的 UR5e 真机驱动。真机相机标定、TCP、坐标和控制接口由硬件组适配验证。螺丝刀抓取尚未验证；两列两层码垛的仿真结果见 v0.4.0。

已有视觉结果只覆盖记录中的指定布局，原始误差和范围见 [MULTI_OBJECT.md](MULTI_OBJECT.md)、[OBJECT_LIBRARY.md](OBJECT_LIBRARY.md) 和 [PALLETIZING.md](PALLETIZING.md)。后续功能在新分支开发，通过验证后发布新标签，已发布版本继续保留。
