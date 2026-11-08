# 48 次视觉反馈评测：图与源数据

图 1：[成功率](success_rates.pdf)（[SVG](success_rates.svg)、[600 dpi PNG](success_rates.png)、[源数据](success_rates.source-data.csv)）。两个面板覆盖无扰动和对准脉冲，每组 8 次，共六组。点为完整任务成功率，误差线为 Wilson 95% 区间；提前失败保留在分母。

图 2：[配对差值](paired_differences.pdf)（[SVG](paired_differences.svg)、[600 dpi PNG](paired_differences.png)、[源数据](paired_differences.source-data.csv)）。四项比较均为同种子的“迭代模式 − 对照模式”；区间使用 Bonferroni 调整的精确二项边际界限，是保守差值区间。配对 McNemar 检验与 Holm 校正见[报告](../README.md)，不以点估计的方向宣称优越性。

全部六组及四个配对区间已与 `summary.json` 逐项核对，没有选择性省略。两张图及图 1 各面板已人工查看，文字、图例和区间均清晰，无裁切或覆盖。数据来源 SHA-256 见 [provenance.json](provenance.json)，导出文件和绘图源码校验值见 [qa_summary.json](qa_summary.json)。

使用 Python／matplotlib，宽度 183 mm，PDF／SVG 保留可编辑文字。审计结果：

- 图 1 面板对齐通过；图 2 只有一个坐标轴，面板间对齐为 **N/A**，不称为通过。
- 两份 PDF 最小字形为 **7.5 pt**，无低于字号阈值的文字；遮挡检查均可审计，零警告、零失败。
- 源码检查 20 项通过、零失败；唯一警告是没有 TIFF。这里使用课程报告所需的 PDF／SVG 和 600 dpi PNG，未把该警告隐去。

各项原始 `*.alignment.json`、`*.text-audit.json`、`*.collisions.json` 及审计覆盖图均保留。[绘图约定及复现命令](../../../VISUAL_FEEDBACK_FIGURES.md)。
