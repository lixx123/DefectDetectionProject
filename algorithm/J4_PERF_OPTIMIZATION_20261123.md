# J4 运行时间优化记录（opt1~opt4，2026-11-23）

> 目的：记录 J4 四轮运行时间优化，按阶段说明「改了什么文件、改了什么代码、涉及哪些参数、有什么影响」，
> 便于后续维护、修改，以及"更微小疵病识别"扩展时回退/复用。

## 0. 概述

- 分支：`perf/j4-bbox-stats-mask`（基于 `283ce12`）。
- 原则：**每一轮优化后，最终检测结果（疵病个数、像素面积、精确 mask 字节）都与基线逐项一致**，只提升速度。
- 最终同机实测：

| 样品 | 基线 J4 | 优化后 J4 | 提速 | 疵病个数 / 总像素面积（与基线一致） |
|---|---|---|---|---|
| 26(1) | 234.98s | **57.85s** | **4.06×（快 75%）** | 63 个 / 28665 px² |
| 181 | 46.57s | **15.37s** | **3.03×（快 67%）** | 66 个 / 321007 px² |

---

## 1. opt1：stats_mask / max_hull_distance 的 bbox 局部扫描

### 改动文件
- `src/detection/local_boundary_refinement.py`
- `src/detection/case03e2_multicandidate.py`
- `scripts/h3_b151/scripts_v3/stage_refine.py`

### 具体代码改动
- `max_hull_distance(mask)` 与 `stats_mask(mask)` 原来对**全窗口 mask**（约 384×384）做 `np.nonzero(mask)`。
  现在两者增加可选参数 `bbox=(x0,y0,x1,y1)`，改为 `np.nonzero(mask[y0:y1, x0:x1])` 并把坐标**偏移回全帧**；
  不传 `bbox` 时保持原全窗口行为（向后兼容）。
- `stage_refine.detect_window_H_seeded` 的逐候选循环里，对每个 H 组件计算安全包围框并传给这两个函数：
  `rb = (max(0,x-r), max(0,y-r), min(W,x+w+r), min(H,y+h+r))`。

### 涉及参数
- `r = max(policy.max_extension_radius_px, policy.bounded_fallback_radius_px)`
  = `max(12, 7)` = **12 px**（H bbox 向外扩的安全半径）。
  - `max_extension_radius_px` ← config `CASE03E2_HSEED_MAX_EXTENSION_RADIUS_PX = 12`（user_config.py L285）。
  - `bounded_fallback_radius_px` ← config `CASE03E2_HSEED_BOUNDED_RADIUS_PX = 7`（user_config.py L295）。

### 正确性依据
- 精修后的 `combined` 必满足 `combined ⊆ dilate(H, r) ⊆ H_bbox ± r`（扩展像素来自
  `full_component & near & ~H`，`near = dilate(Hmask, (2r+1)×(2r+1))`）。故 `rb` 一定包含 `combined` 全部
  True 像素，bbox 局部 `np.nonzero` 与全窗口结果**完全一致**。

### 影响
- 性能：逐候选 `np.nonzero` 从全窗口（~147K 元素）降到 bbox 局部（微小候选仅几个元素）。
- 正确性：等价（坐标偏移回全帧），经 `verify_bbox_opt.py` 逐对象 mask/bbox/质心/面积/Feret/状态/标记比对一致。

---

## 2. opt2：Gaussian22 / Closing61 / DoG 残差层全帧预计算

### 改动文件
- `scripts/h3_b151/prepare_raw.py`
- `scripts/h3_b151/scripts_v3/stage_j4.py`
- `scripts/h3_b151/scripts_v3/detector.py`

### 具体代码改动
- 原 `filter_context` 对**每个非空 tile** 在 93px guard 窗口上重算三种残差：
  - gaussian22 = `medianBlur(3)` + `GaussianBlur(σ22)` + `GaussianBlur(σ0.85)`
  - closing61 = `medianBlur(3)` + `morphologyEx(CLOSE, 61×61 椭圆)` + `GaussianBlur(σ0.85)`
  - DoG = `GaussianBlur(σ8) − GaussianBlur(σ2)`
- 现在 `prepare_raw.compute_residual_layers()` 在 **prep 阶段一次性全帧预计算**这三层，写为 float32 memmap
  （`residual_gaussian22.npy` / `residual_closing61.npy` / `dog.npy`），路径写入 `inputs.json`。
- `stage_j4.run_tile` 的 `context_provider` 改为从 memmap **裁剪判定窗口 `[t:b, l:r]`**（不再重算大核滤波）。
- `detector.one` 加载三个 memmap 传入 `residual_layers`；缺省时回退旧 `filter_context`（向后兼容）。

### 涉及参数
- `RESIDUAL_HALO_PX = 96`（prepare_raw.py 常量）：分带预计算的水平条带 halo。
  必须 ≥ Gaussian22 支撑半径（~66px）+ 中值 1.5 + 平滑 3 ≈ 70px，96px 留余量。
- `step = 2048`（条带高度，仅影响 prep 内存/速度，不影响结果）。
- 旧 guard `CASE03J4_FILTER_CONTEXT_PX = 93`（user_config.py L450）在预计算路径下不再使用（仅回退路径用）。

### 正确性依据
- 预计算条带 halo（96px）覆盖所有大核支撑，判定窗口内残差值等于 guard 窗口重算值。
  经 `verify_residual_layers.py` 验证**逐像素 bit-identical（max diff = 0.0）**。

### 影响
- 性能：消除 598 个非空 tile × 2 种残差的重复重算（guard 重叠），26(1) 约省 46s；prep 增加约 17.3s。
- 磁盘/内存：3 个 float32 全帧层 ≈ **1.19GB**（prep 一次性，检测期间 memmap 读，检测后由 opt3 删除）。
- 正确性：bit-identical。

---

## 3. opt3：逐候选循环 / 门控的全窗口 `labels==j` 等 bbox 局部化 + 清理大内存中间数据

### 改动文件
- `src/detection/candidate_local_noise.py`
- `scripts/h3_b151/scripts_v3/stage_process.py`
- `scripts/h3_b151/scripts_v3/stage_refine.py`
- `scripts/h3_b151/staging_entry.py`

### 具体代码改动
- `local_raw_statistics(..., mask_origin=None)`：新增可选 bbox 局部候选掩膜（origin=(x,y)），不传时保持全窗口行为。
- `stage_process.py`：
  - F 门控：`hmask=labels==j` → `hmask_local=labels[y:y+bh,x:x+bw]==j`，`near[hmask]` → `near[y:y+bh,x:x+bw][hmask_local]`。
  - DoG 中位：`dog[labels==j]` → `dog[y:y+bh,x:x+bw][labels[y:y+bh,x:x+bw]==j]`。
  - 无对象路径：`fused_labels[labels==j]=j` → bbox 局部 `fused_labels[y:y+h,x:x+w][labels[...]==j]=j`。
- `stage_refine.py`：
  - `Hmask=(labels==j)`（全窗口比较）→ `hmask_local + np.zeros + bbox 赋值`。
  - `median(threshold_map[Hmask])`、`combined[Hmask]` 检查 → bbox 局部。
- `staging_entry.py`：检测完成后删除 3 个残差 memmap 层（约 1.2GB，可由 RAW 重算），只保留必要结果
  （最终对象 CSV / 精确 mask / 图 / 指标）。

### 涉及参数
- 无新增参数；bbox 直接取 `connectedComponentsWithStats` 的组件 `(x,y,w,h)`。

### 影响
- 性能：全窗口 `labels==j`（147K 元素比较/索引）改为 bbox 局部，约省 4%。
- 正确性：等价（bbox 局部与全窗口索引结果相同）。
- 磁盘：检测后自动删除残差层，每 run 省 1.2GB。

---

## 4. opt4：跳过 1~2px 微小候选的 ObjectRegion 构造（⚠️ 关键边界）

### 改动文件
- `scripts/h3_b151/scripts_v3/stage_refine.py`

### 具体代码改动
- 主循环开头：`area < policy.min_h_pixels_for_refinement`（即 1~2px）时直接 `output.append(None); continue`，
  跳过 Proposal / 精修 / hull / stats / ObjectRegion 的构造。
- 末尾 `kept_H` 守恒校验：`full_skip = skip_ids ∪ {area<min_h_pixels_for_refinement 的组件}`，
  排除被跳过的 1~2px，保证 `all H pixels must be exactly preserved` 断言仍然成立。

### 涉及参数
- `policy.min_h_pixels_for_refinement` = **3**（← config `CASE03E2_HSEED_MIN_H_PIXELS_FOR_REFINEMENT = 3`，
  user_config.py L286）。`area < 3` 即 1~2px。

### 正确性依据
- 1~2px 候选在慢路径下，两种残差精修必然返回 `H_too_small_to_refine_but_retained`（因为 area<3），
  结果确定是 H-only 微对象；快路径返回 None 后，`process_one` 用无对象路径
  `fused_labels[labels==j]=j` 重新标注其 H 像素，**最终 fused mask 与慢路径完全一致**。

### 影响
- 性能：跳过约 73% 的候选（26(1) 约 3.8 万 / 5.4 万），`_refinement_by_H_seed` 调用数从 104962 → 28558。
- 正确性：**最终检测结果（个数/像素面积/精确 mask）不变**（已字节级验证）。
- **审计计数变化（有意为之）**：`num_review_objects`、`all_proposal_masks`、`local_proposal_audit`、
  `H_source_proposal_count` 减少——1~2px 不再有独立对象 ID / 精修审计 / "需复核"标记。

### ⚠️ opt4 边界：后续"更微小疵病识别"必须先考虑
opt4 是"以牺牲 1~2px 独立审计换取运行速度"的**可逆工程取舍**，仅适用于当前"中大尺寸疵病"输出目标。
**一旦目标下探到 ≤2px 微小疵病，必须先回退/改造 opt4**，恢复对 1~2px 的 ObjectRegion/审计输出，
否则这些小候选不会进入独立复核队列（其像素仍在源掩膜中，但无独立对象与复核标记）。

---

## 5. 参数汇总（维护用）

| 参数 | 定义位置 | 值 | 影响 |
|---|---|---|---|
| `CASE03E2_HSEED_MIN_H_PIXELS_FOR_REFINEMENT` | config/user_config.py L286 → HSeedConfig.min_h_pixels_for_refinement | 3 | opt4 的 1~2px 阈值（`area<3` 跳过） |
| `CASE03E2_HSEED_MAX_EXTENSION_RADIUS_PX` | config/user_config.py L285 → HSeedConfig.max_extension_radius_px | 12 | opt1 的 bbox 安全半径 r |
| `CASE03E2_HSEED_BOUNDED_RADIUS_PX` | config/user_config.py L295 → HSeedConfig.bounded_fallback_radius_px | 7 | 同上（r 取 max(12,7)） |
| `RESIDUAL_HALO_PX` | scripts/h3_b151/prepare_raw.py 常量 | 96 | opt2 残差条带 halo（须 ≥70px） |
| `CASE03J4_FILTER_CONTEXT_PX` | config/user_config.py L450 | 93 | 旧 filter_context guard（opt2 预计算路径不再用） |

---

## 6. 正确性验证方法（后续每次改动后必做）

1. **最终输出逐疵病比对（每轮必做）**：`compare_final_output.py <基线目录> <优化目录>`
   比缺陷个数、`source_area_px2`、逐疵病面积/Feret/bbox/band、精确 mask 字节。
2. **对象级等价**：`verify_bbox_opt.py`（monkeypatch 全窗口 stats_mask/max_hull_distance 对照）。
3. **残差 bit-identical**：`verify_residual_layers.py`（预计算裁剪 vs 旧 filter_context）。
4. **cProfile 剖析**：`profile_j4_subset.py`。

结果：26(1) 63 缺陷 / 28665 px²，181 66 缺陷 / 321007 px²，精确 mask 全部字节一致。
回归测试 43 passed + 18 subtests（12 个失败为纯源码仓库缺失历史结果数据，与优化无关）。

---

## 7. 复现/验证脚本（克隆根目录，未提交进仓库）
- `compare_final_output.py <基线目录> <优化目录>`
- `verify_bbox_opt.py` / `verify_residual_layers.py` / `profile_j4_subset.py`

## 8. 提交记录（分支 perf/j4-bbox-stats-mask）
- `6f3b12c` opt1
- `2978db3` opt2
- `93c3dab` opt3 + 清理
- `b09ce66` opt4
- `a375c1d` 文档（初版）
