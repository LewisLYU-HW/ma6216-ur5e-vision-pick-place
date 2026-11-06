# 工件导出、3D 打印和真机交接

## 已导出的文件

WSL 原件目录为 `/home/loutasaiya/projects/MA6216-VISION/assets/printable`。Windows 文件管理器可打开：

```text
\\wsl.localhost\Ubuntu-24.04\home\loutasaiya\projects\MA6216-VISION\assets\printable
```

| 工件 | 切片打印文件，毫米 | FoundationPose 文件，米 | 尺寸 XYZ / mm |
|---|---|---|---|
| 原绿色工件 | [green_print_mm.stl](../assets/printable/green_print_mm.stl) | [green_model_m.obj](../assets/printable/green_model_m.obj) | 74 × 40 × 44 |
| 橙色斜肩棱柱 | [orange_print_mm.stl](../assets/printable/orange_print_mm.stl) | [orange_model_m.obj](../assets/printable/orange_model_m.obj) | 64 × 38 × 42 |
| 紫色渐缩切角块 | [purple_print_mm.stl](../assets/printable/purple_print_mm.stl) | [purple_model_m.obj](../assets/printable/purple_model_m.obj) | 68 × 42 × 48 |

`manifest.json` 记录尺寸、几何体积、单位、打印坐标平移和每个文件的 SHA256。三个 STL 已重新载入检查：封闭、外向面、正体积，且尺寸与仿真几何一致。绿色 OBJ 与原绿色工件导出结果一致，其 SHA256 为 `7a469234401a45ee6faff8e8e54ed70a45446745eed7ef0b8594e8b860c3d73e`。这些是数字模型验证，不是打印机实物验证。

## 操作步骤

1. 在 Windows 文件管理器中打开上述目录，把 `green_print_mm.stl` 单独交给打印同学；也可以把整个目录交接，同时带上米制 OBJ 和清单。
2. 在切片软件中导入 STL，单位选毫米、缩放 100%。绿色工件应显示为 74 × 40 × 44 mm，底面在 Z=0。若显示为 0.074 mm 或 74000 mm，先纠正单位，不要凭外观打印。
3. 保持宽底面贴打印平台，检查切片预览和打印机可用范围。具体材料、支撑和打印参数由打印同学根据设备及切片结果确定。STL 本身没有颜色；当前分割依赖绿色、橙色和紫色外观，可选择相应材料或喷涂，并在真实光照下重新调颜色阈值。
4. 打印后用卡尺核对尺寸，测量实际质量，并确认夹持侧面平整、没有明显翘曲。仿真三件均配置 0.10 kg；这不是打印件预计质量，也不是模型体积自动推导的结果。
5. 向真机同学一起交付 CAD、尺寸、模型坐标约定和抓取配置。打印完成只建立了相同外形；真机相机内外参、实际 TCP、夹爪开口/力、机器人基座变换和控制接口仍需实测适配。现有感知链使用 RGB-D；仅有普通 RGB 图像不能原样替代深度输入。

## 模型坐标不能混用

感知使用 `*_model_m.obj`：单位米，保留仿真中物体原点。打印使用 `*_print_mm.stl`：顶点放大 1000 倍，并沿 Z 平移使底面位于 0。

绿色打印坐标满足 `p_print_mm = 1000 * p_model_m + [0, 0, 22]`；橙色 Z 平移为 21 mm，紫色为 24 mm。不要把底面原点的 STL 直接替换米制感知 OBJ，否则会引入比例或抓取高度偏差。模型中配置的抓取点在物体原点上方 3 mm，末端 pinch local Y 是两指闭合方向；它仍需转换为真机实测 TCP 的约定。

## 重新导出

原绿色工件最初由 Python 顶点程序生成，并没有必须先找到的独立 CAD 文件。新增导出入口读取同一份几何定义：

```bash
cd /home/loutasaiya/projects/MA6216-VISION
conda activate foundationpose
python scripts/export_workpieces.py \
  --output "artifacts/print_export_$(date +%Y%m%d_%H%M%S)"
```

该命令一次导出三个模型及清单。输出目录必须不存在，以保留已经交付的版本。日常打印直接使用已生成的 `assets/printable` 即可。
