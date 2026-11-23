# J4 运行时间优化记录（opt1~opt4，2026-11-23）

在独立分支 `perf/j4-bbox-stats-mask`（基于 283ce12）完成四轮 J4 运行时间优化。
**最终检测结果（疵病个数、像素面积、精确 mask 字节）与基线逐项一致**，仅运行速度提升。
本记录同步写入正式工程 `PROJECT_IMPLEMENTATION.md`。

## 优化清单与同机实测

| 优化 | 内容 | 26(1) J4 | 181 J4 |
|---|---|---|---|
| 基线（283ce12） | — | 234.98s | 46.57s |
| opt1 | `stats_mask`/`max_hull_distance` 增加可选 bbox 局部扫描（坐标偏移回全帧），逐候选不再扫全窗口 | 149.55s | — |
| opt2 | Gaussian22/Closing61/DoG 残差层改为全帧预计算（磁盘 memmap）+ 逐 tile 裁剪，消除 93px guard 重叠重算；检测后删除残差层（约 1.2GB） | 101.19s | — |
| opt3 | 逐候选循环与 F/DoG 门控里的全窗口 `labels==j` 等操作 bbox 局部化 | 97.22s | — |
| **opt4** | **1~2px 微小候选（`area<min_h_pixels_for_refinement`）走快路径，跳过 ObjectRegion 构造** | **57.85s** | **15.37s** |

- 26(1) 累计提速 **4.06×（快 75%）**；181 号样品 **3.03×（快 67%）**。
- 变更文件：`src/detection/case03e2_multicandidate.py`、`src/detection/local_boundary_refinement.py`、`src/detection/candidate_local_noise.py`、`scripts/h3_b151/scripts_v3/stage_refine.py`、`stage_process.py`、`stage_j4.py`、`detector.py`、`prepare_raw.py`、`staging_entry.py`。

## 正确性验证（每轮优化后必做）

克隆根目录 `compare_final_output.py <基线目录> <优化目录>` 逐疵病比对：
缺陷个数、`source_area_px2`（总像素面积）、逐疵病面积/Feret/bbox/band、精确 mask 字节。

- 26(1)：63 缺陷 / 总像素面积 28665 px² / 63 个精确 mask 字节一致。
- 181：66 缺陷 / 总像素面积 321007 px² / 66 个精确 mask 字节一致。
- 回归测试 43 passed + 18 subtests（12 个失败为纯源码仓库缺失历史结果数据，与优化无关）。

## ⚠️ opt4 的重要边界 —— 后续"更微小疵病识别"必须先考虑

opt4 对 **1~2px（`area<3`）候选跳过 ObjectRegion 构造并返回 None**，其 H 像素经 `process_one`
的 None 路径仍完整保留在源掩膜中，**最终检测结果不变**；但：

- `num_review_objects`、`all_proposal_masks`、`local_proposal_audit`、`H_source_proposal_count`
  等**审计计数减少**——1~2px 候选不再有独立对象 ID、精修审计和"需复核"标记。
- 1~2px 候选在 J5 中属于 SMALL（绿），不进 MEDIUM/LARGE 最终输出；但**若后续要单独识别或人工复核
  "≤2px 的更微小疵病"**，必须先撤销或改造 opt4 快路径，恢复对 1~2px 的 ObjectRegion/审计输出，
  否则这些小候选不会进入独立复核队列（其像素仍在源掩膜中，但无独立对象与复核标记）。

**结论：opt4 是"以牺牲 1~2px 独立审计换取运行速度"的可逆工程取舍，仅适用于当前"中大尺寸疵病"输出目标；
一旦目标下探到 ≤2px 微小疵病，必须回退 opt4 或为微小候选恢复独立对象构造。**

## 复现/验证脚本（克隆根目录，未提交）

- `compare_final_output.py <基线目录> <优化目录>`：逐疵病 + 精确 mask 字节比对（每轮优化后的验收项）。
- `verify_bbox_opt.py` / `verify_residual_layers.py` / `profile_j4_subset.py`：分项等价验证与 cProfile 剖析。

## 提交记录

`perf/j4-bbox-stats-mask` 分支：
- `6f3b12c` opt1 bbox stats_mask/max_hull_distance
- `2978db3` opt2 残差全帧预计算 + 检测后删除残差层
- `93c3dab` opt3 bbox labels==j + 清理大内存中间数据
- `b09ce66` opt4 跳过 1~2px 微小候选
