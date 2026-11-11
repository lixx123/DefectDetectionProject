# K8D RAW外围稳定性与候选关联模块专项审查报告

**审查日期：** 2026-11-05  
**工程：** `D:\疵病检测\DefectDetectionProject`  
**审查范围：** K8D三档RAW外围选择、轮廓稳定性判断、B源候选关联证据、当前统一RAW入口的K8D接纳门控，以及20张RAW优先复核试验中的K8D执行范围。  
**审查方式：** 源码与调用链只读检查、26_1/26_2历史K8D输出复核、20张RAW K8DE优先复核结果统计、当前统一程序21条K8D试验逐条核查、合成边界测试。  
**源码修改：** 本轮未修改K8D源码、阈值、统一检测门限、原始RAW、历史Mask或最终检测结果。

## 1. 审查结论摘要

**K8D核心稳定性算法通过单元测试和历史像素级复现；但当前统一检测程序的额外8倍增长门限，会拒绝一部分K8D已经判定为稳定的RAW外围。另有一个SOURCE_ONLY状态与返回Mask不一致的问题。**

| 审查维度 | 结论 |
|---|---|
| K8D源码实现 | PASS |
| K8D源B候选像素保留 | PASS |
| 3/2/1.5 MAD稳定性选择逻辑 | PASS |
| 26_1/26_2历史32个候选像素级复现 | PASS |
| 20张RAW优先K8DE试验 | 20/20帧状态PASS，但不是完整生产检测验收 |
| K8D单元测试 | 11 passed |
| 当前统一程序的8倍增长门限 | **P1：拒绝6/14个稳定外围建议** |
| 40 px²初始候选门限 | 与K8C审查发现相同，进一步挡住小种子K8D修复 |
| SOURCE_ONLY_NO_MEANINGFUL_EXPANSION返回值 | P2：状态与Mask不一致 |
| K8D稳定外围是否等于真实疵病边界 | 否，仍需人工/独立真值验证 |

## 2. 审查对象与版本

| 类型 | 文件 |
|---|---|
| K8D核心算法 | `src/detection/case03k8d_group_stability.py` |
| K8D单元测试 | `tests/test_case03k8d_group_stability.py` |
| 双帧32候选执行脚本 | `scripts/run_case03k8d_grouped_raw_contours.py` |
| 双帧独立验证脚本 | `scripts/verify_case03k8d_real_masks.py` |
| 20张RAW K8DE优先试验 | `scripts/run_case03_frozen_K8DE_priority_all20.py` |
| 20张RAW独立验证 | `scripts/verify_case03_frozen_K8DE_priority_all20.py` |
| 当前统一RAW入口 | `scripts/run_unified_raw_input.py` |
| 当前统一参数 | `config/user_config.py` |

K8D核心算法SHA256：

`99b7af86ee586e8ed3795ef51767f3869b4a723b6551a673935ad77aafcafb45`

该值与冻结发布清单 `CASE03_FROZEN_RELEASE_20261019_v2/FROZEN_PIPELINE_AND_FILES_SHA256.json` 中 `03K8D_SEEDED_RAW_OUTER` 阶段登记值一致。

当前统一入口SHA256：

`dbd2154d8646f1750bf076a584f96a1c40fbc806a1a61f395a694c1899cccbf5`

## 3. K8D实际算法执行顺序

K8D不是新的候选生成器。它接收K8B已有的B源连通域和K3 RAW外围模块预先计算的3/2/1.5 MAD三档Mask，判断哪一档外围可以作为稳定的复核建议。

### 3.1 128×128局部RAW输入和源候选核验

每个B源候选以128×128 RAW ROI进行处理。K8D先核验：
- seed、WORK_CORE、B标签图和三档RAW Mask尺寸均为128×128；
- seed非空且完整位于WORK_CORE；
- seed内所有标签必须等于当前B源连通域ID；
- B源候选面积使用完整工作带连通域面积，而不是128×128裁剪片段面积。

任一条件不满足即拒绝进入正常外围恢复，避免用不完整ROI冒充完整候选。

### 3.2 严格3 MAD源锚

先检查3 MAD严格外围：
- 3 MAD Mask面积必须非零；
- 3 MAD与原始seed的重叠比例至少60%。

若不满足，返回原始seed，状态为：

`SOURCE_ONLY_UNRELIABLE_3MAD`

**即使2 MAD或1.5 MAD突然出现很大的Mask，也不允许绕过3 MAD源锚直接接受大外围。**

### 3.3 严格外围安全检查

若3 MAD源锚有效，仍需检查：
- 3 MAD面积是否超过2,000 px²；
- 是否越出WORK_CORE；
- 是否触及128×128 ROI边界；
- 是否触及RAW外围计算半径上限；
- PCA形状紧致度对应的长短轴比是否超过2.8。

触发任一条件时，返回完整3 MAD外围与原seed的并集，标记：

`CENSORED_FULL_OUTER_REVIEW`

这类完整外围只供复核，不是稳定外围，也不能作为最终疵病边界。

### 3.4 3→2→1.5 MAD逐级放宽

严格3 MAD通过后，依次检查：
- 3→2 MAD面积增长比例不超过1.35；
- 2→1.5 MAD面积增长比例不超过1.25；
- 每次放宽的边界非嵌套损失不超过7%；
- 新Mask不超过2,000 px²；
- 形状长短轴比不超过2.8；
- seed支持比例不低于60%；
- 不越出WORK_CORE；
- 不触及ROI边界或RAW计算半径上限。

任一级失败即停止继续放宽，保留上一级通过的外围。K8D因此不是无条件选取最宽松的1.5 MAD。

### 3.5 多源候选关联证据

对选定RAW外围覆盖到的其他B连通域，使用其完整工作带面积计算覆盖比例：
- 完整覆盖比例至少80%、面积至少3 px²：列为同一暗斑的候选关联成员；
- 面积小于3 px²：列为微小碰撞，不作为独立关联成员；
- 非完整覆盖且重叠像素超过3或重叠比例超过10%：列为部分竞争候选；
- 可关联兄弟候选超过8个：触发过多成员风险。

K8D只记录成员证据和复核分组，不自动合并正式疵病ID。

### 3.6 状态输出

| 状态 | 含义 |
|---|---|
| STABLE_SINGLE_OUTER_REVIEW | 单个B源候选的RAW外围通过稳定性检查 |
| STABLE_GROUP_OUTER_REVIEW | RAW外围包含其他B源候选，形成同一暗斑的关联复核假设 |
| AMBIGUOUS_FULL_OUTER_REVIEW | 存在部分竞争候选或成员过多，保留完整外围供复核 |
| CENSORED_FULL_OUTER_REVIEW | 外围越界、触边、超面积或形状不安全，完整外围仅供复核 |
| SOURCE_ONLY_UNRELIABLE_3MAD | 3 MAD没有可靠源锚，只保留原始seed |
| SOURCE_ONLY_NO_MEANINGFUL_EXPANSION | 扩张不足12%，按语义应只保留原始seed |

以上状态均不是“真实疵病确认”。STABLE表示RAW外围在当前启发式约束下稳定，不代表已经获得物面真实边界或物理缺陷ID。

## 4. K8D关键参数

| 参数 | 当前值 | 作用 |
|---|---:|---|
| 3 MAD seed重叠比例下限 | 0.60 | 严格源锚 |
| 最大外围面积 | 2,000 px² | 绝对面积安全上限 |
| 3→2 MAD面积增长上限 | 1.35 | 第一档稳定性 |
| 2→1.5 MAD面积增长上限 | 1.25 | 第二档稳定性 |
| 边界非嵌套损失上限 | 0.07 | 防止外围跳变 |
| PCA紧致度长短轴比上限 | 2.8 | 排除极端细长/不稳定外围 |
| 同一成员完整覆盖比例 | 0.80 | 候选关联 |
| 最大关联成员数 | 8 | 过多成员保护 |
| 关联微小分量面积阈值 | 3 px² | 1–2 px²仅记微小碰撞 |
| 部分竞争像素阈值 | 3 px² | 部分重叠判断 |
| 部分竞争比例阈值 | 0.10 | 部分重叠判断 |
| 最小有效扩张比例 | 1.12 | 低于12%按source-only处理 |

注意：K8D本身没有把“外围面积/seed面积不得超过5倍”作为拒绝规则。该设计是为避免此前过度保守的5倍回退导致完整暗斑仍只剩很小种子。

## 5. 26_1/26_2真实RAW双帧复核

K8D v3使用历史保存的K8C 3/2/1.5 MAD Mask，并重新执行RAW外围计算进行逐像素复核。只处理此前优先筛选的32个候选，不代表对两帧全部B候选执行了K8D。

| 指标 | 26_1 | 26_2 |
|---|---:|---:|
| K8D处理候选 | 13 | 19 |
| 外围得到扩展 | 10 | 11 |
| 稳定中大外围显示建议 | 7 | 9 |
| 完整外围复核显示组 | 3 | 1 |
| 原J5 WORK中大对象 | 25 | 26 |
| 原B/J5源像素是否修改 | 否 | 否 |
| 正式ID是否自动合并 | 否 | 否 |

上述“稳定中大外围”和“完整外围复核”是显示级分组统计，不是独立真实疵病数。

### 5.1 四个关键回归案例

| 对象 | 原始seed | 3/2/1.5 MAD面积 | K8D结果 | 状态 |
|---|---:|---:|---:|---|
| F2-B2-C1148 | 48 | 317/353/369 | 369 | STABLE_GROUP |
| F2-B2-C1161 | 64 | 314/353/370 | 370 | STABLE_GROUP |
| F2-B2-C626 | 34 | 273/323/348 | 348 | STABLE_GROUP |
| F2-B2-C1483 | 12 | 0/0/1746 | 12 | SOURCE_ONLY_UNRELIABLE_3MAD |

C1148与C1161的外围相互包含多个B源种子，属于同一暗斑的关联假设；C626外围包含C658。K8D没有自动合并正式ID。

C1483是重要反例：尽管1.5 MAD产生1,746 px²的大Mask，但3 MAD无可靠源锚，因此仍只保留12 px²原始seed，防止大面积背景/遮光带被误吸收。

### 5.2 K8D独立像素级QA

既有 `independent_QA.json` 状态为 `K8D_REAL_PIXEL_EXACT_QA_PASS`：
- 32个候选的原B源Mask与先前K8C存档完全一致；
- 3/2/1.5 MAD Mask与历史保存的RAW外围结果逐像素一致；
- 所有返回外围均包含完整原始seed；
- 稳定外围不越出WORK_CORE；
- 1148、1161、626、1483四个重点回归案例完成专项核查；
- 原始J5/K5/B数据未修改；
- 人工外围确认字段仍为空，物面真实边界仍待人工/独立真值验证。

本轮重新运行：

`pytest -q tests/test_case03k8d_group_stability.py`

结果：**11 passed**。

## 6. 20张RAW K8DE优先复核试验

历史 `CASE03_FROZEN_K8DE_PRIORITY_ALL20_20261019_v1` 的独立QA记录：
- 20/20帧状态PASS；
- 317,673个原始B源候选均纳入源标签审计；
- K8D RAW外围试验总数4,643；
- K8E像素级复核组4,546；
- 新物理疵病自动批准数0；
- 所有微小候选未执行K8D RAW扩张，但仍保留；
- J5/B生产级跨通道去重尚未完成。

这里的4,546是K8E精确像素并集的复核组数，不是真实疵病数量。

### 6.1 20张RAW并非全部重新运行

- 26_1：131条RAW试验，使用既有K8I2冻结结果，不在该脚本中重跑；
- 26_2：5条RAW试验，使用既有K8I2冻结结果，不在该脚本中重跑；
- 其余18帧：本次K8DE脚本实际执行K8D/K8E优先复核。

因此“20/20 PASS”表示20帧均有可审计的阶段结果，不表示20帧全部重新执行K8D，也不表示完整疵病检测验收通过。

### 6.2 18张新RAW的K8D状态

18张新RAW共4,507条K8D RAW试验：

| K8D状态 | 数量 |
|---|---:|
| SOURCE_ONLY_UNRELIABLE_3MAD | 4,019 |
| STABLE_SINGLE_OUTER_REVIEW | 208 |
| STABLE_GROUP_OUTER_REVIEW | 170 |
| CENSORED_FULL_OUTER_REVIEW | 68 |
| AMBIGUOUS_FULL_OUTER_REVIEW | 33 |
| SOURCE_ONLY_NO_MEANINGFUL_EXPANSION | 9 |
| **合计** | **4,507** |

4,019条严格3 MAD无可靠源锚的候选只保留原始seed，不允许1.5 MAD巨大外围抢占。所有未进入RAW试验的B源候选仍保留在 `ALL_ORIGINAL_B_DISPOSITION.csv` 中。

### 6.3 20张RAW优先试验与当前统一入口的候选范围不同

20张RAW优先试验采用：

`ENABLED_CLASSES = PROMISING_DARK_REVIEW, UNCERTAIN_REVIEW, BOUNDARY_REVIEW`

即边界候选也进入K8D复核；1–2 px²和3–7 px²微小候选不扩张，但继续归档。

当前统一入口的规则不同：它只接受PROMISING/UNCERTAIN，且还要求B源面积至少40 px²；BOUNDARY_REVIEW不进入当前统一K8D路径。二者不能混为同一套候选选择策略。

## 7. 当前统一RAW入口中的K8D实际接纳情况

当前 `scripts/run_unified_raw_input.py` 调用K8D后，还执行：

`reason.startswith('STABLE_') and outer.sum() <= max_raw_growth_ratio * source_area`

配置文件 `config/user_config.py` 当前设置：

`max_raw_growth_ratio = 8.0`

因此，K8D内部判定为STABLE的外围，还要再次通过8倍面积增长限制才能替代原始seed。

### 7.1 当前26_1/26_2实际结果

| 指标 | 26_1 | 26_2 |
|---|---:|---:|
| 当前统一入口K8D试验 | 12 | 9 |
| K8D内部STABLE状态 | 7 | 7 |
| 被8倍门限接纳 | 2 | 6 |
| 被8倍门限拒绝 | **5** | **1** |

合计14个稳定外围建议中，6个被统一入口额外8倍门限拒绝，最终回退到原始seed。

### 7.2 被8倍门限拒绝的六个稳定外围

| 对象 | 原seed | K8D稳定外围 | 增长比例 |
|---|---:|---:|---:|
| F1-B3-C0739 | 60 | 1,806 | 30.10× |
| F1-B3-C1837 | 59 | 1,214 | 20.58× |
| F1-B3-C1908 | 55 | 1,872 | 34.04× |
| F1-B3-C3015 | 172 | 1,805 | 10.49× |
| F1-B4-C4577 | 112 | 1,452 | 12.96× |
| F2-B4-C0075 | 47 | 984 | 20.94× |

这些外围均已通过K8D自身的3/2/1.5 MAD稳定性、种子支持、嵌套、WORK_CORE、形状和绝对面积等检查；其中外围面积仍小于2,000 px²。统一入口却因额外8倍比例限制拒绝它们。

这与K8D原始设计“不再因相对seed增长超过5倍就硬回退”的目标存在直接冲突。

**P1：K8D稳定外围没有完整进入统一检测结果。**

**建议：** 不应在没有真实疵病真值支持的情况下，用8倍比例再次覆盖K8D的稳定性判断。建议后续将其改为明确的复核状态，或评估是否取消该额外硬门限；如仍保留，必须给出与已确认暗斑相符的边界依据。当前不直接修改参数。

### 7.3 40 px²门限再次挡住K8D回归案例

K8D v3成功恢复的F2-B2-C626为34 px² seed，K8D外围348 px²，增长10.24倍。当前统一入口的40 px²初始面积门限会在调用K8D之前就排除该候选；即使放宽40 px²门限，后续8倍门限仍会拒绝其10.24倍外围。

因此K8D独立回归修复并没有完整集成到当前统一RAW生产路径。该问题与K8C审查的40 px² P1问题相互叠加。

## 8. 代码问题与改进建议

### K8D-01：统一入口8倍增长门限覆盖K8D稳定结果（P1）

已核查6/14个当前统一入口的稳定外围被额外8倍门限拒绝。K8D本身已有2,000 px²绝对面积、逐级增长、嵌套、形状、工作区和seed支持等安全条件。

**建议：** 后续单独评估8倍门限；不能仅因相对seed增长大就静默回退。至少应保留稳定外围并标记增长较大待复核。

### K8D-02：SOURCE_ONLY_NO_MEANINGFUL_EXPANSION状态与返回Mask不一致（P2）

当前源码在面积增长低于12%时设置：

`status = SOURCE_ONLY_NO_MEANINGFUL_EXPANSION`

但函数最后仍返回：

`proposed = selected_raw_mask | seed`

没有在该分支返回 `seed.copy()`。

本轮用100 px² seed加1个外围像素进行合成验证，实际得到：
- 状态：SOURCE_ONLY_NO_MEANINGFUL_EXPANSION；
- 原始seed：100 px²；
- 返回Mask：101 px²；
- 新增像素：1 px²。

20张RAW的18张新帧中共有9条该状态，其中8条返回Mask面积大于原seed，例如375→414、382→412、400→435、583→643 px²。

20张RAW K8DE脚本将所有RAW试验Mask加入后续K8E分组，因此这8条虽标记为source-only，仍可能以略微扩张的Mask参与复核组并集。它们不会自动变成物理疵病，但状态语义不一致。

**建议：** 当扩张比例低于12%时，应明确返回 `seed.copy()`，并增加单元测试。20RAW独立验证目前检查了SOURCE_ONLY_UNRELIABLE_3MAD的seed等值，但没有检查SOURCE_ONLY_NO_MEANINGFUL_EXPANSION。

### K8D-03：三条执行路径的候选选择规则不一致（P1/P2）

| 执行路径 | K8D输入候选范围 |
|---|---|
| K8D双帧v3独立试验 | 32个优先候选 |
| 20张RAW K8DE优先试验 | PROMISING、UNCERTAIN、BOUNDARY；共4,643条RAW试验 |
| 当前统一RAW入口 | PROMISING、UNCERTAIN且seed面积≥40 px² |

因此，K8D独立试验和20RAW优先试验的结果不能直接代表当前统一入口的实际检测能力。尤其是边界候选和小面积seed在统一入口中没有进入K8D。

**建议：** 后续统一候选选择策略，并在验收报告中明确“候选总数、进入K8D数量、被K8D拒绝/保留seed数量、最终采用外围数量”。

### K8D-04：非稳定完整外围必须保持复核语义（P2，使用约束）

CENSORED和AMBIGUOUS状态可能返回完整外围，且可能包含WORK_CORE外像素。20RAW独立验证只要求STABLE外围严格位于WORK_CORE内，对CENSORED/AMBIGUOUS保留完整复核Mask。

这符合“展示完整问题区域供复核”的设计，但不能直接把这些外围作为最终疵病轮廓或正式尺寸统计。当前统一入口只将STABLE外围作为候选扩展来源，非稳定状态保留seed；20RAW K8DE输出则是复核组，不是生产缺陷结果。

### K8D-05：K8D面积和长度仍是探测器像面当量

当前使用3.2 μm像元换算面积和长度。K8D输出字段明确记录 `physical_object_plane_calibration_confirmed=False`。因此这些值只能称为探测器像面等效尺寸，不应在没有物面标定时直接称为滤光片物面真实尺寸。

## 9. 最终处理决定

1. 保留K8D现有3/2/1.5 MAD逐级稳定性算法，不在本轮修改源码。
2. 将统一入口8倍增长门限列为P1，后续单独制定修订方案；在解决前，不应宣称K8D独立稳定外围已完整进入统一检测结果。
3. 将40 px²上游门限作为K8C/K8D共同P1问题处理；尤其不能忽略34 px²的C626回归案例。
4. 修复SOURCE_ONLY_NO_MEANINGFUL_EXPANSION返回值与状态不一致，并增加单元测试。
5. 统一K8D独立试验、20RAW优先试验和统一RAW入口的候选选择规则。
6. 保持CENSORED/AMBIGUOUS为复核结果，不自动计入正式疵病或物理尺寸统计。
7. 不自动合并K8D/K8E复核组的正式疵病ID；仍需独立人工/真值确认。

**K8D最终结论：核心算法和历史数据复现通过；当前统一检测入口的额外8倍面积增长门限会拒绝部分K8D稳定外围，40 px²上游门限也挡住部分小种子回归案例。K8D尚不能视为已完整集成到当前统一RAW生产路径。**

## 10. 本轮未执行的操作

- 未修改K8D算法源码；
- 未修改 `max_raw_growth_ratio=8.0`；
- 未修改 `min_b_source_area_px2=40`；
- 未修改K8E分组规则或K8F/G/I显示规则；
- 未修改原始RAW、历史K8B/J5 Mask、用户确认记录和正式缺陷ID；
- 未重新运行20张RAW完整检测；
- 仅执行只读审查、K8D单元测试、合成行为验证及新增审查图像生成。


## 11. 图像证据与结果图册

本节将K8D历史真实RAW输出与本轮新增的统一入口门限诊断图插入报告。K8D外围均为复核建议，不是已经确认的物理疵病边界。

### 图11-1　当前统一入口8倍门限拒绝的六个K8D稳定外围

![黄色为原始B seed像素，青色为K8D稳定RAW外围；统一入口因增长超过8倍而未采用这些外围](outputs/K8D_MODULE_AUDIT_20261105/K8D_unified_8x_gate_rejected_stable_outer_examples.png)

**图像结论：** 六个对象均被K8D标记为STABLE，但统一入口的8倍增长门限将其拒绝。图像显示这些RAW局部具有明显暗核，说明8倍门限对K8D稳定结果的覆盖影响需要单独验证。

### 图11-2　26_2四个关键对象旧结果与K8D结果对比

![1148、1161、626和1483四个关键对象的RAW、原始seed、旧结果和K8D结果](outputs/case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3/frame26_2/K8D_REGRESSION_4TARGET_OLD_VS_NEW.png)

**图像结论：** 1148、1161、626的外围得到扩展；1483虽然1.5 MAD出现大面积响应，但由于3 MAD没有可靠源锚，仍保留12 px²原始seed。这张图同时展示了K8D的扩展能力和防止大面积误扩张的保护机制。

### 图11-3　F2-B2-C1148：48 px²源候选至369 px²外围

![C1148原始RAW、B源、三档MAD和K8D外围](outputs/case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3/frame26_2/band02/F2_B2_C01148_K8D_six_panel.png)

**图像结论：** 48 px²源候选经3/2/1.5 MAD稳定性检查后得到369 px²复核外围，状态为STABLE_GROUP_OUTER_REVIEW。该外围还包含其他B源成员的关联证据，但不自动合并正式ID。

### 图11-4　F2-B2-C626：34 px²源候选至348 px²外围

![C626原始RAW、34 px² B源、三档MAD和348 px² K8D外围](outputs/case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3/frame26_2/band02/F2_B2_C00626_K8D_six_panel.png)

**图像结论：** 该案例是K8D修复小种子回退问题的重要回归对象。它也说明当前统一入口40 px²门限会在K8D执行之前排除该候选。

### 图11-5　26_2原J5中大对象与K8D稳定外围建议

![原J5工作区中大对象和K8D稳定外围建议联合显示](outputs/case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3/frame26_2/02_J5_MED_LARGE_plus_STABLE_K8D.png)

**图像结论：** 该图展示原J5工作区中大对象与K8D稳定外围建议的空间关系。K8D建议仍是待确认补充结果，不能直接与J5对象数量相加作为真实疵病数。

### 图11-6　26_2完整外围待复核案例

![K8D完整外围待复核图，不回退为极小seed](outputs/case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3/frame26_2/04_AMBIGUOUS_NO_SHRINK_OUTERS.png)

**图像结论：** 对不满足稳定条件的完整外围，K8D保留橙色复核区域，而不是把完整RAW证据缩回极小seed。此类Mask仍是复核证据，不得直接作为最终疵病边界。

### 图11-7　20张RAW中的K8DE优先复核显示示例（30_4）

![30_4样本K8DE优先复核1至8倍显示图](outputs/CASE03_FROZEN_K8DE_PRIORITY_ALL20_20261019_v1/30_4/K8DE_ALL_PRIORITY_REVIEW_1to8.png)

**图像结论：** 该图展示20张RAW优先复核阶段中一个新样本的候选分布。它只显示K8C优先类别对应的K8D/K8E复核候选，不包含全部微小候选，也不是最终生产缺陷标注图。

## 12. 审查产物

本轮新增诊断图目录：

`outputs/K8D_MODULE_AUDIT_20261105/`

新增图像：
- `K8D_unified_8x_gate_rejected_stable_outer_examples.png`

独立审查报告：

`K8D_MODULE_AUDIT_20261105.md`

总算法开发报告应追加K8D专项审查摘要及关键图像引用。历史K8D v3、K8DE 20RAW输出目录保持只读，不覆盖。
