# DefectDetectionProject 疵病识别算法开发程序报告
## ——以 26 (1).raw 为例，按最新 roi-bh 程序真实执行顺序

> 报告基线：当前工程源码 + `outputs/K8A_TWO_LEVEL_FINALGUARD_26_1_ROI_BH_20261020_v2`
>
> 报告原则：严格按程序调用顺序说明“目的→程序→输入→算法→参数→输出→异常分支→下一步关系”。历史Case阶段仅用于解释设计来源，不作为主流程顺序。

---

## 1. 工程目标与本报告边界

DefectDetectionProject 当前正式检测目标是：对同规格12 bit RAW图像中的**有效工作区域**自动完成暗异常候选增强、候选形成、噪声证据筛选、跨块对象关联、RAW轮廓恢复、对象去重、尺寸计算和最终矩形标注。

本报告以 `26 (1).raw` 为唯一贯穿示例。生产业务边界已确定为：

- WORK / BAND_EDGE：进入生产检测；
- NON_WORK：不进入最终疵病报告；
- 非工作区历史候选不静默删除，仍保留来源审计；
- W005属于NON_WORK历史回归样例，不属于生产结果要求。

当前推荐入口模式为：

```powershell
python main.py --case unified-final --input "<RAW>" --roi-mode roi-bh --run-id <唯一ID>
```

本报告不以历史 `--fresh` 全幅1620 tile入口作为主流程。

---

## 2. 总体真实调用链

当前 `roi-bh` 的实际代码链为：

```text
main.py
  ↓
scripts/run_two_level_unified.py::run_raw
  ↓
RAW文件/QC/SHA256
  ↓
case03k8a_band_locator.py::locate_transmission_bands
  ↓
two_level_roi.py::build_plan
  ↓
case03k8a_band_locator.py::rasterize_region_masks
  ↓
two_level_roi.py::compute_fused
  ↓
run_case03j4_fullscan.py::run
  ↓
run_case03j4_fullscan.py::run_tile
  ↓
run_case03t_threeway_comparison.py::process_one
  ↓
H170/230 + H种子Gaussian22/Closing61 + F/G/H
  ↓
J1/J2 tile内对象化
  ↓
run_case03j5_global_merge.py::run
  ↓
跨tile J5合并
  ↓
run_unified_raw_input.py::fresh_j5
  ↓
run_unified_raw_input.py::fresh_b
  ↓
K8B → K8C → K8D
  ↓
已审查26帧才加载人工批准/否定信息
  ↓
unified_raw_recovery.py::recover_objects
  ↓
run_case03_unified_final_detector_26_1_2.py::consolidate
  ↓
run_unified_raw_input.py::export
  ↓
exact mask / 面积 / Feret / 最终矩形图
  ↓
verify_two_level_unified.py::verify
```

---

# 3. Step 0：主程序入口

## 3.1 程序位置

`main.py`

当：

```text
--case unified-final
--roi-mode roi-bh
--input <RAW>
```

同时存在时，主程序进入：

```python
scripts.run_two_level_unified.run_raw(...)
```

因此本报告真正的最新生产调度入口不是旧 `run_unified_raw_input.run_raw`，而是 `run_two_level_unified.run_raw`。

## 3.2 设计目的

入口层只负责：

1. 解析运行模式；
2. 限制错误参数组合；
3. 将显式RAW交给两级检测流程。

算法本身不堆在 `main.py` 中。

---

# 4. Step 1：RAW输入合法性与QC

## 4.1 输入

26_1实际输入：

```text
26 (1).raw
11276 × 9200
16 bit unsigned big-endian container
effective bits = 12
dtype = >u2
```

文件SHA256：

```text
30bbd09680e9bac1b918c10419528a7d42386829e7f6a8a9b690316f9ee1d339
```

## 4.2 程序检查

`run_two_level_unified.run_raw`首先检查：

- 文件必须存在；
- 文件字节数必须等于 `11276×9200×2`；
- 使用只读 `np.memmap(... dtype='>u2')`；
- 每512行检查一次最大DN；
- 任意像素超过 `2^12-1=4095` 立即失败。

随后保存：

- `input.json`
- `source_SHA256_at_start.json`

目的不是检测疵病，而是保证后续所有DN处理基于正确RAW，并保留源码追溯。

26_1本次：

```text
QC_seconds = 0.7052 s
RAW_unchanged = true
```

---

# 5. Step 2：K8A自动定位有效工作带

## 5.1 程序

`src/detection/case03k8a_band_locator.py`

核心函数：

```python
locate_transmission_bands()
```

K8A在最新两级流程中已经前移到Black-Hat之前。

## 5.2 为什么先定位工作区

整幅RAW包含：

- 有效透射工作带；
- 遮光/屏蔽区域；
- 顶部、底部非工作亮平台；
- 其它无需进入最终质检的区域。

如果先对整幅RAW执行全部高成本检测，会浪费大量计算。

K8A只回答：

> 哪些区域值得继续运行高成本疵病检测？

它不直接判断某个暗点是否是疵病。

## 5.3 行方向鲁棒亮度剖面

首先只采样中央76%横向范围：

```text
central_fraction = 0.76
y_stride = 4
x_stride = 12
```

对采样后的每一行计算中位数，然后一维Gaussian平滑：

```text
smooth_sigma_rows = 17 sampled rows
约对应 68 RAW pixels
```

中位数而不是均值的目的，是减弱局部暗斑、划痕对工作带整体亮度剖面的影响。

## 5.4 工作带候选条件

程序使用峰/谷结构寻找工作带，关键条件包括：

```text
min_peak_prominence_dn = 75
min_peak_spacing_px = 220
min_band_width_px = 170
max_band_width_px = 1300
min_dark_shield_trough_gap_px = 80
min_band_contrast_dn = 90
boundary_height_fraction = 0.27
```

一个工作带必须：

1. 存在明显亮平台峰；
2. 两侧均有暗屏蔽谷；
3. 宽度合理；
4. 对比度足够；
5. 不能只是图像顶部/底部外部亮平台。

## 5.5 二维边界拟合

仅用一维行剖面不能处理工作带轻微倾斜。

因此K8A又在横向取30个独立位置：

```text
x_column_sample_count = 30
local_column_halfwidth_px = 155
local_x_stride = 8
```

分别寻找每个工作带的上、下边缘，然后鲁棒线性拟合：

```text
y_top(x) = m_top x + b_top
y_bottom(x) = m_bottom x + b_bottom
```

可信性门限：

```text
median residual <= 30 px
P90 residual <= 85 px
```

如果边缘样本不足、残差过大或几何异常，后续两级ROI不得继续相信这个定位。

## 5.6 26_1实际结果

26_1自动识别：

```text
4个有效工作带
band_count_fixed = false
validation_flags = []
```

四个工作带的一维近似范围：

```text
Band 1: y≈2614 ~ 3231
Band 2: y≈4431 ~ 4955
Band 3: y≈5297 ~ 5913
Band 4: y≈6253 ~ 6959
```

边缘拟合残差均远低于门限。

例如Band2：

```text
top median residual = 1.20 px
top P90 residual    = 2.85 px
bottom median       = 0.63 px
bottom P90          = 1.09 px
```

因此本帧K8A几何可被两级调度接受。

**图5-1  26_1原始RAW与K8A识别出的四条有效工作带**

![26_1原始RAW与K8A四条工作带](REPORT_ASSETS_26_1/01_RAW_K8A_WORKBANDS.png)

**图5-2  K8A行方向鲁棒DN剖面及工作带峰谷定位**

![K8A行方向DN剖面](REPORT_ASSETS_26_1/02_K8A_ROW_PROFILE.png)

---

# 6. Step 3：生成区域语义mask

K8A定位后调用：

```python
rasterize_region_masks()
```

生成两张全分辨率图：

```text
region_type_fullres.png
band_id_fullres.png
```

区域代码：

```text
0 = NON_WORK
1 = SHIELD
2 = WORK_CORE
3 = BAND_EDGE_REVIEW
```

band ID只写入WORK_CORE，不把未知区域静默当成工作区。

这一步非常重要，因为后续K8B、RAW恢复和最终安全约束都需要知道某个像素属于哪条有效工作带。

---

# 7. Step 4：建立Two-level ROI检测计划

## 7.1 程序

`src/detection/two_level_roi.py::build_plan`

注意：

**ROI不是把工作带直接裁出来做算法。**

程序先计算整个后续算法链最大空间依赖，再向工作带外扩。

## 7.2 空间依赖计算

当前记录的主要支持半径：

```text
Black-Hat closing两次形态学依赖 = 30 px
Gaussian22 + median + smoothing = 93 px
Closing61 + smoothing = 65 px
F RAW ring = 12 px
G protection = 8 px
H DoG = 32 px
J1/J2 = 53 px
J4 existing halo = 64 px
K8D RAW context = 64 px
Final RAW background context = 72 px
configured minimum = 93 px
```

最大值：

```text
algorithm_halo_px = 93
```

再加：

```text
review_margin_px = 12
```

所以工作带几何外扩至少：

```text
93 + 12 = 105 px
```

## 7.3 26_1的检测矩形

最终几何范围：

```text
Band1 expanded: y = 2449 ~ 3399
Band2 expanded: y = 4258 ~ 5131
Band3 expanded: y = 5122 ~ 6093
Band4 expanded: y = 6072 ~ 7142
x = 全宽 0 ~ 11276
```

## 7.4 与J4原始网格对齐

程序不会新建一种ROI tile。

仍然使用原J4：

```text
core = 256 × 256 px
```

只选择与上述扩展范围相交的原始tile。

26_1：

```text
全图J4 tiles = 1620
实际调度       = 765
跳过           = 855
```

因此ROI优化只改变“哪些tile执行”，没有改变J4算法本身。

**图7-1  Two-level ROI安全外扩及J4 tile调度范围**

![Two-level ROI与J4 tile调度](REPORT_ASSETS_26_1/03_TWO_LEVEL_ROI_J4_SCHEDULE.png)

## 7.5 失败回退

以下情况之一发生时，ROI计划不能继续：

- 找不到工作带；
- 工作带数量异常；
- 边界拟合不可信；
- 边界反转/越界；
- 工作面积异常；
- 工作带重叠；
- K8A抛异常。

此时：

```text
roi_mode = FULL_FRAME_FALLBACK
```

并且未知几何不会被伪造为“非工作区无疵病”。

---

# 8. Step 5：ROI多尺度Black-Hat

## 8.1 算法

暗目标增强：

```text
BlackHat_k = Closing_k(I) - I
```

结构元均为椭圆，尺度：

```text
3 / 5 / 9 / 15 / 31 px
```

五个尺度逐像素取最大：

```text
BH_fused(x,y)=max(BH3,BH5,BH9,BH15,BH31)
```

所有计算直接使用原始uint16 DN，不使用8 bit显示图。

## 8.2 ROI-BH的块计算

```text
chunk = 512 px
max kernel = 31 px
two-operation dependency = 30 px
extra guard = 2 px
RAW halo = 32 px
```

每个需要计算的512块读取真实RAW的额外32 px上下文，避免ROI边界零填充改变形态学结果。

## 8.3 65535哨兵

输出 `fused_blackhat.npy` 仍保持整幅RAW尺寸。

没有计算的位置写：

```text
65535
```

因为正常12 bit响应不可能达到65535。

因此：

```text
0~4095 = 已计算的真实响应
65535  = UNCOMPUTED
```

J4和K8B消费响应前都调用 `require_computed_response()`。

只要实际需要的区域含65535，程序立即失败，不允许将未计算区误认为极强疵病。

## 8.4 26_1实际计算量

```text
blackhat_chunks = 253
BH input pixel visits = 80,239,104
BH output pixels = 63,506,432
kernel evaluations = 401,195,520
BH time = 3.81 s
```

---

# 9. Step 6：J4局部检测

## 9.1 J4几何

每个执行tile：

```text
core = 256 × 256
halo = 64 px
```

真正进入算法的是：

```text
core + halo
```

只有core区域结果最终归属该tile。

因此靠近tile边缘的疵病仍能看到相邻区域真实上下文。

## 9.2 J4入口安全检查

`run_tile()`先读取：

- local RAW；
- local fused Black-Hat。

然后检查整个工作窗口不存在65535哨兵。

通过后调用：

```python
process_one(local, response, 170, 230, ...)
```

---

# 10. Step 7：H170/230双阈值候选

J4内部第一层正式候选来自固定：

```text
low = 170 DN
high = 230 DN
```

逻辑不是简单 `BH>=170`。

程序先得到低阈值连通域，然后要求：

> 一个低阈值连通域中至少存在一个BH>=230的强种子像素。

因此：

```text
170 → 决定弱连接范围
230 → 决定这个连通范围是否有足够强种子
```

这就是H170/230 hysteresis。

它既保留弱延展部分，又避免只有弱噪声而无强响应的连通域全部进入。

---

# 11. Step 8：H种子约束Gaussian22 / Closing61轮廓精修

固定H候选形成后，并不允许Gaussian/Closing自己去全图寻找新疵病。

当前规则是：

> H170/230是源候选；Gaussian22和Closing61只能围绕已有H种子补充轮廓。

关键参数：

```text
Gaussian/Morph high floor = 65 DN
low floor = 24 DN
high MAD multiplier = 4.0
low MAD multiplier = 1.8
max H extension radius = 12 px
bounded fallback radius = 7 px
max extension/H area ratio = 12
bounded fallback max ratio = 3
```

这个设计来源于历史实验中Gaussian/Closing独立找候选会引入大片背景和大量点噪声。

因此正式J4保留：

```text
H产生候选
Gaussian/Closing补边
```

而不是：

```text
H + Gaussian + Closing三路独立发现疵病
```

---

# 12. Step 9：F/G/H噪声证据门控

## 12.1 F：极小候选RAW局部对比度

主要针对面积≤5 px的小候选。

局部RAW背景环：

```text
outer radius = 12 px
inner guard = 2 px
minimum background pixels = 20
sigma floor = 3 DN
```

计算：

```text
ΔDN = background median - candidate median
relative contrast = ΔDN / background median
Z = ΔDN / robust sigma
```

弱小孤立候选的参考门限：

```text
relative contrast >= 0.08
Z >= 3.0
```

但在 `process_one()` 函数内部，这一步仍保留原始H、隐藏建议和精修mask，可在内存中逆向核对；但J4下游只消费门控后的 `fused_joint_display`。因此 `hide_suggestion` 会阻止对应候选进入后续J4/J5对象链，不能简单表述为“只影响显示”。

## 12.2 G：结构保护

若小候选：

- 已有H锚定Gaussian22/Closing61精修支持；
- 或距离较大H结构很近；

则优先进入保护/复核，而不是仅凭小面积低对比度隐藏。

关键参数：

```text
support area >= 6 px
protection radius = 8 px
```

## 12.3 H：6~30 px背景纹理复核

对面积：

```text
6 ~ 30 px²
```

且此前仍被保留的对象，再检查RAW纹理证据。

弱背景候选只有在：

```text
relative contrast < 0.06
AND
Z < 2.5
```

同时成立时才建议隐藏。

以下情况保护：

```text
Black-Hat peak >= 320 DN
DoG median >= 16 DN
长线结构 length >=12 px 且 aspect>=3.5
邻近 >=40 px² 大H结构，radius=5 px
```

最终得到 `fused_joint_display`，作为J4实际对象化mask。

### 12.4 当前实现中的“可逆”边界

函数级别上，`build_joint_maps()` 同时返回：

```text
h_original
h_kept_display
h_hidden_suggestion
fused_original
fused_joint_display
```

因此在 `process_one()` 内部，F/G/H门控是可逆的：原始H像素没有被算法就地改写。

但当前 `run_case03j4_fullscan.py::run_tile()` 写入正式J4 NPZ时，只保存了门控后的source mask及后续对象标签：

```text
source_detected_uint8
grouped_source_only_i32
inferred_bridge_i32
continuous_display_i32
...
```

没有把 `h_original`、`h_hidden_suggestion`、`fused_original` 和逐H候选的F/G/H状态持久化到J4输出。因此，**hide_suggestion在当前生产链中会阻止该H候选进入J4/J5，其精确H级几何不能仅依靠当前J4产物完整恢复。**

### 当前版本的候选噪声保存策略（项目决策）

经项目讨论，当前版本接受这一取舍：

- 不逐一保存被F/G/H抑制候选的坐标、轮廓、局部图像或完整二值Mask；
- 不额外生成隐藏候选CSV账本；
- 不为此增加软件端独立的噪声审计页面；
- 不改变F/G/H现有判定规则、阈值和最终检测Mask。

原因是当前被抑制候选中有大量极小点状响应。现阶段逐点持久化会增加输出文件、存储和软件维护复杂度，而尚无明确的实际漏检案例证明这项成本是必要的。`hide_suggestion` 是算法当前的抑制决策，不等于人工确认该候选一定是背景噪声。

**已知限制：** 当前正式J4结果不能单独还原某次运行中所有被抑制H候选的精确位置和形状。若后续发现真实疵病疑似被F/G/H误抑制，应保留对应原始RAW，并使用当时的Engine代码版本和参数配置重新运行；针对问题区域开启临时调试输出，导出H候选、F/G/H状态及原因，再决定是否需要调整规则或增加长期审计功能。若原始RAW、代码版本或参数配置缺失，则不能保证完整重建历史候选。

因此，这项内容记录为**当前版本接受的工程取舍和后续改进触发条件**，不是当前版本必须整改的阻塞项。

**图12-1  代表性J4 tile（T011_007）从RAW、Black-Hat、H170/230到精修及F/G/H门控的六阶段对照**

![T011_007六阶段检测链对照图](REPORT_ASSETS_26_1/J4_CORE_T011_007/T011_007_STAGE_6PANEL.png)

---

# 13. Step 10：J4 tile内对象化、J1/J2

J4对 `fused_joint_display` 做连通域对象化，并计算：

- source area；
- max Feret；
- bbox；
- size grade。

像素分级门限：

```text
MEDIUM:
 area >= 40 px² 或 length >= 15 px

LARGE:
 area >= 250 px² 或 length >= 45 px
```

这只是工程像素级分组，不是成品合格等级。

随后J1在tile内部进行碎片关联，主要参数：

```text
max gap = 18 px
direction tolerance = 38°
bridge DoG median >=16 DN
bridge positive fraction >=0.7
```

J2可以生成连续显示桥接，但：

> 推断bridge像素不计入真实测量面积/Feret。

J4保存多层mask：

```text
source_detected_uint8
source_region_label_i32
grouped_source_only_i32
inferred_bridge_i32
continuous_display_i32
```

## 13.1 26_1 J4结果

```text
planned tiles = 765
completed tiles = 765
J4 local objects = 698
coverage = SCHEDULED_ROI
```

J4明确声明这些不是最终全局疵病ID。

**图13-1  T010_018中J1分组、J2推断bridge与连续显示的区别**

![J1与J2 tile内关联示例](REPORT_ASSETS_26_1/J1_J2_J5/05_J1_J2_T010_018.png)

---

# 14. Step 11：J5跨tile全局对象化

J5只负责把J4在不同core中的对象重新关联。

## 14.1 直接像素连续

如果两个对象跨tile边界满足8邻域直接连续：

```text
gap <= sqrt(2)
```

直接接受。

因为这是原始source像素的真实连续性。

## 14.2 有间隙碎片

如果存在间隙，则要求：

```text
gap <= 18 px
min piece area = 5 px
long segment anchor >=12 px
aspect >=1.5
direction tolerance =30°
bridge DoG median >=16 DN
positive bridge fraction >=0.70
```

如果同一个对象面对多个距离相近的候选：

```text
ambiguity margin = 2 px
```

则拒绝含糊自动关联。

## 14.3 J5只关联身份，不虚增测量面积

J5使用Union-Find合并对象身份。

原source像素面积必须严格守恒：

```text
J4 source area before = J5 source area after
```

## 14.4 26_1实际结果

```text
J4 unmerged objects = 698
J5 global candidates = 687
source area before = 20,963 px²
source area after  = 20,963 px²
candidate seam pairs = 22
accepted links = 11
其中direct links = 11
separated inferred links = 0
跨tile对象 = 8
```

这说明26_1这一轮J5合并全部来自真实跨边界像素连续，没有依赖推断间隙桥接。

**图14-1  DEFECT_00649跨tile真实8邻域连续示例**

![J5跨tile直接连续示例](REPORT_ASSETS_26_1/J1_J2_J5/06_J5_DEFECT_00649_DIRECT_SEAM.png)

---

# 15. Step 12：已知26帧的J5身份回归

因为26_1是开发阶段已经审查过的RAW，程序通过完整RAW SHA256识别为known frame。

最新两级J5对象ID不能靠新的顺序编号与历史对象对应。

程序使用：

> 完全相同的J4 local member set

作为对象身份依据。

26_1：

```text
WORK/EDGE required historical J5 objects = 687
exact member set matched = 687
missing = 0
```

因此两级ROI没有改变工作区J5对象构成。

对于一张真正新的RAW，没有这个历史身份映射步骤。

---

# 16. Step 13：从J5选择生产主候选

`fresh_j5()`建立当前J5来源账本。

最终主候选并不是把687个J5对象全部输出。

`build_j5()`优先保留：

1. WORK中的MEDIUM/LARGE；
2. SMALL中具有明显方向性的细线目标。

小划痕保护条件包括：

```text
Feret >= 10 px
且 bbox aspect >= 1.6
```

因此J5在这里承担“已有主通道候选”的角色。

---

# 17. Step 14：K8B分工作带补充候选

K8B是J5之外的工作带补充通道。

它利用K8A的WORK_CORE，对每条工作带分别统计Black-Hat背景。

统计采用：

```text
sample stride = 8
median
MAD sigma = 1.4826×MAD
sigma floor = 2 DN
```

## 17.1 两套阈值

A支路：

```text
固定 H170/230
```

B支路：

选择该帧RAW中位数最高的工作带作为参考带，把参考带170/230对应的鲁棒Z分数转移到其它工作带。

26_1参考Band1：

```text
Band1 = 170 / 230
Band2 = 64.7143 / 87
Band3 = 128.4286 / 173
Band4 = 134.4286 / 179
```

这使低亮度工作带仍有机会形成补充候选，而不是强行使用相同绝对BH阈值。

### 代码一致性备注

当前K8B元数据字符串仍写：

```text
ANCHOR_ROBUST_Z_TRANSFER_NOT_APPROVED_FOR_PRODUCTION
```

但最新 `run_two_level_unified → fresh_b` 已实际消费该B支路作为补充候选源。

因此这是**当前代码行为与历史命名之间的文档不一致**，正式报告以代码真实行为为准；后续应统一命名。

---

# 18. Step 15：K8C对K8B候选做RAW证据分流

K8C不删除B源mask，而是分类。

主要类别：

```text
EXISTING_FIXED_H
MICRO_HIDE_SUGGESTION
BOUNDARY_REVIEW
MICRO_REVIEW
PROMISING_DARK_REVIEW
UNCERTAIN_REVIEW
```

## 18.1 局部RAW背景

候选周围使用：

```text
inner radius = 6 px
outer radius = 24 px
min valid background = 70 px
```

并排除：

- 当前目标；
- 所有B暗候选；
- 非WORK区域。

计算：

- RAW候选中位数；
- 背景中位数；
- ΔDN；
- 相对暗度；
- robust MAD Z；
- DoG暗核；
- 距离工作带边界距离。

## 18.2 强暗证据

PROMISING条件核心为：

```text
area >= 8 px
relative darkness >= 0.07
MAD Z >= 2.0
DoG P90 >= 3 DN
```

1~2 px不会物理删除，只记：

```text
MICRO_HIDE_SUGGESTION
```

距离WORK边界32 px以内进入边界复核。

## 18.3 当前最终候选门槛

在 `fresh_b()` 中，真正允许进一步提出final mask的K8B来源还要求：

```text
source area >= 40 px²
classification ∈ {PROMISING_DARK_REVIEW, UNCERTAIN_REVIEW}
```

因此微小候选仍保留审计，但不会因为K8B旁路直接升级为最终对象。

---

# 19. Step 16：K8D 128×128 RAW轮廓稳定性

对满足条件的B来源，以其中心构造128×128 ROI。

分别运行RAW外围：

```text
3.0 sigma
2.0 sigma
1.5 sigma
```

然后K8D比较轮廓稳定性。

关键限制：

```text
3σ seed overlap >= 0.60
max outer area = 2000 px²
3→2 area ratio <=1.35
2→1.5 area ratio <=1.25
nesting loss <=0.07
compact aspect <=2.8
group coverage >=0.80
```

稳定结果可能为：

```text
STABLE_SINGLE_OUTER_REVIEW
STABLE_GROUP_OUTER_REVIEW
```

风险结果包括：

```text
CENSORED_FULL_OUTER_REVIEW
SOURCE_ONLY_UNRELIABLE_3MAD
...
```

只有 `STABLE_*` 且面积增长不超过源面积8倍时，fresh_b才用RAW外围替换源B轮廓。

否则仍保留源B本身，不因精修失败而静默丢候选。

26_1实际执行：

```text
RAW trial objects = 12
STABLE_SINGLE = 6
STABLE_GROUP  = 1
CENSORED      = 4
UNRELIABLE_3MAD = 1
```

---

# 20. Step 17：26_1人工批准/否定记录的SHA绑定

这一步只对已审查的26_1/26_2生效。

程序不是根据文件名判断，而是比较完整RAW SHA256。

若SHA256与26_1一致：

- 加载2个已人工确认暗斑mask；
- 加载历史人工否定组；
- 已批准mask不可变；
- K8B不能重复覆盖同一批准源；
- 人工否定区域不得被RAW恢复重新引入。

26_1两处确认暗斑面积：

```text
297 px²
398 px²
```

对于新的RAW：

> 不加载26号人工坐标和批准mask。

---

# 21. Step 18：Unified RAW bounded recovery

这是最终后端的重要轮廓恢复步骤：

`src/detection/unified_raw_recovery.py::recover_objects`

它只处理：

```text
非人工批准的 B_* 对象
```

不生成新的独立种子。

## 21.1 同带邻近B对象先形成恢复组

同一band，bbox距离：

```text
<=36 px
```

可以进入共同RAW恢复试验。

## 21.2 建背景

源mask外：

```text
inner = 44 px
outer = 68 px
```

且必须仍在同一WORK band。

背景像素少于500则拒绝。

单源目标：

- 鲁棒平面背景。

多源细长目标：

- Gaussian sigma=16的局部尺度背景。

## 21.3 RAW残差

```text
residual = background - GaussianBlur(RAW, sigma=1.3)
```

robust sigma：

```text
sigma >= 3 DN
```

支持阈值：

```text
threshold =
max(
  residual median + 3*sigma,
  0.15 * source residual P99
)
```

## 21.4 必须满足一个共享RAW连通域

恢复目标必须存在一个真实RAW支持连通域，同时覆盖组内每个源：

```text
每个seed coverage >= 90%
```

否则这些B源仍保持分离。

## 21.5 安全硬约束

候选恢复必须同时满足：

```text
不跨WORK_CORE
不达到source distance cap 40 px
不触ROI边缘
short axis <=48 px
area <=10000 px²
area growth <=8× source area
不与其它对象重叠
不与人工负例重叠
```

任意失败立即拒绝恢复，不为了得到更大的轮廓关闭安全门。

## 21.6 F1_FINAL_0029实例

四个Band02 B源：

```text
C614
C1028
C1273
C1562
```

通过共享RAW支持恢复为：

```text
F1_FINAL_0029
area = 3469 px²
max Feret = 189.97368 px
bbox = [5244,4508,5326,4687)
reason = SHARED_CONNECTED_RAW_3SIGMA_SOURCE_DISTANCE_BOUNDED
```

这一步是“基于真实RAW证据的有界恢复”，不是形态学画线连接。

---

# 22. Step 19：Unified Final 像素级去重

最终使用：

`consolidate()`

只在同一band内比较对象。

两个对象必须有真实mask交集。

自动认为同一对象的条件：

```text
intersection >= 3 px
AND
intersection / smaller_area >= 0.25
```

符合条件：

- exact union；
- source UID合并；
- 不重复计面积。

弱部分重叠但不足以判为同一对象时，不强制合并。

对象优先级：

1. user approved；
2. 更高来源priority；
3. 更大mask。

若存在像素竞争，后处理按优先级确保最终mask互不重叠。

源对象即使最终被更高优先级对象完全覆盖，其来源关系仍保留在独立审计表中。

---

# 23. Step 20：精确mask与尺寸计算

最终 `export()` 对每个对象保存：

```text
EXACT_FINAL_BINARY_MASKS/F1_FINAL_xxxx.npz
```

每个NPZ包含：

- exact binary mask；
- global RAW bbox；
- source UID列表。

## 23.1 面积

```text
A = exact final mask中的前景像素数
```

不是bbox面积。

## 23.2 长度

```text
L = exact mask像素中心凸包最大Feret距离
```

不是：

- bbox对角线；
- 弯曲划痕中心线长度；
- 显示框长度。

## 23.3 物理单位

虽然探测器像元为3.2 μm，但当前缺少样品物面的独立标定关系。

因此正式定量仍使用：

```text
px
px²
```

不能直接把当前数字写成样品表面μm或μm²。

---

# 24. Step 21：最终矩形显示

最终用户图：

```text
00_FINAL_DEFECTS_ONLY_fullframe_1to4.png
```

显示原则：

- 不绘制mask彩色填充；
- 不绘制缺陷轮廓；
- 只画矩形框；
- 显示ID；
- 显示A和L。

显示框：

```text
scale = 1.5 × exact mask bbox
```

这个扩大只用于定位。

它绝不参与面积与长度计算。

显示图按4倍stride缩图：

```text
display_stride = 4
font = 18 px
```

并进行label避碰检查。

---

# 25. Step 22：26_1最终结果

最终代码重新运行26_1得到：

```text
final objects = 36
total exact final area = 20,356 px²
LARGE = 19
MEDIUM = 16
SMALL = 1
```

两处人工确认暗斑：

```text
297 px²
398 px²
```

总来源：

```text
fresh source records = 17,453
其中：
J5 = 687
K8B = 16,766
```

真正进入最终对象的source UID只有其中一部分；未进入final的source并不从审计中消失。

历史完整来源账本：

```text
32,370 rows
fresh reproduced = 17,453
historical preserved, not rescanned = 14,917
```

这正是“只检测有效工作区域，同时不静默丢历史候选”的工程实现。

---

# 26. Step 23：独立QA

最终不是只看“36个对象”是否相同。

`verify_two_level_unified.py`做像素级独立回归。

主要检查：

1. 所有执行J4窗口的Black-Hat与全幅参考逐像素比较；
2. J4 NPZ中的所有array逐项比较；
3. K8A band ID逐像素比较；
4. WORK/EDGE J5对象按exact member set比较；
5. J5面积、Feret、bbox必须不变；
6. K8B B_SOURCE_ALL逐像素比较；
7. 每个final mask与source UID集合完全一致；
8. 最终full-resolution binary mask完全一致；
9. 人工批准mask逐像素不变；
10. 人工负例冲突必须为0；
11. 历史source ledger行集不能丢；
12. 主渲染图不能画mask轮廓；
13. label和box不得碰撞。

26_1结果：

```text
Independent QA = PASS
BH work-window diff = 0
J4 grouped source diff = 0
verified tiles = 765
WORK/EDGE J5 exact objects = 687
final binary diff = 0
final objects = 36
approved masks exact = true
negative conflict = 0
historical source rows = 32370
```

因此当前证据支持：

> K8A前移 + ROI Black-Hat降低了非工作区计算量，但没有改变26_1有效工作区域内的既有检测结果。

---

# 27. Step 24：运行性能

26_1最新final-guard运行：

```text
QC                  0.705 s
K8A + plan          1.007 s
ROI Black-Hat       3.811 s
J4                 74.057 s
J5                  2.468 s
K8/final/export    11.168 s

total              93.863 s
```

J4仍是当前主要计算耗时。

相较原全幅1620 tile：

```text
1620 → 765
减少52.78%
```

因此K8A前移的主要收益来自减少J4高成本tile执行，而不是单纯减少Black-Hat时间。

---

# 28. 安全设计总结

当前主链有五类关键fail-closed机制。

## 28.1 RAW格式门禁

尺寸/字节数/有效bit不符合即失败。

## 28.2 K8A几何门禁

工作带定位不可信，不允许把未知区域当作NON_WORK直接跳过，而是全幅fallback。

## 28.3 65535哨兵门禁

J4/K8B不能消费任何未计算Black-Hat像素。

## 28.4 RAW恢复门禁

恢复必须满足工作带、距离、面积、宽度、coverage、负例冲突等条件。

## 28.5 来源审计门禁

任何源候选不能因最终未入选而从历史账本静默消失。

---

# 29. 当前代码中需要标明的文档一致性问题

## 29.1 K8B方法命名

当前K8B阈值结果元数据仍写：

```text
NOT_APPROVED_FOR_PRODUCTION
```

但最新roi-bh代码已经实际调用并消费该分带支路。

因此该字符串已不能准确描述当前软件状态，建议后续改为中性名称，例如：

```text
ANCHOR_ROBUST_Z_TRANSFER
```

并在文档中说明它是K8B补充候选源，而不是替代J4主通道。

## 29.2 旧用户指南

`UNIFIED_DETECTOR_USER_GUIDE.md`仍主要描述旧 `--fresh` 全幅1620 tile流程。

当前推荐正式链已经是：

```text
--roi-mode roi-bh
```

后续软件文档应同步。

## 29.3 unified_proposal_selection.py

该模块属于历史/冻结proposal消费逻辑。

最新 `run_two_level_unified.py` 主链并未调用它。

当前fresh roi-bh的最终RAW恢复由：

```text
unified_raw_recovery.recover_objects()
```

直接完成。

正式流程图中不应错误地把 `select_proposals()` 插入最新运行顺序。

---

# 30. 当前算法的逻辑本质

如果把整个复杂程序压缩为最核心的工程逻辑，可以归纳为：

```text
第一层：在哪里检测？
K8A识别有效工作带
        ↓
安全外扩 + 原J4网格调度

第二层：哪些像素具有暗异常响应？
多尺度Black-Hat
        ↓
H170/230主候选

第三层：候选轮廓是否可以合理补全？
H种子约束Gaussian22 / Closing61

第四层：它是不是弱背景噪声？
RAW局部对比度 + MAD + DoG + 结构保护

第五层：同一疵病是否被切成多个部分？
J1/J2 tile内关联
        ↓
J5跨tile对象化

第六层：不同工作带照明条件下是否还有补充候选？
K8B分带阈值
        ↓
K8C证据分流
        ↓
K8D RAW稳定外围

第七层：轮廓是否还能根据真实RAW安全恢复？
Unified RAW bounded recovery

第八层：多个来源是否属于同一个最终对象？
真实mask像素重叠去重

第九层：如何测量？
exact final mask
→ area
→ max Feret

第十层：如何交付？
矩形框 + ID + A + L
→ 全来源审计
→ independent QA
```

这条链路的核心原则不是“尽量把所有暗东西都框出来”，而是：

> **主候选优先保证召回，轮廓补充必须有源候选锚定，跨区域关联需要几何/RAW证据，最终尺寸只来自真实mask。J5/K8B及最终来源具备完整审计；F/G/H在函数内部可逆，当前J4只持久化门控后的正式source mask，被抑制H候选的逐点信息暂不保存，这是当前版本接受的工程取舍，后续仅在出现实际漏检案例时按需开启局部调试。**

---

# 31. 当前技术边界

本报告对应的是当前26_1最新工程链，不应扩大解释为：

- 已证明所有真实疵病零漏检；
- 已获得统计意义上的Precision/Recall；
- 已完成所有20帧当前版本的盲测；
- 3.2 μm/px已经是样品物面标定；
- 每个自动对象都已人工确认为真实疵病。

当前可以严谨声明的是：

> 对26_1，最新roi-bh两级流程已经完成真实RAW重算和独立像素级回归，工作区检测结果与经审查的全幅参考保持一致，同时减少了非工作区域的高成本计算。

---

# 32. 报告扩展内容索引

原主链审查完成后，已补充四个独立附录，并完成当前源码双帧重跑：

- **附录A（第33节）：** Case03A—K8I历史算法演化、各阶段设计原因及当前生产链取舍。
- **附录B（第34节）：** ImageJ线性灰度拉伸与弱异常补漏实验方案；属于待执行计划，不代表实验已经完成。
- **附录C（第35节）：** 26_1/26_2两帧历史ROI-BH运行结果、独立QA与精确Mask几何联合审查。
- **附录D（第36节）：** 历史运行acceptance.json状态滞后、源码SHA不一致及版本问题。
- **第37节：** 当前源码对26_1/26_2重新运行、源码SHA闭环、独立QA和验收汇总。

这些附录和追加审查均不改变第2节所列当前 `roi-bh` 的真实调用顺序。


---

# 33. 附录A：Case03A—K8I算法演化与当前主链取舍

本附录解释历史开发阶段的设计来源。**它不是当前程序的运行顺序**；当前真实运行顺序仍以第2节的 `roi-bh` 调用链为准。历史阶段中出现的实验算法、人工ROI、候选排序和临时显示规则，不应误写成当前生产算法全部执行的步骤。

## A.1 Case03A：阈值分割方法筛选

### 目标
比较Black-Hat响应的固定DN阈值与局部Median/MAD阈值，观察不同尺度、不同样品下的候选像素密度。

### 主要实现
- 固定阈值对照：150、200、250、300 DN，主对照掩膜为200 DN。
- 局部阈值：\(T=\max(120,\operatorname{Median}+k\cdot1.4826\operatorname{MAD})\)，\(k=3,5,7\)。
- 局部网格256 px，统计采样步长4 px。
- 只生成全分辨率二值Mask，不做连通域、形态学、面积删除、分类或Top-N截断。

### 结论与取舍
Case03A-R1进一步修正了局部阈值计算，并增加floor主导网格比例、MAD=0网格比例等退化诊断。样品26的3 px尺度下，局部k=5方案约99.57%的网格由绝对阈值下限主导，说明该条件下局部统计并未真正提供有效的空间自适应。

**当前取舍：不把局部MAD作为生产主检测阈值；保留固定阈值作为可解释、可复现的主检测基础。** 这不代表局部自适应在其他数据或其他尺度下必然无效。

## A.2 Case03B：H170/230滞后阈值候选生成

### 目标
从连续Black-Hat响应中提取可追溯的候选像素区域，而不是直接输出疵病真值。

### 主要实现
- S候选：\(R\geq230\) DN，作为强响应种子。
- H候选：\(R\geq170\) DN，作为弱响应支持区域。
- 在H支持区域中，保留包含S种子的8连通分量。
- 另行保存S/H掩膜、H的low-only区域和全量候选表。

Case03B对26—30号样品第一帧执行全图候选提取，正式汇总行25条、候选明细约2,254,801条记录。26号样品H170/230候选为88,043个连通域（后续Case03C报告再次核对）。

### 结论与取舍
H170/230成为后续算法的候选来源。此阶段不执行形态学、面积筛除、Top-N截断或真实疵病判定。**S是种子，H是支持区域；H连通域不是天然等同于一个物理疵病。**

## A.3 Case03C、D：候选关联、特征描述与复核优先级

Case03C对26_1的S230核心与H170/230候选进行关联，提取RAW参考环带、灰度差、MAD、形状PCA等描述性特征，并生成分层人工复核图册。报告记录H候选88,043个、S核心91,937个，RAW参考环带有效候选66,399个。特征缺失或参考环带无效的候选仍保留，不因无法计算特征而自动删除。

Case03D对88,043个H候选建立人工复核顺序：
- A：881个，前1%；
- B：7,924个，随后9%；
- C：79,238个，最后90%。

评分由候选面积和Black-Hat峰值的经验百分位各占50%构成，不读取人工标签。后验统计仅评价已经标注的候选，不代表全图Precision/Recall。单像素候选全部位于C组，因此另建35,678个单像素候选的完整审计队列和Top-100人工抽查视图。

### 结论与取舍
Case03C/D解决的是“如何保存、描述和安排人工复核”，而非“如何自动确定疵病真伪”。A/B/C不是缺陷置信度等级；任何优先级都不能替代真实RAW核查。

## A.4 Case03E、E2：RAW轮廓精修与H种子约束

Case03E在10处人工定位区域开展60组局部试验，比较：
- Closing61背景估计；
- Closing101背景估计；
- Gaussian22背景估计；
- 每种方法的宽松/保守阈值。

这10处仅是局部开发样本，不是独立验证集。实验暴露出背景连通、窗口触边和方法面积不稳定问题：弱响应扩展可能把邻近的大面积暗背景吞入候选，导致面积和长度被严重高估。

Case03E2因此明确：
1. 原H170/230连通域是唯一候选来源；
2. Gaussian22/Closing61只允许对已有H源提出局部扩展；
3. 原H像素必须保留；
4. 竞争H核心、ROI边界、扩展面积和源/扩展比例设置保护条件；
5. 全局低阈值连通域不安全时，才尝试H种子锚定的有界救援；
6. 有界扩展仍标记为待复核，不自动成为精确物理轮廓。

W005试验中，有界共识版本对手绘近似范围的覆盖率达到99.26%，但手绘范围并非像素级真值，且该样本参与了算法开发；该数值不能作为独立轮廓准确率。

### 结论与取舍
当前主链保留H种子约束的Gaussian22/Closing61思想，拒绝“无H种子、仅凭局部暗背景独立生成候选”的做法。扩展区域必须有明确的源候选、局部约束和审计记录。

## A.5 Case03F、G、H：RAW噪声分流与结构保护

这几个阶段围绕“哪些弱候选更像局部背景噪声”展开，而不是训练疵病分类器。

- **F：** 利用局部RAW相对对比度、背景MAD和显著性统计，给已有H候选形成可逆的keep / review / suggest-hide建议。
- **G：** 增加保护规则。已有Gaussian/Closing精修证据、邻近较大H结构或弱候选附近存在结构支撑时，不轻易建议隐藏。
- **H：** 对6—30 px中小候选增加DoG暗核、Black-Hat峰值、细长形态和邻近大结构保护；只有多项RAW证据同时偏弱时，才形成隐藏建议。

26_1局部试验记录显示：F阶段保留1,569个原始H候选来源；G阶段将1,056个候选标为隐藏建议、289个保护复核、224个保留；H阶段进一步调整建议范围。所有这些“隐藏”仅用于显示/复核建议，原始H来源和精修对象不被改写。

### 结论与取舍
噪声抑制应当是证据分流，而不是不可逆删点。对于RAW参考无效、细线形态、邻近结构支撑或强响应候选，优先保留或复核。F/G/H是K8C类RAW证据分流思路的历史基础，但不能把历史局部窗口试验数量当作当前全幅生产统计。

## A.6 Case03I：像素尺寸分级与标注展示试验

Case03I首次把候选轮廓、编号、面积和最大Feret跨度组合到图像中，并试用SMALL/MEDIUM/LARGE显示档位。第一帧仅扫描9个ROI，第二帧扫描18个ROI；报告明确指出这些不是完整RAW全幅检测，且尚未完成跨ROI去重。

当时使用的40 px²、250 px²、15 px、45 px门限只是图像像素级演示参数。它们不是产品质量验收标准，也不应直接换算成滤光片物面微米尺寸。

### 结论与取舍
保留面积、最大Feret、编号和分级显示的工程需求；正式全幅链改为先完成对象合并和精确Mask，再计算尺寸。当前最终定量单位为px和px²，3.2 μm探测器像元间距不能替代样品物面标定。

## A.7 Case03J：从局部ROI走向全幅Tile检测与全局对象化

Case03I暴露出ROI局部统计的三个问题：窗口重复、窗口边界截断、同一划痕被拆成多个候选。Case03J因此把处理范围扩展到全幅Tile，并分成两个层次：

- **J4：** 按全幅Tile调度候选检测，Tile边界设置重叠/上下文，执行固定阈值候选和局部精修。
- **J1/J2：** 在Tile内部进行候选关联、连续结构及碎片关系处理。
- **J5：** 将Tile结果映射回RAW全局坐标，进行跨Tile对象化、来源关联和去重，避免同一物理对象因Tile切割重复计数。

J5不是简单按bbox距离合并：必须结合候选像素/Mask的真实关系及方向连续性，避免将相邻背景或不同疵病误连。当前ROI-BH分支中，26_1执行J4的Tile数为765，J5输出WORK/EDGE对象687个；这组数字属于当前两级ROI运行，不应与旧全幅1620 Tile实验混为一谈。

### 结论与取舍
全幅检测的对象单位由“局部连通域”转向“全局对象”。最终尺寸必须在J5对象化后计算；Tile局部bbox或局部连通域数量不能直接当作整片滤光片疵病数量。

## A.8 Case03K：工作带约束、分带补充和RAW轮廓证据

K阶段进一步解决三个问题：只检测有效工作区、不同工作带响应差异、补充候选如何安全进入最终结果。

| 子阶段 | 主要目的 | 当前定位 |
|---|---|---|
| K8A | 自动定位工作带、WORK/BAND_EDGE/NON_WORK区域，建立ROI和区域Mask | 当前两级ROI主链组成部分 |
| K8B | 以参考工作带的鲁棒统计为锚，向其他工作带转移阈值尺度，生成补充候选 | 当前补充候选来源；不替代J4/J5 |
| K8C | 使用RAW局部背景、相对暗度、MAD显著性、DoG等证据对补充候选分流 | 当前候选证据审查环节；不能单独认定真实疵病 |
| K8D | 在128×128 RAW局部区域比较不同噪声倍数下的外围轮廓稳定性，并保留触边/不稳定状态 | 当前RAW补充轮廓证据环节 |
| K8E | 对候选成员建立精确Mask并集的对象假设，审查多源是否可能属于同一异常 | 历史/辅助对象假设审查，不等同自动确认 |
| K8F | 记录用户批准的补充组及其来源关系 | SHA/样本受限的人工确认依据 |
| K8I | 建立全幅来源谱系，记录源候选、分组、最终对象和未入选来源 | 审计/追溯机制，不是新的独立检测器 |

### K8阶段的边界
1. K8B新增候选数量增加，只能说明候选召回范围扩大，不能直接证明真实疵病检出率提高。
2. K8C的噪声证据分类不是经过独立真值训练/验证的物理疵病分类器。
3. K8D的稳定轮廓是RAW外围稳定性证据，不是独立物理轮廓真值。
4. K8E的exact union只说明成员Mask可以精确求并，不自动证明成员属于同一个物理疵病。
5. K8F人工批准信息只能在输入RAW身份匹配、来源范围明确的条件下应用；不能把26号样品人工坐标迁移到其他RAW。
6. K8I的核心价值是来源不丢失、去向可追溯。未进入最终对象的源候选仍应保留审计记录。

## A.9 历史算法到当前生产链的最终取舍

当前 `roi-bh` 主链实际保留的是：

- 固定H170/230主候选；
- H种子约束的Gaussian22/Closing61局部精修；
- F/G/H阶段形成的结构保护和RAW噪声分流思想；
- J1/J2 Tile内关联与J5跨Tile全局对象化；
- K8A工作带定位；
- K8B/C/D补充候选及RAW轮廓证据；
- SHA绑定的已审查人工批准/否定信息；
- Unified RAW bounded recovery；
- exact Mask去重、面积/Feret计算、全来源审计和独立QA。

不应误写为当前主链必然执行的历史支路包括：Case03A局部MAD作为主阈值、Case03D复核优先级排序、Case03I旧ROI分级显示、K8E自动合并、历史proposal selection模块。它们分别属于对照试验、人工管理、旧显示试验或辅助审查，不得未经源码确认插入当前真实调用链。

**历史演化的核心结论：** 算法不是通过不断降低阈值来追求候选数量，而是逐步建立“固定阈值候选锚定—RAW约束扩展—空间对象关联—工作区限制—来源审计”的工程约束。其首要目标是防止背景被并入、候选被静默删除以及尺寸被不可靠Mask污染。


---

# 34. 附录B：ImageJ灰度拉伸与弱异常补漏实验方案（待执行）

## B.1 实验目的

已有RAW图像在ImageJ中进行Brightness/Contrast灰度拉伸后，可以观察到原始显示下不明显的局部暗细节。本实验用于确认这些细节是否对应当前自动检测主链未覆盖的真实暗异常，并区分：

1. 固定阈值偏高导致的弱响应候选遗漏；
2. Black-Hat尺度与异常宽度不匹配；
3. 局部背景梯度、条带或工作带边缘；
4. CMOS纹理、随机噪声或显示拉伸产生的视觉假象。

本实验是**候选漏检诊断**，不是直接修改生产算法，也不是以视觉增强结果作为疵病真值。

## B.2 输入与保护原则

- 使用26_1、26_2原始12 bit RAW；两帧分别处理，不复制另一帧的候选坐标或Mask。
- 只分析K8A确认的WORK/BAND_EDGE有效工作区域；NON_WORK不纳入疵病报告。
- 读取当前冻结的J5对象、K8B补充来源、K8C证据分流、K8D轮廓审查和最终对象结果作为对照。
- RAW必须只读；ImageJ中的Brightness/Contrast仅用于显示，禁止点击Apply后覆盖原始DN。
- 每次输出记录RAW SHA256、图像尺寸、工作带ID、显示上下限、饱和比例和软件参数。
- 所有人工新发现先记为 `VISUAL_WEAK_REVIEW`，未经独立确认不写入正式疵病表。

## B.3 灰度拉伸设计

对每一条有效工作带分别统计RAW DN分布，建立统一的线性显示映射：

\[
I_8=255\cdot\operatorname{clip}\left(
\frac{DN-L}{U-L},0,1\right)
\]

其中L、U为该工作带的显示下限和上限。建议先比较三组显示窗口：

| 方案 | 下限L | 上限U | 作用 |
|---|---|---|---|
| Stretch-1 | P0.1 | P99.9 | 温和拉伸，保留较多灰度层次 |
| Stretch-2 | P0.5 | P99.5 | 中等拉伸，作为主要观察方案 |
| Stretch-3 | P1.0 | P99.0 | 强拉伸，观察弱暗细节，同时检查噪声放大 |

以上百分位只决定显示映射，不参与检测阈值，不代表缺陷判定标准。

**显示一致性要求：** 同一工作带内所有ROI使用相同的L/U；不能对每个ROI分别自动拉伸后直接比较暗度。若额外做局部ROI自动拉伸，只能标记为辅助观察图，不能用于跨ROI灰度定量。

首轮只做线性Brightness/Contrast，不叠加CLAHE、Gamma、锐化或降噪。否则无法判断细节究竟来自原始DN，还是来自额外图像处理。

## B.4 重点对照区域

每条工作带按四类区域建立图册：

1. **正式结果区：** 当前最终结果中的中、大疵病，检查拉伸后轮廓是否覆盖RAW可见暗异常。
2. **补充候选区：** K8B新增候选及K8C/K8D待复核对象，检查弱候选是否具有稳定RAW暗结构。
3. **视觉新增区：** 拉伸后人工发现、但J5/K8B均没有对应来源的区域，重点记录坐标和局部背景。
4. **背景对照区：** 条带边缘、亮暗过渡、纹理密集区和无明显异常区域，用于识别拉伸后被放大的背景结构。

每条工作带至少选择若干有代表性的局部区域；不能只挑选已知疵病附近的ROI。

## B.5 对视觉新增候选的RAW定量核查

对于人工标记的每个 `VISUAL_WEAK_REVIEW` 区域，在原始RAW DN上计算：

- 候选区域DN中位数；
- 周围背景环DN中位数；
- 候选与背景的绝对DN差；
- 局部背景MAD；
- 相对暗度；
- MAD归一化显著性；
- 候选面积、长宽比、主方向和局部连通性。

可使用以下描述性统计：

\[
\Delta DN=\operatorname{Median}(DN_{bg})-
\operatorname{Median}(DN_{cand})
\]

\[
Z_{MAD}=\frac{\Delta DN}
{\max(3,1.4826\operatorname{MAD}(DN_{bg}))}
\]

这些量用于候选排序和解释，不在本轮直接设定新的生产分类阈值。背景环应避开其他候选、工作带边缘和已知结构；参考像素不足时标记为 `RAW_REFERENCE_INVALID`，不强行计算。

## B.6 与现有检测链的关联规则

每个视觉新增候选必须追溯到以下一种状态：

- `MATCH_FINAL_OBJECT`：与当前最终对象重合；
- `MATCH_J5_SOURCE`：J5有来源，但最终对象处理时未入选；
- `MATCH_K8B_SUPPLEMENT`：由K8B补充通道发现；
- `MATCH_REVIEW_ONLY`：已有来源，但仍处于复核/不稳定状态；
- `NO_EXISTING_SOURCE`：当前J5和K8B均无对应来源。

其中 `NO_EXISTING_SOURCE` 才是需要重点调查的潜在漏检区域。匹配必须在相同RAW、相同工作带和全局坐标系下完成，不能只凭显示图上的视觉接近判断。

## B.7 下一步算法决策

只有在人工复核和RAW DN统计共同支持后，才决定是否开展以下试验：

- 若弱异常在RAW中确实存在，但Black-Hat响应不足：分析核尺寸、结构元素尺度与异常宽度的匹配关系；
- 若Black-Hat响应存在但未达到170 DN：开展局部阈值补充试验，但必须与固定阈值主通道并行、可回退；
- 若局部RAW对比度不足且DoG/形态特征不稳定：优先保留复核，不直接调低阈值；
- 若细节主要位于工作带边缘或背景梯度处：完善工作带边界保护，不将其当作疵病补漏；
- 若为单像素或极小暗点：进入微小候选独立审计，不因面积小而静默删除。

任何新检测支路必须保留原J5结果、完整候选来源、参数快照和独立回归对照。不得用拉伸后的8 bit PNG作为检测输入。

## B.8 实验交付与验收

计划交付：

- `stretch_config.csv`：每帧、每工作带的P0.1/P99.9、P0.5/P99.5、P1/P99和显示参数；
- `visual_weak_candidate_review.csv`：人工新增候选的全局坐标、工作带、来源匹配、复核状态；
- `raw_dn_profiles.csv`：候选与背景的原始DN统计；
- 每工作带三档拉伸图及代表ROI联系图；
- `source_manifest.json`：RAW、Mask和配置文件SHA256；
- `comparison_to_frozen_final.csv`：视觉新增候选与冻结J5/最终对象的对应关系。

验收重点不是“拉伸后看起来更清楚”，而是：
1. 同一RAW、同一工作带使用统一显示窗口后，细节是否可重复观察；
2. 新增区域是否具有可量化的RAW暗差和空间结构；
3. 是否与条带边缘、背景纹理或局部噪声混淆；
4. 是否确实没有对应的J5/K8B来源；
5. 人工确认后是否能够形成独立、可复现的补漏测试案例。

**本附录只定义实验方案，不表示ImageJ实验已经执行，也不改变当前正式生产算法。**


---

# 35. 附录C：26_1 / 26_2 两帧ROI-BH最终结果联合审查

本节将26_2加入审查范围。数据来源为：
- `outputs/K8A_TWO_LEVEL_FINALGUARD_26_1_ROI_BH_20261020_v2`
- `outputs/K8A_TWO_LEVEL_FINALGUARD_26_2_ROI_BH_20261020_v2`

## C.1 两帧独立QA

| 项目 | 26_1 | 26_2 |
|---|---:|---:|
| 全幅参考Tile数 | 1620 | 1620 |
| ROI计划/实际J4 Tile | 765 / 765 | 765 / 765 |
| 跳过的非计划Tile | 855 | 855 |
| WORK/EDGE J5对象 | 687 | 398 |
| 最终对象数 | 36 | 35 |
| 最终二值Mask与全幅参考差异 | 0 px | 0 px |
| 人工批准Mask数量 | 2 | 2 |
| 人工批准Mask逐像素一致 | 是 | 是 |
| 人工负例冲突像素 | 0 | 0 |
| 独立QA | PASS | PASS |

26_1的人工批准Mask面积为297、398 px²；26_2为348、370 px²。人工批准对象只在对应RAW身份匹配时应用，不得跨帧复制。

## C.2 精确Mask几何完整性

对每个最终对象的NPZ精确二值Mask逐个读取，并在全分辨率区域类型图上检查：

| 项目 | 26_1 | 26_2 |
|---|---:|---:|
| 最终对象NPZ数量 | 36 | 35 |
| NPZ精确Mask像素总和 | 20,356 | 17,709 |
| 最终全分辨率二值Mask像素数 | 20,356 | 17,709 |
| WORK/EDGE之外的Mask像素 | 0 | 0 |
| 对象两两重叠的Mask像素 | 0 | 0 |
| 历史来源账本记录数 | 32,370 | 8,332 |
| 历史账本记录数与QA统计一致 | 是 | 是 |

结果表中的 `final_area_detector_px2`总和与最终二值Mask像素数相等，说明对象级Mask与最终合成Mask之间没有面积损失或重复计数。对象互斥和工作区外像素检查均通过。

## C.3 两帧结果解释

1. 两帧都实际执行765个计划Tile，且没有K8A几何fallback；与1620个全幅Tile相比，各减少855个Tile。
2. 26_1最终对象36个，26_2最终对象35个；对象数量不同是两帧独立成像与独立检测的结果，不应强行要求相同。
3. 两帧最终二值Mask均与各自全幅Fresh参考逐像素一致。该结论是计算结果的回归等价性，不是相对于独立物理真值的Precision/Recall。
4. 两帧人工批准Mask均保持精确像素一致，负例冲突为0。
5. 26_1、26_2的历史来源账本分别保留32,370行和8,332行；其中未在本轮重新计算的历史记录分别为14,917行和4,042行，仍在历史账本中。

## C.4 运行性能

| 时间项 | 26_1 | 26_2 |
|---|---:|---:|
| 总耗时 | 93.863 s | 68.402 s |
| RAW QC | 0.705 s | 0.762 s |
| K8A计划 | 1.007 s | 0.924 s |
| ROI Black-Hat | 3.811 s | 3.989 s |
| J4 | 74.057 s | 54.690 s |
| J5 | 2.468 s | 2.545 s |
| K8最终处理与导出 | 11.168 s | 4.839 s |
| 峰值工作集 | 约1.344 GiB | 约1.294 GiB |

J4仍是主要计算耗时。两帧耗时不同，不应只依据总耗时判断算法效率；输入候选复杂度、RAW局部结构及后续对象数量也会影响执行时间。

---

# 36. 附录D：运行验收元数据与当前源码版本的一致性审查

本节记录2026-11-05对两帧运行产物开展的追加审计。此审计不修改原运行目录。

## D.1 acceptance.json状态与独立QA状态不一致

两帧运行目录的 `acceptance.json`均记录：

`ENGINEERING_OUTPUT_PENDING_INDEPENDENT_QA`

但同目录下的：
- `independent_QA/QA.json`

均记录：
- `status = PASS`
- `errors = []`
- `final_binary_diff_pixels = 0`

因此当前存在**验收汇总状态未随独立QA完成而更新**的问题。应以独立QA明细为当前回归检查结果，同时将acceptance.json标记为元数据状态待同步。

为保护历史运行记录，本次不直接覆盖原acceptance.json。后续如需修正，应新建带版本号的验收汇总文件，并保留原始文件和修改记录。

## D.2 运行源码SHA与当前源码不一致

26_1和26_2各自的 `source_SHA256_at_start.json`均记录221个源文件；当前检查发现：
- 缺失文件：0；
- SHA256不一致文件：4。

不一致文件为：

| 文件 | 运行时SHA256 | 当前文件状态 |
|---|---|---|
| `scripts/run_case03j4_fullscan.py` | `1db8d22e2fe82a35d37e034a63b2b8a4fdcdf0d10c6e7ba8bb52419bf8f66f40` | 当前SHA不同，未找到完全相同的可恢复源码副本 |
| `scripts/run_case03t_threeway_comparison.py` | `11d4b0cc0e28c78e60fa380765fcd15c1af05538265c8e9878cc73f35289bfd9` | 与归档快照一致；当前差异经文本diff检查为注释/文档字符串变化 |
| `src/detection/case03k8a_band_locator.py` | `5da8b55262df30e69de1d0f2257a5f9ee91b69a0c19c219672eb3ba1f0eb33db` | 与归档快照一致；当前差异经文本diff检查为模块说明变化 |
| `src/detection/case03t_hseeded_variable.py` | `11cac9a8b8657981eccc594dd6da5d440573c2af186791700351d988c06e48f2` | 与归档快照一致；当前差异经文本diff检查为模块说明变化 |

除J4以外的三个文件在归档快照与运行时SHA一致，当前文件相对归档快照的差异仅为注释/文档字符串。它们不构成已观察到的算法行为变化。

J4文件的运行时SHA与现存早期归档快照不同。现有早期快照相对当前文件包含缺失的两级ROI调度、`require_computed_response`检查、计划Tile身份核对等实现差异；但该早期快照并非本次运行时的精确版本。因此，**不能用早期快照与当前文件的diff替代运行时版本与当前版本的diff**。

四个当前文件的最后修改时间均为2026-11-05。由于运行时J4源码的精确内容尚未从现存归档中恢复，本报告不对J4运行后代码变化是否影响行为作无证据判断。

## D.3 对当前结果的影响范围

必须区分三个结论：

1. **2026-10-20历史运行结果：** 26_1和26_2的独立QA均PASS，最终二值Mask与各自全幅Fresh参考逐像素一致；但J4运行时源码的精确文件尚未恢复。
2. **2026-11-05当前源码：** 已使用当前源码对26_1、26_2分别进行全新运行，两个新run的221项源码清单均为0项SHA不一致，并再次通过独立QA。当前源码的行为回归闭环已经完成。
3. **本次文档变更：** 只追加/修订Markdown和独立验收汇总文件，没有修改检测源码、RAW、Mask、CSV或历史运行结果。

因此，旧J4源码缺失现在属于历史运行版本的归档/复现问题，不再阻断当前源码版本的两帧回归验收。

## D.4 版本闭环状态与后续工作

已完成：
1. 当前源码重新生成两帧独立运行，run-id分别为 `AUDIT_20261105_CURRENT_SOURCE_26_1_v1` 和 `AUDIT_20261105_CURRENT_SOURCE_26_2_v1`。
2. 两个新run各自记录221项源码SHA256；本次复核均为0项缺失、0项SHA不一致。
3. 两帧重新执行独立QA，均为PASS；Black-Hat工作窗口差异、J4来源差异、最终二值Mask差异均为0。
4. 人工批准Mask逐像素一致、负例冲突为0、历史来源账本完整。
5. 生成独立的 `RECONCILED_ACCEPTANCE_20261105.json`，记录当前源码版本的两帧验收状态；原始acceptance.json保留不覆盖。

仍建议完成：
- 将当前源码快照纳入版本管理，后续每次算法变更使用新run-id并保存源码清单；
- 若需要严格复现10月20日历史J4运行，再单独恢复其SHA为 `1db8d22e...` 的原始源码；若找不到，明确标记该历史版本不可逐字节复现，不用当前源码替代。

**本次审查结论：** 当前源码在26_1、26_2上的重新运行和独立回归均通过；历史J4精确源码仍是归档缺口，但不影响当前版本的行为验收。


---

# 37. 当前源码重新运行：26_1 / 26_2双帧行为回归闭环

为避免历史运行源码SHA不一致继续影响当前版本判断，2026-11-05使用当前源码对两帧RAW重新执行完整 `roi-bh` 流程，采用全新run-id，不覆盖历史结果。

## 37.1 新运行目录

- 26_1：`outputs/AUDIT_20261105_CURRENT_SOURCE_26_1_v1`
- 26_2：`outputs/AUDIT_20261105_CURRENT_SOURCE_26_2_v1`

两帧均识别4条工作带，计划执行765个J4 Tile，无K8A fallback；Black-Hat与J4/J5完成后生成各自最终对象和精确Mask。

## 37.2 当前源码独立QA

| 检查项 | 26_1 | 26_2 |
|---|---:|---:|
| 当前源码SHA清单 | 221项 | 221项 |
| 当前源码SHA不一致 | 0 | 0 |
| 缺失源文件 | 0 | 0 |
| 计划/实际J4 Tile | 765/765 | 765/765 |
| Black-Hat工作窗口差异 | 0 px | 0 px |
| J4分组来源差异 | 0 px | 0 px |
| 最终二值Mask差异 | 0 px | 0 px |
| 最终对象数 | 36 | 35 |
| 人工批准Mask逐像素一致 | 2/2 | 2/2 |
| 人工负例冲突 | 0 px | 0 px |
| 历史来源账本行数 | 32,370 | 8,332 |
| 独立QA | PASS | PASS |

当前源码的最终对象面积总和分别为20,356 px²和17,709 px²，与NPZ精确Mask面积总和、最终全分辨率二值Mask像素数逐项一致。

进一步几何审查：
- WORK/EDGE之外的Mask像素均为0；
- 对象两两Mask重叠像素均为0；
- 历史来源账本行数与独立QA统计一致；
- 两帧实际执行Tile数与计划Tile数一致。

## 37.3 当前源码与历史结果的关系

当前源码重新运行后：
- 26_1最终对象36个，面积总和20,356 px²；
- 26_2最终对象35个，面积总和17,709 px²；
- 两帧最终Mask均与各自2026-10-19全幅Fresh参考逐像素一致；
- 两帧人工批准Mask均保持精确像素一致；
- 两帧负例冲突均为0。

因此，**当前源码版本在26_1、26_2上的行为回归已经闭环**。2026-10-20历史运行的J4精确源码仍是归档缺口，但不再阻断当前源码版本的两帧验收。历史版本不得用当前源码冒充；如需逐字节复现历史运行，仍需单独恢复其精确J4文件。

## 37.4 acceptance.json状态同步

两个新run的原始 `acceptance.json`仍记录 `ENGINEERING_OUTPUT_PENDING_INDEPENDENT_QA`，而独立QA已经PASS。

本次没有覆盖原始acceptance.json，另行生成：
- `outputs/RECONCILED_ACCEPTANCE_20261105.json`

该文件汇总当前源码两帧独立QA和Mask几何检查，综合状态为PASS。原始文件保留其运行时状态和历史证据。

## 37.5 当前运行耗时观察

| 时间项 | 26_1 | 26_2 |
|---|---:|---:|
| 总耗时 | 149.299 s | 114.814 s |
| ROI Black-Hat | 4.678 s | 4.470 s |
| J4 | 112.244 s | 89.602 s |
| J5 | 10.098 s | 10.398 s |
| K8最终处理与导出 | 16.029 s | 6.856 s |
| 峰值工作集 | 约1.460 GiB | 约1.324 GiB |

与10月20日运行相比，本次总耗时和J4/J5耗时更高，但目前没有证据将差异直接归因于算法代码变化。后续若需要评价性能，应在固定机器状态、固定输入和相同输出配置下重复至少3次，比较中位数，并同时记录磁盘缓存、CPU负载和内存占用。

## 37.6 当前验收结论

- **算法回归：** 当前源码两帧均PASS。
- **工作区边界：** 无WORK/EDGE之外的最终Mask像素。
- **对象几何：** 精确Mask面积守恒、对象互斥。
- **人工约束：** 批准Mask保持、负例不重新引入。
- **来源追溯：** 历史来源账本完整。
- **版本管理：** 当前源码221项SHA清单无差异；10月20日历史J4精确源码仍待归档。
- **产品准确率：** 仍需独立物理真值和盲测，不能由像素级回归PASS替代。

独立汇总报告见 `CURRENT_SOURCE_REVALIDATION_20261105.md`；机器可读验收结果见 `outputs/RECONCILED_ACCEPTANCE_20261105.json`。


---

# 38. K8B分波段阈值模块专项审查（2026-11-05）

本节只审查K8B，不修改K8B源码、阈值、RAW、历史候选或K8C及后续模块。

## 38.1 审查结论

- K8B算法实现、WORK_CORE约束和候选源像素保留：PASS。
- 当前源码对26_1/26_2的8个工作带重新运行，与历史K8B B候选Mask逐像素一致，XOR均为0 px。
- 四处已人工确认暗斑均有K8B源候选种子覆盖；种子只占最终恢复Mask的一部分，完整外围来自后续处理。
- 20张RAW的K8A/B/C前段筛查20/20 PASS；该结论不等于20张RAW完整J4/J5/K8D/E验收。
- robust-Z阈值的Precision/Recall及跨带同虚警率假设仍未由独立真值验证，不能将B候选数视为真实疵病数。

## 38.2 当前工程中的K8B定位

当前 `run_unified_raw_input.py` 的 `fresh_b()` 和 `run_two_level_unified.py` 实际调用K8B阈值与滞后分割函数。K8B B分支已作为补充候选来源进入统一检测链，但阈值仍未取得独立真值意义上的生产参数认证。

## 38.3 26_1/26_2关键统计

| 指标 | 26_1 | 26_2 |
|---|---:|---:|
| A固定候选连通域 | 3,009 | 528 |
| B自适应候选连通域 | 16,766 | 3,892 |
| A候选像素 | 12,424 | 7,734 |
| B候选像素 | 39,333 | 14,753 |
| B相对A新增像素 | 26,909 | 7,019 |
| B2自适应阈值 | 64.7143/87.0000 | 64.2500/86.7500 |
| B2候选连通域 | 4,417 | 1,483 |

26_2 Band02的1,483个B候选中，1,402个仅1–2 px²；说明补充候选中微小响应占比很高，不能直接替换固定阈值生产链。

## 38.4 四处人工确认暗斑种子覆盖

| 对象 | 最终Mask面积 | K8B种子像素 | 种子占最终Mask比例 |
|---|---:|---:|---:|
| 26_1 Band04 | 297 px² | 88 px² | 29.6% |
| 26_1 Band02 | 398 px² | 79 px² | 19.8% |
| 26_2 Band02 G006 | 370 px² | 115 px² | 31.1% |
| 26_2 Band02 G009 | 348 px² | 40 px² | 11.5% |

该检查证明四处已确认对象均有K8B源种子，但不等于K8B独立完成了完整轮廓。

## 38.5 测试与版本

- K8B专项单元测试：8 passed。
- 当前源码26_1/26_2：8个工作带Mask逐像素复现，阈值和候选连通域数一致。
- 当前K8B算法模块SHA256与冻结发布清单登记值一致：`e0bdbd1358782980c74ac1e24099d8eca4faf162af5d4eb73074b14d04623b3a`。

发现两个维护事项：
1. `PerBandTrial.minimum_hysteresis_connected_area_px`字段没有传入各运行调用；当前默认均为1，现有结果不受影响，但非默认配置不会生效。
2. 冻结发布清单K8B阶段登记了算法模块，但未在该阶段条目中同时登记历史执行脚本，建议后续补全执行脚本与验证脚本的版本依赖。

## 38.6 最终决定

**保留当前K8B源码和阈值，不在本轮修改。** 继续将B分支作为补充候选来源，与后续分类和RAW安全判断配合；取得独立人工真值后，再决定是否调整阈值及是否正式认证。

完整证据、算法公式、20张RAW统计、源Mask复现记录和问题清单见：
`K8B_MODULE_AUDIT_20261105.md`。


## 38.7 K8B图像证据

以下图片来自K8B历史试验输出目录（2026-10-13），本次审查对其进行了核对并将其插入本报告。它们不是本次审查新生成的图像。所有黄色标记均表示候选像素，不是真实疵病真值或最终疵病轮廓。

### 26_1：B分支相对A固定阈值的新增候选像素

![26_1 B minus A新增候选像素总览](outputs/case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2/frame26_1/B_new_vs_A_fixed_overview.png)

### 26_2：B分支相对A固定阈值的新增候选像素

![26_2 B minus A新增候选像素总览](outputs/case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2/frame26_2/B_new_vs_A_fixed_overview.png)

### 26_2 Band02：面积较大的B候选局部图

![26_2 Band02面积较大的12个B候选局部图](outputs/case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2/frame26_2/band02_candidate_review_atlas/band2_top12_by_area_12patches_RAW_B_candidate.png)

### 26_2 Band02：1–2 px²微小B候选抽样图

![26_2 Band02微小候选抽样图](outputs/case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2/frame26_2/band02_candidate_review_atlas/band2_tiny12_deterministic_12patches_RAW_B_candidate.png)

**图像结论：** 新增候选主要集中在暗工作带，同时包含可见暗斑状响应、工作带灰度过渡附近的候选和大量微小连通响应。图片支持K8B的补充候选能力及其候选负担判断，但不提供独立真值，不能据此声称检测准确率。


---

# 39. K8C候选分类与噪声筛选模块专项审查（2026-11-05）

## 39.1 审查结论

- K8C使用RAW局部背景环带、MAD显著性、DoG暗核特征和WORK_CORE边缘距离对K8B候选进行可逆分类。
- K8C不删除源候选；三类分类Mask互斥，且并集严格等于B源Mask。
- 当前源码对26_1的16,766个候选、26_2的3,892个候选逐项复现历史K8C结果，分类、面积、A重叠像素差异均为0。
- 20张RAW共317,673个B候选完成K8A/B/C前段筛查，20/20通过；这不等于完整J4/J5/K8D/K8E检测通过。
- K8C专项测试与K8B/K8C联合测试共18 passed。

## 39.2 当前分类统计

| K8C分类 | 26_1 | 26_2 | 20张RAW |
|---|---:|---:|---:|
| EXISTING_FIXED_H | 3,008 | 528 | 51,997 |
| BOUNDARY_REVIEW | 20 | 6 | 272 |
| MICRO_HIDE_SUGGESTION | 11,524 | 3,168 | 211,349 |
| MICRO_REVIEW | 2,086 | 173 | 49,649 |
| PROMISING_DARK_REVIEW | 13 | 13 | 287 |
| UNCERTAIN_REVIEW | 115 | 4 | 4,119 |
| **总计** | **16,766** | **3,892** | **317,673** |

分类状态是复核优先级，不是真实疵病/噪声标签。

## 39.3 发现的P1问题：40 px²下游面积门限

当前统一RAW入口在K8C分类后还设置 `min_b_source_area_px2=40`。只有面积达到40 px²且分类为PROMISING或UNCERTAIN的候选才进入K8D。

对四处已确认暗斑的源种子复核发现：
- 26_1最终297 px²暗斑的三个初始种子为34、33、21 px²，均未达到40；
- 26_2最终348 px²暗斑的两个初始种子为34、6 px²，均未达到40。

这两处暗斑在当前已知RAW结果中仍然存在，是因为输入RAW哈希匹配历史样本后加载了SHA绑定的人工确认对象；不能据此证明新RAW也能自动检出。

**结论：40 px²门限可能使真实暗斑在新RAW上无法进入K8D。** 该问题列为P1，需单独制定修订方案。本轮没有修改门限。

## 39.4 其他改进项

1. 任意一个A像素重叠就把整个B连通域归为EXISTING_FIXED_H，B-only扩展不再单独评价。A分支不等于J5最终结果，建议后续核对J5覆盖或拆分部分重叠类别。
2. 统一入口传入 `a & b`，绕过了K8C函数对A包含于B的硬断言。20张RAW中A在B外的像素为0，本轮无结果差异；建议后续改为显式断言。
3. 1–2 px²的MICRO_HIDE_SUGGESTION只依据面积，不代表确认噪声；只能作为主图显示隐藏建议。
4. 7%相对暗度、MAD z=2、DoG P90=3 DN等规则尚无独立盲测真值，不能报告Precision/Recall。

## 39.5 图像证据

### 已确认暗斑初始种子与K8C分类

![四处已确认暗斑对应的K8B种子及K8C分类](outputs/K8C_MODULE_AUDIT_20261105/K8C_confirmed_darkspot_seed_classification_audit.png)

### A/B部分重叠候选及B-only扩展

![A固定阈值与B自适应阈值部分重叠候选](outputs/K8C_MODULE_AUDIT_20261105/K8C_partial_fixed_A_overlap_candidates.png)

### 26_2 Band02的RAW局部候选证据

![第二帧Band02候选RAW局部及K8C分类](outputs/case03k8c_band_supplement_review/run_20261013_f1_f2_allbands_reversible_v2/frame26_2/band02/review_large12_RAW_vs_K8C_outline.png)

### 20张RAW微小候选显示隐藏建议

![20张RAW的K8C微小候选隐藏建议接触表](outputs/K8C_MODULE_AUDIT_20261105/20_RAW_K8C_MICRO_SUGGEST_HIDE_CONTACT_SHEET_preview.png)

## 39.6 文档与处理决定

独立审查报告：

`K8C_MODULE_AUDIT_20261105.md`

本轮未修改K8C源码、阈值、统一检测门限、RAW和历史检测结果。保留K8C可逆分类机制；40 px²下游门限列为P1，A/B部分重叠和调用断言列为P2。

**K8C审查完成。** 完整算法顺序、关键参数、复现统计、20张RAW结果、确认暗斑种子追溯、问题清单及全部图像证据见独立审查报告。


## 39.7 K8C分类Mask在统一输出中的持久化（P2）

独立K8C试验脚本保存了promising/review/micro三类像素级Mask；但当前统一入口 `fresh_b()` 调用K8C时使用 `rows,_,_,_=`，丢弃三个Mask返回值。当前统一运行目录只保存B源Mask和候选级分类CSV，没有直接保存三类K8C像素级Mask。

候选级分类信息仍在 `ALL_SOURCE_DISPOSITIONS.csv` 中，可依据源连通域标签重建，因此不是候选数据丢失；但缺少直接可视化和像素级复核文件。建议后续统一工程修订时保存三类K8C Mask，并增加互斥与并集等于B源Mask的运行时检查。


---

# 40. K8D RAW外围稳定性与候选关联模块专项审查（2026-11-05）

## 40.1 审查结论

- K8D核心源码与冻结发布清单SHA256一致；11项K8D单元测试通过。
- 26_1/26_2历史K8D v3共32个优先候选完成像素级复现，原B源/J5未修改，未自动合并正式ID。
- 20张RAW K8DE优先复核阶段20/20帧状态PASS，共审计317,673个B源候选，执行4,643条RAW外围试验；但26_1/26_2使用既有K8I2冻结结果，18张新RAW才由该脚本实际运行。
- 20RAW试验未处理全部微小候选、未完成J5/B生产级跨通道去重、没有自动批准任何新物理疵病。
- 当前统一入口额外的8倍增长门限拒绝6/14个K8D稳定外围；K8C的40 px²上游门限还挡住C626等小种子回归案例。
- K8D存在SOURCE_ONLY_NO_MEANINGFUL_EXPANSION状态与返回Mask不一致的代码问题，20RAW新帧中8/9个该状态返回Mask仍有少量扩张。

## 40.2 关键结果

| 项目 | 26_1 | 26_2 | 20RAW K8DE |
|---|---:|---:|---:|
| K8D独立v3候选数 | 13 | 19 | — |
| K8D独立v3扩展数 | 10 | 11 | — |
| 当前统一入口K8D试验 | 12 | 9 | 不适用 |
| 当前统一入口稳定状态 | 7 | 7 | — |
| 当前统一入口被8倍门限拒绝 | 5 | 1 | — |
| RAW优先试验总数 | — | — | 4,643 |
| K8E像素级复核组 | — | — | 4,546 |

20RAW的4,546是像素并集复核组数，不是真实疵病数；20/20帧PASS也不等于完整生产检测验收通过。

## 40.3 P1：统一入口8倍增长门限覆盖K8D稳定判断

当前统一入口配置 `max_raw_growth_ratio=8.0`。K8D已经通过3/2/1.5 MAD增长、边界嵌套、WORK_CORE、形状和绝对面积约束的外围，仍可能被该门限拒绝。

本轮核实6个实际被拒绝对象，增长比例为10.49×至34.04×。它们的RAW外围面积均不超过K8D内部2,000 px²绝对面积限制。结果是K8D稳定外围没有进入统一最终候选，原始小seed被保留。

### 8倍门限拒绝的稳定外围示例

![K8D稳定外围被当前统一入口8倍增长门限拒绝](outputs/K8D_MODULE_AUDIT_20261105/K8D_unified_8x_gate_rejected_stable_outer_examples.png)

## 40.4 P2：SOURCE_ONLY_NO_MEANINGFUL_EXPANSION返回值不一致

当扩张比例低于12%时，代码设置SOURCE_ONLY_NO_MEANINGFUL_EXPANSION，但仍返回selected_raw_mask与seed的并集，而不是seed本身。合成验证中100 px² seed返回101 px²，状态仍为SOURCE_ONLY。

20RAW新帧中9条该状态有8条返回面积大于seed。K8DE脚本将这些Mask继续传入后续复核分组；现有独立验证没有检查该状态必须严格等于原seed。建议后续返回seed.copy()并增加回归测试。

## 40.5 候选选择范围存在路径差异

- K8D双帧v3仅处理32个优先候选；
- 20RAW K8DE优先复核处理PROMISING、UNCERTAIN、BOUNDARY类别；
- 当前统一入口只处理PROMISING/UNCERTAIN且面积≥40 px²候选，并额外执行8倍增长门限。

因此，K8D独立试验、20RAW优先复核和当前统一RAW入口并非同一套候选接纳规则。尤其C626的34 px² seed→348 px² K8D稳定外围，在当前统一入口中先被40 px²门限排除。

### 26_2四个关键回归对象

![1148、1161、626、1483的K8D旧结果与新外围对照](outputs/case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3/frame26_2/K8D_REGRESSION_4TARGET_OLD_VS_NEW.png)

## 40.6 20RAW K8DE优先复核示例

![30_4样本K8DE优先复核图](outputs/CASE03_FROZEN_K8DE_PRIORITY_ALL20_20261019_v1/30_4/K8DE_ALL_PRIORITY_REVIEW_1to8.png)

该图为候选复核显示，不是最终生产疵病标注。K8D外围和K8E精确并集均没有自动形成正式疵病ID。

## 40.7 文档与处理决定

独立审查报告：

`K8D_MODULE_AUDIT_20261105.md`

本轮未修改K8D源码、40 px²门限、8倍增长门限、K8E分组规则、RAW或历史检测结果。保留K8D核心稳定性算法；将8倍门限与小种子排除列为P1，将SOURCE_ONLY返回值问题列为P2。

**K8D审查完成。** 完整算法顺序、参数、32候选复现、20RAW范围、21条当前统一入口试验、问题证据和全部图像见独立审查报告。


---

# 41. K8E候选关联与精确像素并集模块专项审查（2026-11-06）

## 41.1 审查结论

- K8E核心源码SHA256与冻结发布清单一致；K8E单元测试10 passed，K8E/K8F/K8I组合测试25 passed。
- 26_1/26_2共32个K8D候选全部分配到31个K8E组；每组保存的精确OR并集均可从K8D源Mask按全局RAW坐标逐像素重建。
- 原B/J5/K8B/K8C/K8D源Mask和正式ID没有修改；K8E group_id只是复核/显示编号。
- 26_2 G009的1148/1161外围面积和739 px²经精确并集变为370 px²，正确去除369 px²重复像素；G006的658只作为嵌入B源成员，不额外增加348 px²组面积。
- 新增跨组审计发现：26_1有G001/G002、G002/G003两对组间交叠，共1,510 px²重复覆盖；K8E当前组面积汇总为组面积之和，不是全局唯一像素面积。
- B源标签1028（74 px²）同时嵌入G001/G002，K8E本层没有标记多组归属冲突；K8I已将其正确路由为B_K8E_MULTIGROUP_CONFLICT。
- K8E的J5重复检查只检测J5中心点；K8F在G006/G009批准前增加全部J5显示BBox相交检查，结果为0。
- 当前统一最终检测对K8D不稳定组回退原始B源，并在最终对象层执行全局像素交叠处理；历史最终QA记录74个输出对象的Mask两两不相交。

## 41.2 真实结果统计

| 指标 | 26_1 | 26_2 |
|---|---:|---:|
| K8D输入候选 | 13 | 19 |
| K8E组数 | 13 | 18 |
| K8D候选全部分配且仅分配一次 | PASS | PASS |
| 各组精确Mask像素级重建 | PASS | PASS |
| 各组面积和 | 14,570 px² | 4,581 px² |
| 全部组的全局唯一像素并集 | **13,060 px²** | **4,581 px²** |
| 跨组交叠重复覆盖 | **1,510 px²** | 0 px² |
| 多组嵌入成员冲突 | B2标签1028 | 0 |

26_1两组间交叠：
- G001/G002：交集548 px²，IoU=0.1631，最小包含率=0.3329；
- G002/G003：交集962 px²，IoU=0.3903，最小包含率=0.5844。
两对均低于当前自动分组门限，因此保留为独立组，但需要跨组冲突标记。

### K8E跨组交叠诊断图

![K8E F1跨组Mask交叠和重复嵌入B标签1028](outputs/K8E_MODULE_AUDIT_20261106/K8E_F1_cross_group_overlap_and_embedded_1028_diagnostic.png)

## 41.3 P2问题与修订建议

1. **跨组Mask交叠没有单独标记。** 保留当前关联阈值，不强行合并低IoU候选；增加跨组交叠边表和`CROSS_GROUP_OVERLAP_REVIEW`。
2. **同一嵌入B标签可出现在多个组。** 增加全局B标签到K8E group ID索引，多组成员转冲突复核；K8I现有`B_K8E_MULTIGROUP_CONFLICT`作为下游防线继续保留。
3. **组面积和不等于全局唯一面积。** 分别报告各组并集面积和、所有组全局并集面积、交叠像素数；修正“no double count”图注。
4. **J5重叠检查仅使用中心点。** K8E增加保守BBox或精确J5 Mask交叠检查，不能只凭中心点判定无重复。
5. **测试覆盖不足。** 新增跨组交叠、重复嵌入成员、非完全链式分组、全组面积统计和J5交叠回归测试。

本轮未修改K8E源码、阈值、K8F批准白名单、K8I来源记录或最终检测结果。

独立报告：

`K8E_MODULE_AUDIT_20261106.md`

新增审查产物：

`outputs/K8E_MODULE_AUDIT_20261106/`

**K8E审查完成。** 组内精确并集实现通过；跨组交叠和多组嵌入成员需要在K8E本层补充冲突台账，但当前K8I和统一最终检测已对相关情况实施下游保护。


---

# 42. K8F人工确认登记与补充候选写入模块专项审查（2026-11-06）

## 42.1 审查结论

- K8F白名单仅包含第二帧G006和G009；第一帧无新增批准组，第二帧新增2组，其他第一帧13组/第二帧16组仍待人工复核。
- K8F单元测试5 passed，历史独立QA为`K8F_INDEPENDENT_QA_PASS`。
- 原J5工作区683/398条记录的原ID、中心、BBox、面积、最大Feret和尺寸等级与原始J5逐行一致。
- K8E/K8F成员追溯CSV核心字段逐行一致；仅五个B源成员626、658、1148、1161、1186被标记为用户确认。
- G006=348 px²，G009=370 px²，两个批准组精确Mask交集0 px²；与原J5全部4,440条显示BBox碰撞数0。
- K8F输出是独立工作区复核清单，不覆盖原J5正式文件，不生成原J5正式缺陷ID，也不构成生产质量认证。
- G006外围内另有1 px² B640微小碰撞，K8D明确标为`micro_collision=True`且`eligible_same_spot_review=False`；K8I继续把它保留为未批准微小源。K8F批准成员表未显式记录该外围内微小碰撞。
- K8F使用硬编码`PITCH=3.2`，与当前`C.PIXEL_SIZE_UM=3.2`一致，但未跟随未来配置修改。

## 42.2 实际输出

| 指标 | 26_1 | 26_2 |
|---|---:|---:|
| 原J5 WORK候选 | 683 | 398 |
| 用户确认新增组 | 0 | 2 |
| 统一复核清单总行数 | 683 | 400 |
| 其他K8E组待审 | 13 | 16 |
| 原J5中大候选 | 25 | 26 |
| 新组与J5全部BBox碰撞 | 0 | 0 |

新增确认组：
- G006：B626 + B658，348 px²；
- G009：B1148 + B1161 + B1186，370 px²；
- 总面积718 px²，像面当量7,352.32 μm²；不代表滤光片物面真实面积。

### G006额外微小碰撞来源

![G006批准外围内B640微小碰撞像素](outputs/K8F_MODULE_AUDIT_20261106/K8F_G006_extra_micro_collision_640_traceability.png)

## 42.3 P2/P3问题与修订建议

1. G006批准外围中含B640的1 px²微小碰撞，但K8F批准成员字段没有记录该未纳入成员；建议新增`source_B_micro_collisions_not_merged`字段，不改变批准成员和面积。
2. 将`PITCH=3.2`改为`float(C.PIXEL_SIZE_UM)`，使面积/长度像面当量跟随用户配置。
3. 将验证器的数量断言升级为精确集合断言，检查K8E/K8F来源追溯逐行一致、待审组ID精确差集、五个批准成员ID和批准组之间像素交叠。
4. `APPROVALS.expected_primary`当前未使用；新增组记录的`original_J5_grade_unchanged=True`字段语义也可调整。

本轮未修改K8F源码、批准白名单、J5/K8E/K8I或最终检测结果。

独立报告：

`K8F_MODULE_AUDIT_20261106.md`

新增审查产物：

`outputs/K8F_MODULE_AUDIT_20261106/`

**K8F审查完成。** 当前批准逻辑和原J5保护通过；无P1阻断项，保留两项P2配置/来源追溯修订。

