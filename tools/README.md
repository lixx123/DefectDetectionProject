# tools（开发/验证脚本，非生产管线）

本目录收纳开发期临时脚本，不属于 `algorithm/` 生产流程，也不被 `main.py` 引用。

| 文件 | 用途 |
|---|---|
| `analyze_dead_code.py` / `analyze_dead_code_v2.py` | 死代码 import 闭包分析（v2 修正了 h3_b151 全链与 scripts_v3 裸导入） |
| `compare_final_output.py` | 两次运行最终输出逐字节比对（缺陷数 / 源面积 / 精确 mask） |
| `profile_j4_subset.py` | J4 子集 `cProfile` 剖析 |
| `verify_bbox_opt.py` | opt1（bbox 局部 `stats_mask`/`max_hull_distance`）正确性验证 |
| `verify_residual_layers.py` | opt2（残差层预计算）逐字节验证 |
| `move_dead_code.py` | 死代码归档脚本（生成 `archive/legacy_stages_20261123/` + MANIFEST） |
| `dead_code_plan.json` / `wip_bbox_opt.patch` | 归档计划与 opt1 补丁留档 |

这些脚本多数把 `algorithm/` 加进 `sys.path` 后直接运行；若移动了位置，需要按脚本内的路径假设调整。
