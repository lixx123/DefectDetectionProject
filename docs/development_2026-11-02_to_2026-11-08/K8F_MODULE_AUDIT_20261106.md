# K8F人工确认登记与补充候选写入模块专项审查报告

**审查日期：** 2026-11-06  
**工程：** `D:\疵病检测\DefectDetectionProject`  
**审查对象：** K8F人工批准白名单、K8E确认组读取、J5空间排重、统一工作区候选索引、B源成员追溯、Mask导出及K8F下游消费。  
**审查方式：** 源码/验证脚本/单元测试检查、K8E/K8F/J5输出逐行核对、批准Mask逐像素核对、全部J5 BBox碰撞复核、K8I和统一最终检测调用检查。  
**代码修改：** 本轮未修改任何K8F源码、审批白名单、K8E/K8F/K8I历史结果、J5原始记录、RAW或最终检测Mask。

## 1. 审查结论摘要

**K8F当前人工确认白名单、原J5候选保留、两处批准组几何验证和J5 BBox排重均通过。** 只有第二帧G006/G009两组进入独立统一工作区复核清单；第一帧没有新增批准组；其余13/16个K8E组继续待审。

本轮重新核对发现：
- 原J5工作区683/398条记录的中心、BBox、面积、最大Feret和尺寸等级均与原始J5逐行一致；
- K8E成员追溯CSV与K8F导出的追溯CSV逐行一致，只有5个B源成员被标记为用户确认；
- 两个批准组的精确Mask互不相交，面积分别348和370 px²；
- 两个批准组与原J5全部4,440条候选显示BBox均无相交；
- K8F测试5 passed，历史独立QA为`K8F_INDEPENDENT_QA_PASS`。

发现两个需要改进的P2问题：
1. G006批准外围Mask中还包含一个1 px²的B640微小碰撞像素。K8D明确将它标为`micro_collision=True`且`eligible_same_spot_review=False`，K8I仍将其作为独立待审微小源保留；K8F批准记录没有显式记录这个“位于批准外围内但不属于已批准成员”的微小碰撞来源。
2. K8F脚本将像元尺寸`PITCH=3.2`写死，而工程配置已有`C.PIXEL_SIZE_UM=3.2`可配置项。当前结果正确，但以后修改用户配置时K8F报告尺寸不会自动跟随。

本轮没有发现错误批准其他K8E组、修改原J5记录或将两处目视确认组误写成正式生产缺陷ID的情况。

| 审查维度 | 结论 |
|---|---|
| 仅G006/G009两组批准 | PASS |
| 683/398条原J5 WORK记录保留 | PASS |
| 原J5中心/BBox/面积/Feret/等级逐行一致 | PASS |
| K8E来源成员追溯逐行一致 | PASS |
| 两个批准组精确Mask | PASS |
| 批准组之间像素交叠 | 0 px² |
| 对全部J5显示BBox碰撞 | 0 |
| 其他K8E组保持待审 | PASS |
| 像元尺寸配置一致性 | **P2：脚本硬编码3.2** |
| G006额外微小碰撞来源记录 | **P2：Mask内含B640，但未单独登记** |
| 独立验证器精确集合断言 | P2：当前验证多处只检查数量，尚缺精确集合断言 |

## 2. 审查对象与版本

| 类型 | 文件 |
|---|---|
| K8F登记脚本 | `scripts/run_case03k8f_approved_supplements_ledger.py` |
| K8F独立验证 | `scripts/verify_case03k8f_approved_register.py` |
| K8F单元测试 | `tests/test_case03k8f_confirmed_register.py` |
| J5碰撞诊断脚本 | `scripts/diagnose_case03k8f_J5_overlap.py` |
| K8E输入 | `outputs/case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1` |
| J5输入 | `outputs/case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2` |
| K8F输出 | `outputs/case03k8f_confirmed_group_register/run_20261014_F26_2_two_user_approved_G006_G009_v2` |
| K8I下游 | `outputs/case03k8i_full_frame_lineage/run_20261015_sample26_2frames_fullcandidate_lineage_v1` |

K8F是人工确认登记/工作区复核清单生成模块，不是重新检测模块。它不修改原J5的`global_defects.csv`、正式ID、尺寸等级或源Mask，也不把新组写成原J5对象ID。


## 3. K8F代码执行顺序

### 3.1 人工批准白名单

脚本中硬编码的批准组仅为：
- `K8E_F2_B2_G006`：选中B标签626，嵌入B标签658，预期组面积348 px²；
- `K8E_F2_B2_G009`：选中B标签1148/1161，嵌入B标签1186，预期组面积370 px²。

仅第二帧允许这两个组进入批准登记；第一帧批准列表为空。白名单测试明确断言批准组ID和成员集合，不会把K8E中其他暂定中大组自动写为已确认。

### 3.2 读取K8E精确组Mask

`read_geometry()`读取K8E保存的`EXACT_GROUP_MASK.npz`，取得：
- 精确布尔外围Mask；
- 全局RAW ROI；
- K8D选中源B标签；
- 嵌入B标签；
- Mask内出现的全部B标签；
- 紧外接框、中心、面积和最大Feret。

随后重新计算面积、Feret和尺寸等级。批准组必须满足：
- K8E组存在且唯一；
- 面积与白名单预期值完全相等；
- selected/embedded B标签集合与白名单完全相等；
- 所有预期B标签均出现在外围Mask对应的B标签图中；
- 试验尺寸等级为LARGE；
- K8E状态为允许人工确认的`EMBEDDED_B_SOURCE_REVIEW`或`MUTUAL_CONTOUR_NEAR_IDENTICAL_REVIEW`。

### 3.3 J5全图BBox排重

K8F不是只检查J5 WORK中心点，而是将每个批准组的紧外接框与原J5全图分类表中的所有显示BBox比较，覆盖第二帧全部4,440条J5候选。

使用半开边界逻辑判断BBox相交。只要存在一个相交对象就抛出异常，禁止写入批准记录。

这比K8E的J5中心点检查更保守。当前G006/G009的碰撞数量均为0。

### 3.4 建立统一工作区候选复核清单

K8F把原J5 WORK候选与两处新增批准组放在一个独立CSV中：
- 原J5候选保留原`global_defect_id`、位置、BBox、面积、最大Feret和原尺寸等级；
- 新增组使用`supplement_K8E_group_id`，不分配原J5 ID；
- 所有记录另有`work_candidate_review_ID`作为当前复核清单的排序索引；
- 新增组标记`visual_defect_confirmed_by_user=True`；
- 原J5候选继续标记`EXISTING_J5_CANDIDATE_UNREVIEWED`；
- 全部记录标记非生产认证登记、物面尺寸未标定、源Mask未修改。

### 3.5 其他K8E组保留待审

K8F将未批准K8E组写入`other_K8E_groups_pending_manual_review.csv`，并标记：
- `manual_identity_and_full_outer_approved=False`；
- `not_added_to_unified_workband_register=True`。

同时导出全部K8E源成员追溯表，仅将G006/G009的五个成员标记为用户确认。

### 3.6 导出与无损验证

对G006/G009精确Mask另存PNG，并重新解码后逐像素比较K8E NPZ，确认导出没有改变二值像素。全帧显示图仅绘制轮廓，不填充区域；小候选仍保留独立参考图。

## 4. K8F实际输出

### 4.1 两帧工作区登记数量

| 项目 | 26_1 | 26_2 |
|---|---:|---:|
| 原J5 WORK候选 | 683 | 398 |
| 新增用户确认组 | 0 | 2 |
| 统一工作区复核清单行数 | 683 | 400 |
| 其他K8E组待人工确认 | 13 | 16 |
| 原J5 WORK中大候选 | 25 | 26 |
| 新增组与全部J5 BBox碰撞数 | 0 | 0 |

第一帧没有套用第二帧人工批准记录。第二帧只有G006和G009两组获得用户确认标记。

### 4.2 两处新增批准组的精确数据

| K8E组 | 选中B源 | 嵌入B源 | 面积 | 最大Feret | 尺寸等级 |
|---|---|---|---:|---:|---|
| G006 | 626 | 658 | 348 px² | 23.6008 px | LARGE |
| G009 | 1148、1161 | 1186 | 370 px² | 23.4094 px | LARGE |
| **合计** | 3个选中成员 | 2个嵌入成员 | **718 px²** | 不相加 | — |

按当前3.2 μm探测器像元计算：
- G006：面积像面当量3,563.52 μm²，最大Feret像面当量75.523 μm；
- G009：面积像面当量3,788.80 μm²，最大Feret像面当量74.910 μm；
- 合计面积像面当量7,352.32 μm²。

这些尺寸不是滤光片物面真实尺寸；K8F明确标记`physical_object_plane_size_calibrated=False`。

### 4.3 原J5逐行数据保持

本轮将K8F 683/398条原J5工作区记录与原始J5表逐行合并核对，以下字段全部一致：
- 原J5全局ID；
- 中心X/Y；
- BBox四边界；
- 面积；
- 最大Feret；
- 尺寸等级。

原J5中大候选仍分别为25/26个。K8F没有重算或覆盖J5源Mask，也没有将新的复核索引`WORK_F26_*`冒充原始J5正式ID。

### 4.4 来源追溯与待审清单

| 项目 | 26_1 | 26_2 |
|---|---:|---:|
| K8E源成员追溯行数 | 20 | 24 |
| K8F输出追溯行数 | 20 | 24 |
| 追溯核心字段逐行一致 | PASS | PASS |
| 标记用户确认的B源成员 | 0 | 5 |
| 待审K8E组ID集合与源K8E差集一致 | PASS | PASS |

第二帧确认成员为626、658、1148、1161、1186。其余16组未写入统一工作区登记。

### 4.5 两个批准组之间没有像素重叠

本轮将G006和G009的精确NPZ Mask重新放回全局RAW坐标，计算两者交集：

`intersection_px2 = 0`

因此718 px²是这两个批准组的全局唯一并集面积，不存在二者之间的重复计数。



## 5. 新发现：G006批准外围内还有一个未批准微小B源像素

### 5.1 实际像素证据

检查G006的`source_B_label_grid`与348 px²批准外围Mask：
- 外围内出现的B源标签为626、658、640；
- 白名单选中成员为626；
- 白名单嵌入成员为658；
- 额外标签640只有1 px²，位于G006外围内部。

进一步读取K8D候选626的`review_evidence_json`，发现K8D已明确记录：
- `microscopic_collisions=[640]`；
- B640完整源面积1 px²；
- B640的1 px²落入RAW外围；
- `micro_collision=True`；
- `eligible_same_spot_review=False`；
- `partial_competitor=False`。

K8F没有将640写入`source_B_connected_components`或`source_B_embedded_components`，这是正确的：B640不是用户确认的G006同一暗斑成员。

### 5.2 下游来源处置

K8I全帧来源表中B640仍为：
- `B_NOVEL_MICRO`；
- `MICRO_HIDE_SUGGESTION`；
- `K8E_group_ids`为空；
- `user_confirmation_state=PENDING_REVIEW`。

统一最终检测的源处置表中，B640被记录为`ALGORITHM_NOISE_SUGGEST_EXCLUDED_SOURCE_RETAINED`，没有被写成已人工确认噪声，原始源像素仍保留。

因此，B640没有作为一个独立成员被合并进K8F确认名单；但它的一个像素确实位于G006已确认外围Mask内部，属于外围几何范围内的微小碰撞像素。

### 5.3 诊断图

![G006已确认外围中626、658和额外微小碰撞B640的位置关系](outputs/K8F_MODULE_AUDIT_20261106/K8F_G006_extra_micro_collision_640_traceability.png)

### 5.4 P2问题：批准记录没有显式保存未纳入成员的微小碰撞列表

K8F的`read_geometry()`返回所有位于外围内的B标签，但审批断言只要求它是预期成员集合的超集。随后`newly_approved_record()`只写入selected和embedded标签，没有将额外微小碰撞列表写入批准记录。

当前K8D/K8I/统一最终检测已有证据保留B640的独立状态，因此本次没有发生源候选静默丢失或自动认定同一缺陷。但批准记录单独查看时，无法直接知道G006外围内还覆盖一个未批准的1 px²微小候选。

**建议：**
- 在K8F新增`source_B_micro_collisions_not_merged`字段，记录B640及其K8D证据；
- 验证器要求所有未列入selected/embedded的外围内B标签，都能在K8D证据中找到`micro_collision=True`或其他明确排除理由；
- 不将B640加入已批准成员集合，不改变G006面积348 px²，也不更改其用户确认状态。

## 6. 配置一致性与验证器覆盖问题

### K8F-02：像元尺寸3.2 μm在脚本中硬编码（P2）

当前工程配置：

`config/user_config.py: PIXEL_SIZE_UM = 3.2`

K8F脚本却使用：

`PITCH = 3.2`

当前两者相同，所以本次面积/长度像面当量计算正确。但如果用户以后在配置区把像元尺寸改为其他值，K8F登记输出仍会使用3.2，造成配置与报告尺寸不一致。

**建议：** 改为`PITCH = float(C.PIXEL_SIZE_UM)`，并将测试改为验证PITCH跟随配置，而不是固定断言3.2。

### K8F-03：独立验证器部分集合检查只验证数量（P2）

当前验证器对以下内容主要检查行数：
- 待审K8E组数量13/16；
- 已确认成员追溯行数5；
- 其他部分汇总行数。

本轮额外执行了集合级核对，确认：
- K8F导出的全部K8E来源成员行与K8E原追溯CSV核心字段逐行完全相同；
- 待审组ID集合恰好等于原K8E组ID减去G006/G009；
- 五个批准成员ID恰好为626、658、1148、1161、1186；
- 两个批准组之间Mask交集为0。

**建议：** 将这些本轮已完成的集合比较固化到`verify_case03k8f_approved_register.py`，不能只依赖数量相等。

### K8F-04：验证器没有检查批准组之间的像素交叠（P2）

当前G006/G009精确交集为0，但K8F独立验证器只分别验证每个组Mask与K8E原始Mask相同，没有检查两个新批准组互相是否交叠。

**建议：** 对全部新增批准Mask执行全局坐标两两交集检查；任何交集必须在审批记录中显式说明，不能直接把面积相加。

### K8F-05：两个字段语义可以更清晰（P3）

- `APPROVALS.expected_primary`当前未被使用；可删除或增加对应断言。
- `newly_approved_record()`对新增K8E补充组也设置`original_J5_grade_unchanged=True`，容易让人误解为新增组原本有J5等级。建议改成明确的`original_J5_records_unchanged=True`或将J5等级字段标记为不适用。



## 7. K8F下游调用关系

### 7.1 K8I来源追溯

K8I读取K8F`workband_unified_candidate_review_register.csv`，并校验：
- 第一帧批准组集合为空；
- 第二帧批准组集合恰好为G006/G009；
- 只有这两个组的五个B源成员路由到`B_K8E_GROUP_CONFIRMED`；
- 其他K8E组继续为`B_K8E_GROUP_PENDING`；
- 多组归属候选路由到`B_K8E_MULTIGROUP_CONFLICT`。

K8I不会仅凭K8E测量表的空人工确认字段推断用户批准，而是从K8F独立登记中读取批准状态。

### 7.2 统一最终检测

统一最终检测程序从K8F白名单读取G006/G009：
- 只对这两个组将K8E嵌入B成员加入已确认组来源集合；
- 其他K8E组不能因为K8E状态为STABLE就自动成为用户确认疵病；
- 原J5源对象与新K8E补充对象在最终像素合并中保持来源追溯；
- 最终对象仍标记探测器像面当量，未标记物面尺寸标定完成。

历史统一最终检测独立QA记录两帧最终对象39/35个、共74个，最终Mask两两不相交，四处用户确认暗斑的原始二值Mask保持精确。74个是算法输出对象数，不是真实疵病真值数量。

## 8. 测试结果与审查产物

### 8.1 测试

单独运行：

`pytest -q tests/test_case03k8f_confirmed_register.py`

结果：**5 passed**。

与K8E/K8I相关测试组合此前运行结果：**25 passed**。

历史独立验证状态：`K8F_INDEPENDENT_QA_PASS`。

本轮额外只读核查：
- 原J5 683/398行中心、BBox、面积、Feret和等级逐项一致；
- K8E/K8F来源追溯表核心字段逐行完全一致；
- 待审组ID集合精确等于K8E组ID减去批准白名单；
- 5个批准B源成员ID准确；
- G006/G009精确Mask交集为0；
- 全部J5显示BBox碰撞为0；
- G006内额外B640为K8D明确记录的1 px²微小碰撞，仍在K8I中保持未批准状态。

### 8.2 新增审查产物

目录：

`outputs/K8F_MODULE_AUDIT_20261106/`

新增：
- `K8F_G006_extra_micro_collision_640_traceability.png`
- `K8F_AUDIT_SUMMARY.json`

独立审查报告：

`K8F_MODULE_AUDIT_20261106.md`

总算法开发报告已追加第42节K8F专项审查摘要。

## 9. 最终处理决定

1. 保留当前仅批准G006/G009的白名单，不扩大用户确认范围。
2. 保留原J5全图数据、正式ID、源Mask和尺寸等级不变的原则。
3. 将G006中的B640微小碰撞作为未批准来源关系单独记录，不把它加入G006已确认成员，不改变348 px²批准外围。
4. 将像元尺寸改为读取`C.PIXEL_SIZE_UM`，避免未来配置变化时K8F输出仍写死3.2。
5. 将K8F验证器改为精确集合核对：K8E来源追溯行、批准成员ID、待审组ID、批准组之间的像素交集。
6. 保持`work_candidate_review_ID`仅作为工作区复核索引，不替换原J5正式ID。
7. 继续将K8F输出定义为独立统一工作区复核清单，不把它称为已认证生产缺陷登记表。
8. 继续将尺寸定义为探测器像面当量，物面尺寸仍需独立倍率标定。

**K8F最终结论：当前批准范围、原J5不可变性、几何排重和两组精确Mask均通过；没有发现误批准其他K8E组。需要补充G006内微小碰撞B640的来源说明，并修复像元尺寸硬编码及验证器集合检查不足。当前无P1阻断项。**

## 10. 图像证据

### 图10-1　26_2工作区中大候选与两处用户确认暗斑

![冻结J5中大候选与G006/G009用户确认外轮廓](outputs/case03k8f_confirmed_group_register/run_20261014_F26_2_two_user_approved_G006_G009_v2/frame26_2/02_MEDLARGE_plus_two_USER_CONFIRMED_DARKSPOTS.png)

### 图10-2　仅显示两处用户确认暗斑外轮廓

![G006/G009用户确认外轮廓独立图](outputs/case03k8f_confirmed_group_register/run_20261014_F26_2_two_user_approved_G006_G009_v2/frame26_2/03_ONLY_user_confirmed_darkspot_outlines.png)

### 图10-3　G006外围中的B640微小碰撞

![G006外围Mask包含一个未作为同一缺陷成员批准的1px B640微小碰撞](outputs/K8F_MODULE_AUDIT_20261106/K8F_G006_extra_micro_collision_640_traceability.png)

## 11. 本轮未执行

- 未修改K8F登记脚本或独立验证器；
- 未修改`APPROVALS`白名单；
- 未修改K8E G006/G009原始Mask；
- 未修改J5原始数据、正式ID或源Mask；
- 未修改K8I来源追溯和统一最终检测结果；
- 未新增任何用户批准组；
- 未将B640标记为已确认噪声或已确认疵病；
- 未生成物面尺寸、Precision/Recall或产品质量合格结论。

**K8F专项审查完成。** 下一模块按代码执行顺序进入K8G：显示框扩展、标注布局和中大/小疵病显示层，重点检查显示框是否改变真实Mask/尺寸、是否漏掉已确认补充组、不同图层是否重复或错误隐藏候选。
