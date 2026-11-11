# K8C候选分类与噪声筛选模块专项审查报告

**审查日期：** 2026-11-05  
**工程：** `D:\疵病检测\DefectDetectionProject`  
**审查范围：** K8C候选级RAW证据分类、噪声建议、候选源保留、统一检测程序中的K8C调用及其下游门控。  
**审查方式：** 只读源码检查、历史输出复核、当前26_1/26_2结果逐候选对照、20张RAW统计核查、单元测试。  
**源码修改：** 本轮未修改任何算法源码、阈值、原始RAW、历史候选Mask或最终检测结果。

## 1. 审查结论摘要

**审查结论：实现与复现通过；生产门控存在高优先级召回风险。**

| 审查维度 | 结论 |
|---|---|
| K8C分类逻辑与参数实现 | PASS |
| RAW局部对比度、MAD、DoG和工作区边缘判断 | PASS |
| 26_1/26_2候选逐项复现 | PASS，分类、面积、A重叠像素均完全一致 |
| K8C三类归档Mask无损分区 | PASS，历史独立QA通过 |
| 20张RAW前段候选分类稳定性 | PASS，20/20完成K8A/B/C筛查 |
| 人工标签是否参与K8C打分 | 未参与；第二帧12个用户观察样本仅在评分后回查 |
| 新RAW下游面积门限 | **P1：40 px²硬门限可能排除已确认暗斑的初始种子** |
| A固定阈值重叠分类 | P2：任意像素重叠即归为EXISTING_FIXED_H，未单独评估B新增扩展部分 |
| K8C是否为真值分类器 | 否；无独立盲测真值，不能报告Precision/Recall |

**总体判断：K8C模块本身实现了可逆分类和源候选完整保留，软件测试及历史结果复现通过。但当前统一检测程序在K8C之后设置的40 px²面积门限，与已确认暗斑中存在的小面积初始种子不一致。对新RAW而言，这一门限可能使部分真实暗斑无法进入K8D后续处理。K8C可以保留作为候选证据分类层，但当前下游门控不宜直接认定已满足高召回要求。**

## 2. 审查对象与版本

| 类型 | 文件 |
|---|---|
| 核心算法 | `src/detection/case03k8c_noise_review.py` |
| 单元测试 | `tests/test_case03k8c_noise_review.py` |
| 双帧全带试验脚本 | `scripts/run_case03k8c_band_supplement_review.py` |
| 20张RAW前段筛查脚本 | `scripts/run_case03frozen_all20_robustness.py` |
| 当前统一RAW入口 | `scripts/run_unified_raw_input.py` |
| 历史K8C双帧输出 | `outputs/case03k8c_band_supplement_review/run_20261013_f1_f2_allbands_reversible_v2` |
| 20张RAW K8A/B/C输出 | `outputs/CASE03_FROZEN_ROBUSTNESS_20RAW_20261019_v3` |

核心算法SHA256：

`src/detection/case03k8c_noise_review.py`

`5e49dbf38d39e2ce27d2fd15fb94e19a295a2367f28c427b88b7220d91b88e60`

该SHA256与冻结发布清单 `CASE03_FROZEN_RELEASE_20261019_v2/FROZEN_PIPELINE_AND_FILES_SHA256.json` 中的 `03K8C_NOISE_TRIAGE` 阶段登记值一致。

当前统一入口SHA256：

`scripts/run_unified_raw_input.py`

`dbd2154d8646f1750bf076a584f96a1c40fbc806a1a61f395a694c1899cccbf5`

## 3. K8C算法实际执行顺序

### 3.1 输入

每个工作带输入四项数据：

1. 原始RAW局部图像，数据类型为uint16；
2. K8B的B分支二值候选Mask；
3. A分支固定170/230 DN候选Mask，用于识别与固定阈值分支重叠的对象；
4. K8A提供的WORK_CORE工作区掩膜。

K8C只在K8A工作区内处理B候选。输入形状必须一致；B候选不能越出WORK_CORE；A候选按函数接口要求必须包含于B候选。

### 3.2 连通域标记

对B候选Mask执行8连通域标记。每个连通域独立计算：
- 候选面积；
- 局部中心坐标；
- 外接矩形宽、高；
- A固定阈值重叠像素数；
- RAW局部背景统计特征。

K8C的分类单位是B候选连通域，不是最终物理疵病对象。多个候选之后仍可能由K8D或其他关联模块合并。

### 3.3 RAW局部背景环带

对面积大于2 px²的候选，围绕实际候选形状构造局部背景环带：
- 内侧膨胀半径：6 px；
- 外侧膨胀半径：24 px；
- 环带只使用WORK_CORE内像素；
- 排除候选本身、其他全部B候选像素及非工作区像素；
- 有效背景像素至少70个，否则标记为统计证据不足。

该设计避免把附近其他暗候选或非工作区灰度混入局部背景参考。

### 3.4 RAW对比度与MAD统计

设候选RAW中位数为 (D_o)，局部环带背景中位数为 (D_b)：

[
\Delta D = D_b-D_o
]

[
R_d = \frac{D_b-D_o}{\max(D_b,1)}
]

[
\sigma_{MAD}=\max(3,1.4826\times MAD)
]

[
Z_{MAD}=\frac{D_b-D_o}{\sigma_{MAD}}
]

其中3 DN为噪声尺度下限。这里的MAD是局部环带RAW灰度的稳健离散尺度，不是通过独立噪声标定得到的探测器噪声标准差。

### 3.5 DoG暗核特征

分别计算RAW局部图像的高斯平滑结果：
- 小尺度：sigma=2 px；
- 大尺度：sigma=8 px。

使用：

[
DoG=G_{8}(RAW)-G_{2}(RAW)
]

统计候选像素内DoG的中位数和P90。DoG只用于判断已有B候选是否具有暗核结构，**不会单独生成新候选**。

### 3.6 工作区边缘距离

计算候选到WORK_CORE边缘的最小距离。小于32 px时，归类为边界复核，不直接判为噪声。该32 px是K8C的风险分层参数，不改变K8A工作区本身的几何边界。

## 4. K8C关键参数

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `min_promising_area_px` | 8 px² | 优先暗斑候选的最小面积 |
| `micro_suggest_hide_max_area_px` | 2 px² | 1–2 px²建议隐藏 |
| 局部环带内半径 | 6 px | 排除候选附近过近像素 |
| 局部环带外半径 | 24 px | 限定局部背景参考范围 |
| 最小有效背景像素 | 70 | 环带有效性要求 |
| RAW相对暗度下限 | 0.07 | 相对局部背景至少暗7% |
| MAD显著性下限 | 2.0 | RAW暗度显著性条件 |
| DoG P90下限 | 3 DN | 暗核结构支持条件 |
| 工作区边缘复核距离 | 32 px | 边界风险分层 |
| 最大局部特征宽/高 | 360 px | 超大对象转人工复核 |
| MAD尺度下限 | 3 DN | 防止局部MAD过小 |
| 像元尺寸记录 | 3.2 μm | 仅用于探测器等效面积换算 |
| DoG小/大sigma | 2 / 8 px | 暗核结构评价 |

这些阈值是26号数据上的探索性分类参数，不是独立盲测优化得到的生产验收阈值。

## 5. 分类优先级与实际含义

分类顺序非常重要，代码按以下顺序执行：

1. **EXISTING_FIXED_H**：B连通域只要与A固定170/230候选有至少1个像素重叠，就归入该类；不再计算该对象的RAW环带、MAD和DoG分类。
2. **MICRO_HIDE_SUGGESTION**：与A无重叠且面积为1–2 px²。只建议在主图隐藏，源候选仍归档。
3. **BOUNDARY_REVIEW**：候选到WORK_CORE边缘距离小于32 px。边界风险复核，不判噪声。
4. **UNCERTAIN_REVIEW**：局部背景环带无效、对象过大，或RAW暗斑证据不满足优先候选条件。
5. **MICRO_REVIEW**：面积3–7 px²，不判为噪声，不自动删除。
6. **PROMISING_DARK_REVIEW**：面积至少8 px²、背景环带有效、相对暗度至少7%、MAD显著性至少2、DoG P90至少3 DN，且不处于边缘复核区。

**分类标签表达的是复核优先级和证据状态，不是真实疵病/噪声的物理标签。** 特别是：
- `MICRO_HIDE_SUGGESTION`不等于确认噪声；
- `EXISTING_FIXED_H`只表示与固定A分支有像素重叠，不等于已经被J5正式检出；
- `PROMISING_DARK_REVIEW`也不等于已经确认是真疵病。

## 6. 候选源保留机制

`evaluate_binary_band()`返回三个互斥的像素级归档Mask：
- promising；
- review（包含固定A重叠、边界、微小复核及证据不足）；
- micro hide suggestion。

函数末尾执行：
- 三类Mask两两互斥；
- 三类Mask并集必须严格等于输入B Mask；
- 不修改RAW、A Mask、B Mask和WORK_CORE输入数组。

因此K8C本身不会删除B源像素。每个候选还保留连通域标签、面积、全局坐标、分类理由和RAW证据字段。


## 7. 26_1/26_2实际结果与逐候选复现

### 7.1 K8C分类数量

| 分类 | 26_1 | 26_2 |
|---|---:|---:|
| EXISTING_FIXED_H | 3,008 | 528 |
| BOUNDARY_REVIEW | 20 | 6 |
| MICRO_HIDE_SUGGESTION | 11,524 | 3,168 |
| MICRO_REVIEW | 2,086 | 173 |
| PROMISING_DARK_REVIEW | 13 | 13 |
| UNCERTAIN_REVIEW | 115 | 4 |
| **B候选总数** | **16,766** | **3,892** |

26_1中A固定分支原始连通域为3,009个，而与A发生像素重叠的B连通域为3,008个。原因是B阈值降低后，少数A连通域在B分支中发生合并；不能按对象数量一一对应，但像素级A包含关系通过核查。

### 7.2 历史K8C与当前统一工程逐候选对照

将当前统一检测输出中的K8B候选记录，与历史K8C完整候选审计CSV按 `band_id + band_component_label` 逐项连接：

| 项目 | 26_1 | 26_2 |
|---|---:|---:|
| 历史候选记录 | 16,766 | 3,892 |
| 当前候选记录 | 16,766 | 3,892 |
| 分类不一致 | 0 | 0 |
| 候选面积不一致 | 0 | 0 |
| A重叠像素数不一致 | 0 | 0 |
| 当前源UID重复 | 0 | 0 |

当前统一输出的K8B候选记录均保留 `original_source_preserved=True`。这证明当前源码对两帧K8C分类结果实现了逐候选复现，而不只是总数相同。

### 7.3 历史独立QA

既有 `independent_QA.json` 的结果为 `CASE03_K8C_FULL_QA_PASS`：
- 两帧全部4个工作带均处理；
- 每帧12张原分辨率二值分类Mask通过检查；
- 每带三类Mask互斥，三类并集严格等于B源Mask；
- 每帧38张PNG预览成功解码；
- 原J5工作区中心候选数保持26_1为683、26_2为398；
- 第二帧12个用户观察样本没有任何一个被分到1–2 px²建议隐藏类；
- 未将这些结果宣称为真实Precision/Recall。

本轮重新运行K8B和K8C相关单元测试：

`pytest -q tests/test_case03k8b_perband_trial.py tests/test_case03k8c_noise_review.py`

结果：**18 passed**。

## 8. 20张RAW的K8C分类稳定性

20张RAW、80个“帧×工作带”组合的K8A/B/C前段筛查记录显示：
- 20/20帧完成前段筛查；
- B源候选连通域总数317,673；
- 每个工作带的B源像素均被K8C分类Mask完整覆盖；
- `A_fixed_pixels_not_selected_by_B_adaptive`总数为0，80个工作带均为0；
- K8C分类总数与B源候选总数一致。

| K8C类别 | 20张RAW候选数 |
|---|---:|
| EXISTING_FIXED_H | 51,997 |
| BOUNDARY_REVIEW | 272 |
| MICRO_HIDE_SUGGESTION | 211,349 |
| MICRO_REVIEW | 49,649 |
| PROMISING_DARK_REVIEW | 287 |
| UNCERTAIN_REVIEW | 4,119 |
| **总计** | **317,673** |

这里的211,349个MICRO_HIDE_SUGGESTION只是1–2 px²面积规则产生的显示隐藏建议，不代表211,349个真实噪声点；287个PROMISING_DARK_REVIEW也不是287个已确认疵病。

**范围限制：** 该20张RAW试验只完成K8A/K8B/K8C前段筛查。历史汇总明确记录 `full_J4_J5_all20_pipeline_completed=false`，K8D/K8E全20张端到端流程也未完成。因此不得将20/20解释为完整疵病检测算法验收通过。

## 9. 当前统一检测程序中的K8C下游门控

这是本次审查最重要的发现。

### 9.1 当前实际调用

`scripts/run_unified_raw_input.py` 的 `fresh_b()` 实际调用：

`evaluate_binary_band(r, b, a & b, core, noise)`

因此K8C已经进入当前统一RAW检测链，不是只存在于独立试验脚本中。

随后程序执行以下门控：

`if area < C.UNIFIED_FINAL['min_b_source_area_px2'] or classification not in ('PROMISING_DARK_REVIEW', 'UNCERTAIN_REVIEW'): continue`

当前 `config/user_config.py` 中：

`min_b_source_area_px2 = 40`

也就是说，K8C分类为PROMISING或UNCERTAIN仍不够，候选连通域还必须达到40 px²，才会进入后续K8D RAW外围处理。其他分类留在源候选记录中，但不进入B补充检测对象。

### 9.2 当前26_1/26_2实际通过面积门限的数量

| 项目 | 26_1 | 26_2 |
|---|---:|---:|
| K8B全部候选 | 16,766 | 3,892 |
| PROMISING且面积≥40 px² | 9 | 9 |
| UNCERTAIN且面积≥40 px² | 3 | 0 |
| **实际可进入K8D的B候选** | **12** | **9** |
| 占全部B候选比例 | 0.072% | 0.231% |

因此，当前统一程序虽然完整保存了16,766/3,892个K8B源候选，但在B补充路径上只有12/9个候选通过分类和面积门控。

### 9.3 与四处已确认暗斑的直接冲突

当前26_1/26_2最终结果中有四处用户已确认暗斑。逐一追溯它们的K8B初始种子：

| 已确认暗斑 | 最终Mask面积 | K8B源种子面积及K8C分类 | 是否有种子达到40 px² |
|---|---:|---|---|
| 26_1暗斑1 | 297 px² | 34、33、21；均UNCERTAIN_REVIEW | **没有** |
| 26_1暗斑2 | 398 px² | 23 UNCERTAIN_REVIEW；56 PROMISING_DARK_REVIEW | 有1个 |
| 26_2暗斑1 | 370 px² | 48、64 PROMISING；3 MICRO_REVIEW | 有2个 |
| 26_2暗斑2 | 348 px² | 34 PROMISING；6 MICRO_REVIEW | **没有** |

这意味着：
- 26_1的297 px²暗斑没有任何一个B源种子能通过40 px²门限；
- 26_2的348 px²暗斑也没有任何一个B源种子能通过40 px²门限；
- 26_1的398 px²暗斑只有一个56 px²种子可以通过，另一个23 px²种子被门限挡住；
- 26_2的370 px²暗斑有两个较大种子通过，但3 px²的关联种子不会进入后续B补充处理。

**这不是假设，而是当前已确认暗斑的实际源候选面积和分类记录。**

### 9.4 为什么当前最终结果仍然显示这四处暗斑

当前测试RAW恰好是已知的26_1和26_2。统一程序在完整RAW SHA256匹配历史已确认样本时，会额外加载与该RAW哈希绑定的历史人工确认对象。

所以当前输出中仍然出现四处确认暗斑，并不能证明新RAW上的K8C+40 px²门控能够自动检出它们。

对新的、SHA256不同的RAW，不会加载这四处历史人工确认对象。此时26_1的297 px²暗斑和26_2的348 px²暗斑就可能因为所有源种子均小于40 px²而无法进入K8D。

<badge color="danger">P1：需要在新RAW生产使用前处理</badge>

**审查建议：** 不应把40 px²作为K8B初始种子的绝对删除/排除门限。建议将候选源面积与最终疵病面积分开处理：
- PROMISING_DARK_REVIEW的8–39 px²候选应允许进入轻量级RAW/关联复核；
- UNCERTAIN_REVIEW的8–39 px²候选至少应保留低成本复核路径；
- 3–7 px² MICRO_REVIEW不应直接认定为噪声，可在空间邻近或同一暗斑关联后参与轮廓恢复；
- 1–2 px²仍可建议主图隐藏，但源候选必须继续归档。
本轮只记录问题和建议，不修改40 px²参数。

## 10. 其他发现与后续改进

### K8C-02：A固定阈值只要有1个像素重叠，就不再计算RAW证据（P2）

当前分类优先级是 `overlap_with_A > 0` 即归类 `EXISTING_FIXED_H`。这意味着B候选即使有大量B-only新增扩展，只要其中1个像素与A重叠，整个B连通域就不进入RAW局部暗度/MAD/DoG评价。

当前两帧存在：
- 26_1：11个A/B重叠比例低于50%的候选；
- 26_2：4个A/B重叠比例低于50%的候选。

其中包括面积202 px²但A重叠仅20 px²（9.9%）、面积109 px²但A重叠仅11 px²（10.1%）、面积459 px²但A重叠仅153 px²（33.3%）等对象。

这类对象可能是B阈值扩展后与原A候选连接形成的复合连通域。它们被归为EXISTING_FIXED_H后，不再单独评价B-only扩展部分。

**重要语义：** A固定阈值候选不等于J5最终对象。K8C历史报告也明确说明A与J5的候选数量和算法链路不同。因此，`EXISTING_FIXED_H`不能直接解释成“已经由J5检出”。建议后续拆分为：
- A完全覆盖的B候选；
- A与B新增区域部分重叠的复合候选。
第二类应继续做RAW证据评价，或先与J5最终Mask进行明确的像素级覆盖核对，不能仅凭1个像素重叠就跳过。

### K8C-03：统一入口使用a & b，绕过了A包含于B的硬断言（P2）

K8C函数本身会检查A是否有像素落在B之外，但当前统一入口传入的是 `a & b`，因此若未来出现A像素不在B中的情况，调用方会先把这些像素裁掉，使函数内部无法发现该异常。

本次20张RAW、80个工作带的 `A_fixed_pixels_not_selected_by_B_adaptive` 均为0，因此**当前数据没有结果差异**。

建议后续改为先显式执行 `assert np.all(a <= b)`，再将原始A Mask传给K8C，避免调用层静默掩盖异常。

### K8C-04：阈值仍是探索性复核规则，不是盲测分类器（P1）

第二帧Band02此前由用户查看的12个大面积候选，在K8C评分完成后回查，分类为：
- 6个PROMISING_DARK_REVIEW；
- 4个BOUNDARY_REVIEW；
- 1个UNCERTAIN_REVIEW；
- 1个MICRO_REVIEW；
- 0个MICRO_HIDE_SUGGESTION。

用户对这12个候选的观察是“可见暗斑候选”，但K8C仅有6个进入优先暗斑类。其余6个仍被保留为边界/不确定/微小复核，并没有被判为噪声。

这证明K8C类别适合排序和分流，不适合直接用作疵病真实性标签。要认证7%相对暗度、MAD z=2、DoG P90=3 DN等参数，需要独立标注集，不能用这12个开发样本反向调参后再声称盲测有效。

### K8C-05：1–2 px²建议隐藏仅由面积触发（P2）

1–2 px²候选不计算RAW环带、MAD和DoG，直接进入MICRO_HIDE_SUGGESTION。这符合“仅降低主图显示负担”的用途，但不具备噪声物理判定证据。

建议软件界面和报告始终使用“建议隐藏/低优先级显示”，不得使用“已判噪声”或“已删除”。

## 11. 最终处理决定

1. 保留K8C现有RAW局部证据计算和可逆三类Mask归档逻辑。
2. 本轮不修改K8C源码、阈值和历史候选结果。
3. 将40 px²下游硬门限列为P1，后续单独制定修订方案；在修订前，不应宣称当前新RAW路径已满足高召回要求。
4. 将A/B部分重叠候选的分类问题列为P2，后续增加B-only扩展评价或J5像素级覆盖核对。
5. 将统一入口的 `a & b` 改为显式包含关系断言，作为P2工程维护项。
6. 保留K8C现有“隐藏建议不删除源候选”的设计。
7. 未取得独立标注真值前，不报告K8C的Precision、Recall或真实噪声剔除率。

**K8C最终结论：核心分类实现、源候选保留、历史复现和20张RAW前段筛查通过；但当前统一检测链的40 px²面积门控存在已确认暗斑召回风险，必须单独修订和验证后，才能作为新RAW生产检测流程的可靠补充路径。**

## 12. 本轮未执行的操作

- 未修改K8C算法源码或K8C阈值；
- 未修改统一检测程序中的40 px²门限；
- 未修改K8D/K8E及其他下游模块；
- 未覆盖26_1/26_2历史RAW、人工确认记录、K8B源Mask或最终结果；
- 未重新运行20张RAW完整检测；
- 仅执行只读审查、K8B/K8C专项单元测试及新增审查图像生成。


## 13. 图像证据与结果图册

本节插入K8C历史试验图和本轮审查新生成的诊断图。所有图像均来自工程真实输出或由真实RAW/Mask/CSV进行只读整理；未用示意图替代检测结果。

### 图13-1　四处已确认暗斑的K8C初始种子分类核查

![四处已确认暗斑对应的10个K8B初始种子，黄色为源候选像素，绿色为最终疵病框](outputs/K8C_MODULE_AUDIT_20261105/K8C_confirmed_darkspot_seed_classification_audit.png)

**图像结论：** 四处最终已确认暗斑由多个小面积K8B种子构成。图中可以直接看到，26_1的297 px²暗斑三个种子分别只有34、33、21 px²，K8C均为UNCERTAIN_REVIEW；26_2的348 px²暗斑种子只有34和6 px²。它们说明初始候选面积不能直接等同于最终疵病面积。

### 图13-2　A固定阈值与B自适应候选部分重叠的复合候选

![A/B部分重叠候选局部RAW图，青色为A重叠像素，黄色为B-only扩展像素](outputs/K8C_MODULE_AUDIT_20261105/K8C_partial_fixed_A_overlap_candidates.png)

**图像结论：** 部分B连通域只有一小部分像素与A重叠，但仍整体被归为EXISTING_FIXED_H。B-only扩展部分没有单独经过K8C RAW暗斑评分。该图用于定位后续需要与J5正式Mask核对的对象，不代表这些候选已经被判定为真实疵病。

### 图13-3　26_2原J5工作区结果与K8C优先补漏候选

![26_2 J5工作区结果与K8C候选联合展示](outputs/case03k8c_band_supplement_review/run_20261013_f1_f2_allbands_reversible_v2/frame26_2/03_J5_WORK_plus_K8C_provisional_supplements.png)

**图像结论：** 青色标记为K8C优先暗斑候选，原J5工作区结果保持原有显示语义。图中标注的13个K8C候选是补漏复核提议，不应与398个J5工作区对象直接相加并解释为真实疵病数量。

### 图13-4　26_2 Band02用户观察的12个候选RAW局部与K8C分类

![第二帧Band02面积较大候选的RAW局部、K8C分类及局部统计证据](outputs/case03k8c_band_supplement_review/run_20261013_f1_f2_allbands_reversible_v2/frame26_2/band02/review_large12_RAW_vs_K8C_outline.png)

**图像结论：** 12个用户观察候选中，6个为PROMISING_DARK_REVIEW、4个为BOUNDARY_REVIEW、1个为UNCERTAIN_REVIEW、1个为MICRO_REVIEW。后3类仍保留复核，没有被当作噪声删除。

### 图13-5　26_2建议隐藏的1–2 px²微小候选

![26_2工作带内1–2 px²微小候选的主图隐藏建议](outputs/case03k8c_band_supplement_review/run_20261013_f1_f2_allbands_reversible_v2/frame26_2/05_micro_1to2px_HIDE_SUGGESTION_only.png)

**图像结论：** 灰色点为1–2 px²的显示隐藏建议。图像标题明确说明这些源B像素仍然保留，不能把该图解释成算法已确认并删除的噪声。

### 图13-6　20张RAW的K8C优先暗斑候选全局接触表

![20张RAW中K8C优先暗斑候选的全局分布接触表](outputs/CASE03_FROZEN_ROBUSTNESS_20RAW_20261019_v3/20_RAW_K8C_PROMISING_PENDING_CONTACT_SHEET_5samples_x_4frames.png)

**图像结论：** 该图用于比较5片滤光片、每片4帧的K8C优先候选分布。它是K8A/B/C前段筛查图，不代表20张RAW完整J4/J5/K8D/K8E检测已经完成。

### 图13-7　20张RAW的微小候选隐藏建议接触表

![20张RAW中K8C 1–2 px²微小候选的隐藏建议接触表](outputs/K8C_MODULE_AUDIT_20261105/20_RAW_K8C_MICRO_SUGGEST_HIDE_CONTACT_SHEET_preview.png)

**图像结论：** 该图展示20张RAW中微小候选的显示隐藏建议。其数量较大，但源候选未被删除；该分类只用于降低主图显示负担，不能当作噪声真值。

## 14. 审查产物

本轮新增审查目录：

`outputs/K8C_MODULE_AUDIT_20261105/`

其中包含：
- `K8C_confirmed_darkspot_seed_classification_audit.png`
- `K8C_partial_fixed_A_overlap_candidates.png`
- `20_RAW_K8C_MICRO_SUGGEST_HIDE_CONTACT_SHEET_preview.png`

本报告与工程总算法报告均应保留图13-1至图13-7的图片引用。历史K8C试验目录不做覆盖或改写。


## 15. 统一RAW入口的K8C分类Mask持久化补充审查（P2）

在最后核对当前统一运行输出目录时，发现：
- 独立K8C试验脚本会保存 `K8C_promising_raw_supported_mask.png`、`K8C_uncertain_or_fixedH_review_mask.png`、`K8C_micro_suggest_hide_mask.png`，并输出对应图册；
- 但当前统一入口 `fresh_b()` 调用 `evaluate_binary_band()` 时写为 `rows,_,_,_=`，将三个像素级分类Mask返回值直接丢弃；
- 当前统一运行目录的 `upstream_K8BCD/bandXX` 仅持久化 `B_SOURCE_ALL.png` 和RAW外围试验记录，没有单独保存三类K8C像素级Mask；
- 候选级分类字段、连通域标签、源Mask路径仍写入 `ALL_SOURCE_DISPOSITIONS.csv`，因此候选分类信息没有丢失，但像素级分类图不能直接打开查看。

**建议：** 后续统一工程修订时，将三个K8C分类Mask保存为PNG或无损数组，并在运行验收中检查三类Mask互斥且并集等于B源Mask。也可以由完整候选CSV和B源Mask确定性重建，但直接保存更便于工程追溯和人工复核。

本项不改变当前26_1/26_2候选分类数值，列为P2工程可追溯性改进；本轮未修改代码。
