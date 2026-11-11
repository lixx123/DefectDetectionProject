# K8E候选关联与精确像素并集模块专项审查报告

**审查日期：** 2026-11-06  
**工程：** `D:\疵病检测\DefectDetectionProject`  
**审查对象：** K8E同带候选关联、精确像素并集、嵌入B源候选追溯、J5重叠检查及下游K8F/K8I/统一检测调用关系。  
**审查方式：** 源码与单元测试检查、K8E历史独立QA复核、26_1/26_2全部31组掩膜逐像素重算、跨组交叠统计、嵌入B源成员独立覆盖率复核、下游统一检测逻辑检查。  
**代码修改：** 本轮未修改任何算法源码、参数、RAW、K8D/K8E/K8F/K8I历史结果、用户确认记录或最终检测结果。

## 1. 审查结论摘要

**K8E组内精确像素并集实现正确，31个显示组的保存Mask均可由K8D源Mask逐像素重建；原始32个K8D候选均被完整分配，源J5/B数据没有被修改。**

但K8E独立输出存在两个需要修订的工程问题：
1. K8E只在组内执行精确并集，没有检查不同组之间的像素交叠。26_1有两个跨组交叠对，共有1,510 px²被不同组重复覆盖，当前汇总的14,570 px²不是全组全局唯一像素面积。
2. B源标签1028（74 px²）同时作为嵌入成员出现在G001和G002中。K8E本身没有给两个组加跨组冲突标记；后续K8I正确将该源标记为`B_K8E_MULTIGROUP_CONFLICT`并送入复核层。

以上均为K8E复核侧输出/统计的可追溯性问题。当前统一最终检测程序另有全局像素交叠处理，并且对K8D不稳定外围回退至原始B源，因此本轮没有发现这些K8E跨组交叠直接造成最终二值Mask重复计数的证据。

| 审查维度 | 结论 |
|---|---|
| K8E核心源码与冻结清单一致性 | PASS |
| K8E单元测试 | 10 passed |
| K8E/K8F/K8I相关测试组合 | 25 passed |
| 31组精确像素并集重建 | PASS |
| 32个K8D源候选完整分组 | PASS |
| 原B/J5源Mask与正式ID不变 | PASS |
| 嵌入B成员覆盖率独立复核 | PASS |
| 跨组重叠冲突识别 | **P2：K8E本层缺少检查** |
| 重复嵌入成员跨组分配 | **P2：K8E本层未标冲突，K8I下游已识别** |
| J5重复检查 | P2：K8E仅检查中心点，K8F批准前增加BBox检查 |
| 全组全局唯一面积统计 | **P2：当前汇总为组面积之和，不是全局并集** |

## 2. 审查对象与版本

| 类型 | 文件 |
|---|---|
| K8E核心算法 | `src/detection/case03k8e_group_hypothesis.py` |
| K8E执行脚本 | `scripts/run_case03k8e_exact_union_review.py` |
| K8E独立验证 | `scripts/verify_case03k8e_exact_union.py` |
| K8E单元测试 | `tests/test_case03k8e_group_hypothesis.py` |
| K8E下游人工确认登记 | `scripts/run_case03k8f_approved_supplements_ledger.py` |
| K8E全帧来源追溯 | `scripts/run_case03k8i_full_frame_lineage.py` |
| K8E统一最终检测消费 | `scripts/run_case03_unified_final_detector_26_1_2.py` |
| K8E历史输出 | `outputs/case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1` |

K8E核心源码SHA256：

`src/detection/case03k8e_group_hypothesis.py`

`2e0d53338c409a20fac6855228d7433c09b76e8ac34366429077f722be55c4c5`

该SHA256与冻结发布清单`CASE03_FROZEN_RELEASE_20261019_v2/FROZEN_PIPELINE_AND_FILES_SHA256.json`中`03K8E_PIXEL_EXACT_ASSOCIATION`阶段登记值一致。执行脚本、独立验证脚本和测试文件没有作为该阶段的source_files单独登记。

## 3. K8E在完整算法链中的位置

K8E位于K8D之后，职责是对已有K8D RAW外围提议做关联和去重，不负责生成新的疵病候选，也不重新计算黑顶帽、170/230固定阈值或RAW外围。

实际顺序：

1. K8B：产生工作带内B分支连通域候选。
2. K8C：对B候选做RAW证据分类，保留所有源候选。
3. K8D：对选定B候选计算3/2/1.5 MAD RAW外围，并输出稳定/不稳定状态。
4. K8E：只处理K8D选中的32个候选（26_1为13个、26_2为19个），建立组假设并计算组内精确OR并集。
5. K8F：仅将用户目视确认的第二帧G006、G009登记为已确认暗斑补充；其他组保持待审。
6. K8I：将所有J5和B源候选纳入完整来源追溯，并将多组归属的B源标为冲突。
7. 统一最终检测：只消费满足相应状态/面积/人工批准条件的K8E结果，并对最终对象执行全局像素级交叠处理。

**范围限制：** K8E不是全帧所有B候选的关联结果。它只覆盖32个K8D优先候选，不能据此声称整幅图的所有疵病已经完成跨窗口/跨通道去重。


## 4. K8E实际算法执行顺序

### 4.1 输入与空间坐标

每个K8D对象提供：
- 全局RAW像素坐标ROI `box=(x0,y0,x1,y1)`，采用右/下边界不包含的XYXY格式；
- 128×128全分辨率局部K8D外围二值Mask；
- 原始B源种子Mask；
- B连通域标签图；
- K8D状态；
- K8D阶段计算的部分竞争候选和嵌入B成员证据。

本轮抽查的K8D ROI宽高均为128像素，坐标处于原始RAW全分辨率坐标系；K8E没有把8倍预览坐标误当作原始RAW坐标。K8E绘制全帧图时才将全局坐标除以显示抽样步长8。

### 4.2 两候选全局交集

对同一工作带的两个候选，先求两个全局XYXY ROI的交集，再在交叠区域内对二值Mask执行逻辑AND：

`intersection_px2 = count(mask_A AND mask_B)`

随后计算：
- `IoU = intersection / (area_A + area_B - intersection)`
- `min_containment = intersection / min(area_A, area_B)`
- 左右候选覆盖率分别为交集除以各自面积。

无ROI交叠时交集为0；有ROI交叠但二值像素不相交时，交集仍为0。计算基于真实像素坐标，不基于外接矩形面积。

### 4.3 同带候选图关联

只有满足以下两个条件才建立候选关联边：
- 最小轮廓包含率≥65%；
- IoU≥50%。

算法使用并查集将关联边连接的候选组成连通分组。不同工作带之间不建立关联边。

### 4.4 组内非完全配对检查

如果组内候选数大于10，或候选关联边不是完全图（例如A连B、B连C，但A不满足与C的直接关联阈值），则标记为`GROUP_CONFLICT_REVIEW`。

如果任何成员带有K8D部分竞争候选，则同样标记组冲突。

这能避免仅凭链式关联就把所有候选自动认定为同一物理暗斑，但当前代码只检查**同一组内部**的配对完整性，不检查不同组之间是否仍有像素交叠（见第8节）。

### 4.5 组内精确像素并集

`union_global()`建立所有成员ROI的最小全局包围范围，并将每个成员Mask按全局坐标写入布尔画布，执行逐像素OR：

`group_mask = mask_1 OR mask_2 OR ... OR mask_n`

面积定义为`group_mask.sum()`，重复像素数定义为：

`sum(member_mask_areas) - exact_group_union_area`

函数还逐个核验原始成员Mask的所有True像素均存在于并集Mask中。并集不修改任何输入Mask。

### 4.6 嵌入B源成员证据

对没有独立K8D外围、但位于某个K8D RAW外围内的其他B源连通域，若：
- `whole_overlap_fraction >= 0.80`；
- K8D上游标记`eligible_same_spot_review=True`；

则记录为`embedded_B_source_evidence`。这类B源成员只作为待审来源关系，不增加组面积，不生成第二个RAW外围，也不自动合并正式ID。

### 4.7 K8E复核状态

| 状态 | 含义 |
|---|---|
| RAW_SAFETY_UNRESOLVED | 至少一个K8D成员不是STABLE状态 |
| GROUP_CONFLICT_REVIEW | 组内不是完全配对，或存在部分竞争候选，或成员过多 |
| MUTUAL_CONTOUR_NEAR_IDENTICAL_REVIEW | 多个成员的所有配对IoU均≥90% |
| MULTI_PROPOSAL_ASSOCIATION_REVIEW | 多个成员通过关联，但轮廓没有达到近乎相同阈值 |
| EMBEDDED_B_SOURCE_REVIEW | 单个稳定外围中存在完整/近完整嵌入B源成员 |
| SINGLE_STABLE_REVIEW | 单个稳定外围且没有嵌入成员 |

这些是显示/关联复核状态，不是物理缺陷确认状态。

## 5. K8E参数与实际含义

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `pair_min_containment` | 0.65 | 两候选最小包含率门限 |
| `pair_min_iou` | 0.50 | 两候选IoU门限 |
| `mutual_contour_iou_strong` | 0.90 | 多候选近似相同外围参考门限 |
| `full_B_member_coverage` | 0.80 | 嵌入B源候选完整覆盖比例 |
| `max_group_members` | 10 | 超过后转组冲突复核 |
| 全帧图显示步长 | 8 | 仅显示抽样，不改变Mask分辨率 |
| 像元尺寸 | 3.2 μm | 仅探测器像面当量换算 |

组面积和最大Feret由K8E并集Mask计算，单位分别为探测器像素²和像素。换算得到的μm/μm²仍然是探测器像面当量；没有物面放大倍率标定，不能称为滤光片物面真实尺寸。

## 6. 26_1/26_2真实结果与逐像素验证

### 6.1 分组数量与状态

| 指标 | 26_1 | 26_2 |
|---|---:|---:|
| K8D输入候选 | 13 | 19 |
| K8E输出显示组 | 13 | 18 |
| 多个K8D候选归入同组 | 0组 | 1组 |
| 单候选含嵌入B成员 | 5组 | 4组 |
| 原J5 WORK中大候选 | 25 | 26 |
| K8E暂定中大主图显示组 | 7 | 10 |

状态统计：

| K8E状态 | 26_1 | 26_2 |
|---|---:|---:|
| RAW_SAFETY_UNRESOLVED | 6 | 8 |
| SINGLE_STABLE_REVIEW | 5 | 5 |
| EMBEDDED_B_SOURCE_REVIEW | 2 | 4 |
| MUTUAL_CONTOUR_NEAR_IDENTICAL_REVIEW | 0 | 1 |
| **总计** | **13** | **18** |

K8E的`provisional_main_MEDLARGE_eligible`是优先复核显示资格，不是正式疵病批准。尤其EMBEDDED和MUTUAL_CONTOUR组以橙色显示，仍需身份/轮廓复核。

### 6.2 原有独立QA复核

历史`independent_QA.json`记录状态为`K8E_INDEPENDENT_PIXEL_EXACT_QA_PASS`。本轮重新读取并核查其实际产物：
- 26_1的13个、26_2的18个K8E组全部有NPZ精确Mask；
- 每组保存Mask均与该组所有K8D源外围按全局坐标重新OR的结果逐像素相等；
- 每个原K8D B源种子像素均保留在相应组并集中；
- 32个K8D源候选全部且仅分配一次；
- 所有组的`exact_group_union_px2`均等于NPZ中布尔Mask的像素数；
- 26_2 G009的两张高度重叠外围739 px²面积和，被精确并集修正为370 px²，去重369 px²；
- 原J5候选总数保持26_1为15,604、26_2为4,440；
- 原J5、B、K8B、K8C、K8D源数据没有被修改。

### 6.3 关键案例：G009精确并集

26_2 Band02的B源标签1148和1161：
- 原始B种子分别为48 px²和64 px²；
- K8D外围分别为369 px²和370 px²；
- 两外围交集369 px²；
- IoU=0.9973，最小包含率=1.0；
- K8E将其归为`K8E_F2_B2_G009`；
- 面积和739 px²，经精确OR并集后为370 px²；
- 额外嵌入B标签1186为3 px²，100%位于同一外围内，仅记录为待审成员，不再增加面积。

该案例的组内精确去重实现正确。

### 6.4 关键案例：G006嵌入B成员

26_2 Band02的`K8E_F2_B2_G006`：
- 选中K8D外围源B标签626，原始seed为34 px²；
- K8D外围为348 px²；
- 嵌入B标签658为6 px²，覆盖率100%；
- 658不生成独立外围，不增加348 px²组面积；
- K8F只在用户目视确认后，将G006登记为一处暗斑补充。

这与G009的“双K8D外围近乎一致”属于不同证据等级，不能混为一类。



## 7. 新增独立跨组交叠审计

原K8E独立QA验证的是“每个组内部的并集是否正确”，没有检查不同K8E组之间是否仍有像素重叠。本轮将31个组的NPZ Mask放回全局RAW坐标，重新计算全部组间交集，并构造所有组的全局布尔并集。

### 7.1 全局唯一像素统计

| 指标 | 26_1 | 26_2 |
|---|---:|---:|
| K8E组数 | 13 | 18 |
| 各组精确并集面积之和 | 14,570 px² | 4,581 px² |
| 所有组Mask的全局精确并集 | **13,060 px²** | **4,581 px²** |
| 至少被两个组覆盖的唯一像素 | 1,510 px² | 0 px² |
| 重复像素出现次数（超出首次覆盖） | **1,510 px²** | 0 px² |
| 最大组覆盖重数 | 2 | 1 |

26_1的组面积之和比全局唯一并集多1,510 px²，相当于组面积之和的10.36%。因此当前`exact_group_union_total_pixel_area_not_physical_truth=14570`表示**各组内部去重后的面积之和**，不是所有K8E组之间再次去重后的全局唯一像素面积。

### 7.2 26_1两个跨组交叠对

| 组A | 组B | 交集像素 | IoU | 最小包含率 | 两组状态 |
|---|---|---:|---:|---:|---|
| F1-B2-G001 | F1-B2-G002 | 548 | 0.1631 | 0.3329 | 均RAW_SAFETY_UNRESOLVED |
| F1-B2-G002 | F1-B2-G003 | 962 | 0.3903 | 0.5844 | 均RAW_SAFETY_UNRESOLVED |

两组交集分别低于65%包含率和50% IoU门限，因此K8E按当前规则没有把它们自动归并。这种保守分组本身可以接受；问题在于K8E没有把它们记录为**跨组部分交叠冲突**，而且全帧`03_GROUPED_RAW_OUTERS_NO_DUPLICATES.png`副标题写了“no double count”，容易被误解为全局已经去重。

这三个组均为RAW_SAFETY_UNRESOLVED，没有进入K8E暂定中大优先主图。后续统一最终检测也会对这些不稳定组回退至原始B源，而不是直接采用这些交叠RAW外围。因此该问题目前影响K8E研究复核图和组面积汇总的解释，不应误报为最终生产Mask已发生重复面积。

### 7.3 跨组交叠与重复成员诊断图

![26_1 K8E G001/G002及G002/G003跨组交叠，洋红色为重复像素，绿色为重复嵌入B标签1028](outputs/K8E_MODULE_AUDIT_20261106/K8E_F1_cross_group_overlap_and_embedded_1028_diagnostic.png)

图中：
- 青色：组A轮廓；
- 黄色：组B轮廓；
- 洋红色：两个组Mask的共同像素；
- 绿色：嵌入B源标签1028。

### 7.4 P2问题：K8E只做组内并集，没有跨组交叠台账

**发现：** `make_groups()`只在满足阈值的候选间建立边；低于阈值但Mask实际有交集的候选会成为不同组。后续`summary.json`将各组面积直接求和，没有计算所有组Mask的全局并集。当前26_1因此存在1,510 px²跨组重复覆盖。

**建议：**
1. 不降低现有65%/50%关联阈值，不强行把低重叠候选合并。
2. 在分组后额外计算全部不同组之间的像素交集。
3. 对有交集的组添加`CROSS_GROUP_OVERLAP_REVIEW`或单独的冲突边表，保留原组身份。
4. 汇总同时输出`sum_of_group_union_areas_px2`与`global_union_of_all_group_masks_px2`，不能将二者混称为唯一总面积。
5. 将图像副标题改为“per-group exact union; cross-group overlap may remain”。

## 8. 重复嵌入B成员审查

### 8.1 B标签1028同时属于两个K8E组的证据

26_1 Band02的B标签1028：
- 原始B连通域面积：74 px²；
- 在G001的128×128源标签图中可见74 px²，全部74 px²落入G001外围；
- 在G002的128×128源标签图中同样可见74 px²，全部74 px²落入G002外围；
- 因此其`whole_overlap_fraction`在两个组中均为1.0；
- 两个组的原始全局坐标一致，确实是同一个B源连通域，不是标签编号碰撞。

K8E的`make_groups()`只在单个组内部用字典去重嵌入成员，没有维护全局`B_label → K8E_group_ids`索引。因此同一嵌入B源可同时出现在多个组的`K8E_source_member_traceability.csv`中。

### 8.2 下游K8I已正确识别该冲突

本轮检查K8I的`end_to_end_candidate_lineage.csv`：
- B:F1:B02:C0001028的`K8E_group_ids`为`K8E_F1_B2_G001;K8E_F1_B2_G002`；
- `primary_visibility_layer=B_K8E_MULTIGROUP_CONFLICT`；
- `user_confirmation_state=PENDING_REVIEW`；
- `is_user_confirmed=False`；
- 原始74 px² B源像素完整保留。

K8I独立QA的26_1结果也记录了1个`B_K8E_MULTIGROUP_CONFLICT`，26_2为0个。也就是说，K8E自身没有标出重复成员，但下游全帧来源追溯已将它正确降级为冲突复核，而不是静默选取某一个组。

### 8.3 全部嵌入成员覆盖率独立复核

本轮将K8E的`source_full_px`与K8I全帧B源记录中的完整连通域面积对照，并在K8E保存的全局标签图中重新统计落入外围的像素：

| 帧/组/B标签 | 完整源面积 | 组ROI内可见像素 | 落入外围像素 | 声明覆盖率 | 独立复算 |
|---|---:|---:|---:|---:|---:|
| F1 G001 / 460 | 3 | 3 | 3 | 1.000 | 1.000 |
| F1 G001 / 498 | 26 | 26 | 26 | 1.000 | 1.000 |
| F1 G001 / 1028 | 74 | 74 | 74 | 1.000 | 1.000 |
| F1 G002 / 1028 | 74 | 74 | 74 | 1.000 | 1.000 |
| F1 G003 / 1563 | 3 | 3 | 3 | 1.000 | 1.000 |
| F1 G004 / 1787 | 23 | 23 | 23 | 1.000 | 1.000 |
| F1 G012 / 1435 | 5 | 5 | 5 | 1.000 | 1.000 |
| F2 G006 / 658 | 6 | 6 | 6 | 1.000 | 1.000 |
| F2 G009 / 1186 | 3 | 3 | 3 | 1.000 | 1.000 |
| F2 G015 / 115 | 4 | 4 | 4 | 1.000 | 1.000 |
| F2 G017 / 424 | 6 | 6 | 5 | 0.8333 | 0.8333 |
| F2 G018 / 569 | 4 | 4 | 4 | 1.000 | 1.000 |

12条嵌入成员记录的完整源面积均与K8I来源记录一致；12条覆盖率也与独立像素统计一致。F2 G017的B424有6 px²，其中5 px²落入外围，覆盖率83.33%，刚超过80%阈值；该成员仍然是待审关联，不是确认同一物理暗斑。

**结论：** 嵌入成员的源面积与覆盖率数值正确；真正的问题是同一成员可能被多个组重复引用，需要在K8E阶段增加全局冲突标记。K8I现有逻辑已经对此做了防护。



## 9. J5重复候选检查与K8E下游消费

### 9.1 K8E本层J5检查的边界

K8E执行脚本的`inside_j5_centers()`检查方式是：
- 读取冻结的`original_J5_object_center_workband_classification.csv`；
- 只选取J5中心位于WORK_CORE的对象；
- 判断J5中心像素是否落在K8E组外围Mask内。

26_1/26_2共31个组的`J5_centers_inside_outer`均为0。

这是一种中心点重叠筛查，不是J5原始像素Mask与K8E外围的完整交集，也不是BBox相交检查。若K8E外围只与J5对象边缘相交、但没有覆盖其中心，K8E本层可能不会把它标为`EXISTING_J5_CENTER_OVERLAP_REVIEW`。

### 9.2 K8F对实际批准组增加了更严格的检查

K8F只批准第二帧两个用户已目视确认的组：
- G006：626+658，面积348 px²；
- G009：1148+1161+1186，面积370 px²。

K8F在写入统一工作区复核清单之前，对每个批准组的紧外接框与原J5全部对象显示BBox做相交检查，而不只是检查J5中心。两组对原J5全部4,440条记录的BBox相交数均为0。

K8F独立QA为`K8F_INDEPENDENT_QA_PASS`：
- 仅批准G006/G009；
- 第一帧0个新增批准组；
- 第二帧2个新增批准组；
- 其余第一帧13组、第二帧16组仍待人工复核；
- 原J5源记录、ID和面积不变。

因此，K8E中心点检查本身不够严格，但当前两处实际批准组已通过K8F更保守的BBox碰撞检查。该限制仍应在K8E本层修订，避免其他待审组在优先显示层被误解为已经完成J5去重。

## 10. K8I与统一最终检测的下游保护

### 10.1 K8I全帧来源追溯

K8I读取K8E组成员关系后，按每个B源候选关联的K8E group ID数量分类：
- 没有K8E组：按B源类别路由；
- 只属于一个已批准组：`B_K8E_GROUP_CONFIRMED`；
- 只属于一个未批准组：`B_K8E_GROUP_PENDING`；
- 同时属于多个K8E组：`B_K8E_MULTIGROUP_CONFLICT`。

K8I历史独立QA记录：
- 26_1：J5 15,604条、B 16,766条，来源全部有路由；1个多组冲突；
- 26_2：J5 4,440条、B 3,892条，来源全部有路由；2个已批准K8E组，0个多组冲突；
- 原始源像素修改数为0；
- K8D没有对全部B候选重新运行，K8E也只覆盖已选K8D候选。

### 10.2 统一最终检测程序如何消费K8E

当前`run_case03_unified_final_detector_26_1_2.py`读取K8E组测量表和K8F批准登记：
- 只有K8F明确批准的G006/G009可以将嵌入B源成员加入同一补充对象来源集合；
- 未批准的K8E组若为`RAW_SAFETY_UNRESOLVED`，则回退到组内原始B种子，不直接使用不稳定K8D外围；
- 超过统一8倍增长门限的未批准组同样回退至原始B种子；
- 其他满足状态和面积门限的稳定组才使用K8E精确外围；
- 之后对J5、B和K8E来源统一执行全局像素交叠合并/冲突处理，并保证最终Mask两两不重叠。

因此，26_1 G001/G002/G003的跨组重叠没有被作为三个大RAW外围直接写入最终结果；这些组因RAW_SAFETY_UNRESOLVED而回退到原始B种子。标签1028则保留为独立B源候选并带有多组冲突来源记录。

### 10.3 统一最终检测历史QA

现有`CASE03_UNIFIED_FINAL_TWO_RAW_INDEPENDENT_QA_PASS`记录：
- 26_1最终对象39个；
- 26_2最终对象35个；
- 共74个最终输出对象；
- 两帧最终Mask均两两像素不相交；
- 四处用户确认暗斑原始二值Mask保持精确；
- 40,702条J5/B源记录全部完成来源处置；
- 未测量独立真值Precision/Recall。

74是当前统一算法输出对象数，不是经全图真值确认的真实疵病数。

## 11. K8E问题清单与修订建议

本轮没有发现K8E组内像素并集计算错误，也没有发现原始B/J5数据被修改。以下列出K8E自身仍需改进的项目。

### K8E-01：跨组Mask交叠没有在K8E层形成冲突记录（P2）

**证据：** 26_1 G001/G002交集548 px²、G002/G003交集962 px²；两对都低于自动关联阈值，因而保留为不同组，但没有在K8E测量表中标注跨组交叠冲突。

**建议：** 分组后增加全组两两交叠审计；不强行合并低IoU组，只增加`CROSS_GROUP_OVERLAP_REVIEW`关系和可追溯边表。

### K8E-02：重复嵌入B成员没有在K8E本层标记多组冲突（P2）

**证据：** F1 B2标签1028（74 px²）以100%覆盖率同时列入G001/G002。K8I已将其标为`B_K8E_MULTIGROUP_CONFLICT`。

**建议：** K8E生成所有组后，建立全局`(band_id,B_label) → group_ids`索引。一个B标签出现在多个组时，在所有相关组中标记成员归属冲突，并将其从单组唯一成员统计中分离。K8I现有冲突规则继续保留，作为下游第二道防线。

### K8E-03：组面积总和没有与全组全局唯一面积分开（P2）

**证据：** F1各组面积和14,570 px²，而所有组全局精确并集只有13,060 px²；两者相差1,510 px²。F2两者均为4,581 px²。

**建议：** 汇总分别写入：
- `sum_of_group_union_areas_px2`；
- `global_union_of_all_group_masks_px2`；
- `intergroup_overlap_unique_pixels`；
- `excess_duplicate_pixel_occurrences`。

不得将组面积之和解释为全局唯一面积或真实缺陷总面积。

### K8E-04：J5重叠检查仅使用中心点（P2）

**证据：** K8E的`inside_j5_centers()`不读取J5真实二值Mask或BBox；K8F在批准前才补充全部J5显示BBox碰撞检查。

**建议：** K8E本层改为至少执行保守BBox相交检查；若可获得J5精确Mask，进一步执行全局像素交集。中心点检查可保留为独立字段，不应作为唯一排除依据。

### K8E-05：独立测试未覆盖跨组交叠和重复嵌入成员（P2）

当前10项K8E测试覆盖：
- 近似相同轮廓的精确OR并集；
- 分离候选不合并；
- 不跨工作带分组；
- 嵌入成员保留待审；
- 部分重叠竞争候选；
- 非稳定RAW不提升为稳定组；
- 大小差异候选不因包含率单独合并；
- 全局坐标并集及输入不修改；
- ROI形状不一致拒绝。

缺少：
- 两个不满足合并阈值但Mask有交叠的独立组冲突记录；
- 同一B标签被两个组同时引用；
- 三候选链式连接但非完全配对；
- 全组面积和与全局唯一面积的差异断言；
- K8E组与J5 BBox/像素Mask交叠的独立检查。

**建议：** 在K8E修订时新增上述合成回归测试，不要通过降低现有关联阈值来掩盖跨组冲突。



## 12. 最终处理决定

1. 保留当前K8E 65%包含率、50% IoU、90%近同外围和80%嵌入成员覆盖率规则；本轮不改参数。
2. 保留组内精确布尔OR并集逻辑。31组的保存Mask已通过逐像素重建，不能因为跨组冲突就否定组内并集正确性。
3. 将跨组像素交叠审计列为P2：保留不同组身份，但必须记录交叠关系并在显示层明确标注。
4. 将重复嵌入B成员列为P2：K8E本层增加全局多组成员冲突标记；保留K8I现有`B_K8E_MULTIGROUP_CONFLICT`规则。
5. 汇总区分组面积和与全组全局唯一像素并集，修正“no double count”容易引起的误读。
6. K8E的J5重复检查增加BBox/像素Mask交叠，不再仅依赖J5中心点；K8F批准前的BBox碰撞保护继续保留。
7. K8E暂定中大主图只用于优先复核；`EMBEDDED_B_SOURCE_REVIEW`和`MUTUAL_CONTOUR_NEAR_IDENTICAL_REVIEW`不得自动成为正式疵病身份。
8. 只有明确用户确认的K8E组才能通过K8F写入已确认补充登记；其他组继续待审。
9. 不将K8E面积/长度称为滤光片物面真实尺寸；没有物面倍率标定前只报告探测器像面当量。

**K8E最终结论：核心组内精确并集、来源保留和历史像素级复现通过；26_2的1148/1161去重案例正确。26_1存在两对跨组Mask交叠（共1,510 px²重复覆盖）及B标签1028多组嵌入归属。K8I和统一最终检测已对这些情况实施下游冲突路由/像素级保护，但K8E本层应补充跨组冲突台账和全局唯一面积统计。当前不需要推翻K8E主算法，也不应擅自降低关联阈值。**

## 13. 图像证据与结果图册

### 图13-1　26_1跨组交叠与重复嵌入B标签1028

![K8E G001/G002与G002/G003跨组Mask交叠](outputs/K8E_MODULE_AUDIT_20261106/K8E_F1_cross_group_overlap_and_embedded_1028_diagnostic.png)

### 图13-2　26_2 G009：1148/1161双外围精确并集

![G009的RAW、B源种子、K8D外围及精确OR并集](outputs/case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1/frame26_2/group_detail/K8E_F2_B2_G009_RAW_sources_exact_union.png)

**结论：** 两个外围交集369 px²，面积和739 px²，精确并集370 px²；B标签1186仅作为100%嵌入成员待审。

### 图13-3　26_2 G006：626/658嵌入成员

![G006的RAW、B源种子、K8D外围及精确OR并集](outputs/case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1/frame26_2/group_detail/K8E_F2_B2_G006_RAW_sources_exact_union.png)

**结论：** B标签658为6 px²，完整落入626的348 px² K8D外围，不单独增加面积。该组后来经用户目视确认，K8F登记为已确认暗斑补充。

### 图13-4　26_1 K8E优先主图

![J5中大候选与K8E临时关联候选优先显示](outputs/case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1/frame26_1/02_PRIORITY_J5_MEDLARGE_plus_K8E_GROUPED_REVIEW.png)

### 图13-5　26_2 K8E优先主图

![J5中大候选与K8E临时关联候选优先显示](outputs/case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1/frame26_2/02_PRIORITY_J5_MEDLARGE_plus_K8E_GROUPED_REVIEW.png)

### 图13-6　K8I多组成员冲突全帧复核图

![K8I将K8E pending和multigroup conflict单独分层](outputs/case03k8i_full_frame_lineage/run_20261015_sample26_2frames_fullcandidate_lineage_v1/frame26_1/02_ALL_K8E_PENDING_AND_CONFLICT_GROUPS_1to4.png)

## 14. 测试结果、审查产物与未执行操作

### 14.1 测试结果

单独运行：

`pytest -q tests/test_case03k8e_group_hypothesis.py`

结果：**10 passed**。

组合运行：

`pytest -q tests/test_case03k8e_group_hypothesis.py tests/test_case03k8f_confirmed_register.py tests/test_case03k8i_lineage_rules.py`

结果：**25 passed**。

此外，本轮对31个K8E NPZ组Mask进行了独立全局坐标重建，并对12条嵌入成员证据逐条复算，均与历史记录一致。

### 14.2 新增审查产物

目录：

`outputs/K8E_MODULE_AUDIT_20261106/`

新增文件：
- `K8E_F1_cross_group_overlap_and_embedded_1028_diagnostic.png`
- `K8E_intergroup_overlap_audit.csv`
- `K8E_repeated_embedded_member_audit.csv`
- `K8E_global_union_audit.json`

独立审查报告：

`K8E_MODULE_AUDIT_20261106.md`

总算法开发报告已追加第41节K8E专项审查摘要。

### 14.3 本轮未执行

- 未修改`case03k8e_group_hypothesis.py`及任何K8E参数；
- 未修改K8E历史分组CSV、NPZ、图像、独立QA；
- 未修改K8F用户批准白名单或K8I来源追溯结果；
- 未修改统一最终检测脚本、正式J5 ID或最终Mask；
- 未重新运行26_1/26_2全套生产检测；
- 未将任何待审K8E组新增为用户确认暗斑；
- 未宣称获得Precision、Recall或真实物面尺寸。

**K8E专项审查完成。** 下一模块按执行顺序进入K8F：人工确认登记与新增补充候选写入。重点检查人工批准白名单、批准前几何排重、原J5记录不可变性、B源成员映射及新增复核记录是否存在重复/遗漏。
