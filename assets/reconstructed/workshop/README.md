# 工具参考重建包

四个目录均为官方 FoundationPose Neural Object Field 从 RGB-D 观测重建的结果，单位为米、坐标系为参考扫描坐标系。没有直接导出仿真 CAD 作为估计或碰撞规划输入，也没有按 CAD 尺寸事后缩放。

| 工具 | 参考图 | 训练步数 | 提取分辨率 | 仿真外观来源 |
|---|---:|---:|---:|---|
| `hammer` | 24 × 480×480 | 1200 | 0.8 mm | GSO 扫描锤子，50% 尺寸 |
| `screwdriver` | 24 × 480×480 | 1500 | 0.8 mm | GSO 扫描螺丝刀，75% 尺寸 |
| `spanner` | 24 × 480×480 | 1500 | 0.8 mm | 本项目生成的环孔开口扳手 |
| `rack_frame` | 24 × 480×480 | 1500 | 0.8 mm | 本项目生成的独立插接支架与承重挂钩 |

每个目录包含 OBJ/MTL/PNG、`model_free.json`、参考图哈希清单和训练配置。完整参考图与训练中间数据可按 [重建命令](../../../docs/WORKSHOP.md) 重新生成。固定官方提交、模型 SHA-256 和输入协议都记录在清单中。

扫描工具的派生外观及纹理保留 Google Scanned Objects / Laura Downs 等与 Kevin Zakka 的归属，许可沿用 CC BY 4.0；详见 [第三方来源](../../../THIRD_PARTY_NOTICES.md)。官方网络权重仍需独立安装。
