# 视觉反馈结果图的证据与导出约定

问题：迭代视觉反馈是否提高同一仿真任务的完成率，这种差异在对准扰动下是否保留？效果方向由完整评测数据决定，不预设新方法优于对照。

图 1 使用 quantitative grid。a 为无外加扰动的主要对比，b 为同种子的规定力／力矩扰动检验；两幅使用相同坐标、模式颜色和 Wilson 95% 区间。图 2 单独显示同种子的成功率差及保守 95% 区间，避免仅凭边际区间判断配对差异。两张图包括协议中全部任务、模式和环境，不选择有利子集。

统计单位为一次完整试验，每配置 8 次，共 48 次；失败留在分母。图 2 的区间来自 Bonferroni 调整的精确二项边际界限，相应配对 McNemar 检验和 Holm 校正在报告中列出。图不以星号省略精确检验或掩盖宽区间。

沿用仓库的 Python／matplotlib 流程；这是课程项目报告图，没有目标期刊的投稿规格。输出宽度 183 mm，文字不小于 7.5 pt，PDF／SVG 文字可编辑，同时提供 600 dpi PNG。每个点与误差线的数值写入同名 source-data CSV，并记录输入汇总文件的 SHA-256。没有图像面板、裁剪、插值或合成实验数据。

多面板导出前调用 `require_matplotlib_panel_alignment`，保留 1.5 pt 容差检查的 JSON；导出后检查 PDF 文字和遮挡，再查看整图及每个面板。审计工具目录由命令参数传入，不作为仿真运行依赖：

```bash
python3 scripts/plot_feedback_benchmark.py --results docs/results/visual-feedback-v1 \
  --qa-tools "$FIGURE_QA_DIR"
```

脚本拒绝绘制未完成的评测矩阵。最终 QA 结果、图注和实际数据一起存入结果目录的 `figures/`。
