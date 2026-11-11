# 滤光片疵病检测工程

## 2026-10-19 最新审查修复交付

最新矩形终检图为 `outputs/CASE03_UNIFIED_FINAL_DETECTOR_26_1_26_2_20261019_v4/`，历史v2不覆盖。
从输入RAW完整检测请看 [使用指南](UNIFIED_DETECTOR_USER_GUIDE.md)；支持拖放 `Run_Detection.cmd`。
审查证据见 [根因报告](CODE_REVIEW_AND_ROOT_CAUSE_20261019.md)，运行、测试与限制见
[阶段验收](UNIFIED_FINAL_ACCEPTANCE_20261019.md)。以下早期阶段记录保留，不代表当前入口。

本工程面向260624批次滤光片RAW数据，采用Python传统图像处理路线。目标是让**任意一张单幅图像都能够独立完成疵病检测、定位和定量**，不依赖图像配准。

## 当前状态

- Case00：RAW读取与数据体检，已完成并作为当前代码基线。
- 旧Case01：同视场图像配准，已停止作为主流程；历史输出保留。
- Case02：单张图多尺度Black-Hat暗异常增强；既有结果保留并作为Case03-A输入。
- Case03-A：全图固定阈值与局部Median/MAD鲁棒阈值对照；A0基线保留。
- Case03-A-R1：阈值候选扫描、严格零方差比较、真实密度缩略图和扩展诊断；候选尚未确定为正式阈值，完成后停止等待用户视觉验收。

当前活动代码支持Case00和Case02；Case03-A/A-R1使用独立脚本读取既有Case02响应和A0基线；`--case 1`明确拒绝执行旧配准。

## 当前主算法路线

`RAW读取 → 单张图多尺度Black-Hat → 多尺度融合 → 候选响应统计 → 后续ROI/背景建模 → 阈值分割 → 形态学/连通域 → 原始DN与几何定量`

若以后同一位置拍摄多张图，可分别独立检测后比较结果；默认不做配准。

## Case00运行

```powershell
Set-Location 'D:\疵病检测\DefectDetectionProject'
& .\.venv\Scripts\python.exe main.py --case 0
```

可选参数：

```text
--sample 26
--frame 1
--run-id NAME
```

## Case00输出

输出目录：
`outputs/case00/run_YYYYMMDD_HHMMSS/`

包括：
- config_snapshot.json
- input_manifest.csv
- frame_statistics.csv
- histograms.csv
- previews/
- profiles/
- acceptance.md
- logs/

原始RAW文件不会被修改、移动或覆盖。

## 历史配准结果

旧Case01产生的 `outputs/case01/` 仅作为历史记录保留，不属于当前主检测流程，也不应作为Case02的输入前提。

## Case02运行

```powershell
Set-Location 'D:\疵病检测\DefectDetectionProject'
& .\.venv\Scripts\python.exe main.py --case 2
```

默认使用样品26、27、28、29、30的第1帧，统一运行3/5/9/15/31 px椭圆结构元。Black-Hat响应逐尺度以压缩NPZ保存，PNG仅用于显示；Top-N patch仅供人工观察，不等于最终缺陷判定。

## Case02效果验证

验证脚本读取既有Case02运行目录，不覆盖原结果：

```powershell
Set-Location 'D:\疵病检测\DefectDetectionProject'
& .\.venv\Scripts\python.exe scripts\validate_case02.py
```

输出写入 `outputs/case02_validation/run_YYYYMMDD_HHMMSS/`，包括联系图、Top20图册、逐尺度Top10对照、统计报告和人工审核模板。

后续阶段定义以：
`D:\疵病检测\Codex_滤光片疵病检测分阶段实施提示词.md`
为准。

## Case03-A运行

Case03-A不重新计算Black-Hat，不覆盖Case02或Case02验证结果，仅读取既有响应NPZ：

```powershell
Set-Location 'D:\疵病检测\DefectDetectionProject'
& .\.venv\Scripts\python.exe scripts\run_case03a.py
```

默认处理样品26~30、第1帧、3/5/9/15/31 px。固定阈值统计为150/200/250/300 DN，主固定阈值为200 DN；局部鲁棒统计为k=3/5/7、floor=120 DN，主局部参数为k=5。输出写入 `outputs/case03a/run_YYYYMMDD_HHMMSS/`，包括配置快照、输入清单、两类阈值统计、局部网格统计、主掩膜、联系图、典型点patch、报告、验收和日志。主掩膜使用无损packbits保存并执行还原校验。

本阶段不计算真实疵病Recall/F1，不执行连通域、形态学、面积过滤、TopN截断或Case03-B。

## Case03-A-R1补充修订

R1只写入新的 `outputs/case03a_revision/run_YYYYMMDD_HHMMSS/`，不覆盖RAW、Case02 NPZ或旧Case03-A运行目录：

```powershell
Set-Location 'D:\疵病检测\DefectDetectionProject'
& .\.venv\Scripts\python.exe scripts\run_case03a_revision.py
```

A1按3/5/9/15/31 px使用独立固定DN候选扫描；A2先在样品26中心小区域筛查，再用3组代表性`k/floor_dn/min_excess_dn`参数对5个样品对照。A0旧结果与A1/A2分别保存、统计和对照。`density_thumbnail`使用原始bool掩膜块平均覆盖率，`any_hit_thumbnail`仅作会放大稀疏噪声的提示图；叠加图先在全分辨率计算互斥类别，再分别面积下采样。

R1输出包含 `scale_threshold_proposals.csv`、`regional_density_statistics.csv`、`overlap_statistics.csv`、`grid_statistics.csv`、`grid_cells.csv`、`masks/`、真实密度图、原尺寸patch、报告、验收、保护目录核对和变更日志。本轮不自动选定正式阈值，不计算Recall/F1，不进入Case03-B。
## Case03-B completion status (2026-10-08)

The current completed stage is Case03-B. The full self-accepted run is
`outputs/case03b/run_20261008_152500/`. It produced all S/H candidates for
samples 26-30 frame 1, local validation evidence, lossless masks including H
low-only masks, and the sample26 fused-versus-31px comparison. Historical
Case02, Case03-A and Case03-A-R1 results remain protected. Case04 and Case05
were not executed; stop here pending user review.


## Case03-B样品26局部单阈值/双阈值复核图册（独立运行）

仅基于Case02已有融合响应与Case03-B已保存的**全图**S230、H170/230及H150/230掩膜生成局部对照；不修改任何既有检测输出或执行新阈值优化：

```powershell
Set-Location 'D:\疵病检测\DefectDetectionProject'
& .\.venv\Scripts\python.exe scripts\build_case03b_sample26_gallery.py
```

参数集中在 `config/user_config.py` 的 `CASE03B_GALLERY_*`，本次固定样品26、第1帧；复核输出在 `outputs/case03b_gallery/run_YYYYMMDD_HHMMSS/`。查看 `figures/contact_sheet_part01.png` 到 `part03.png`；各位置有原RAW、融合响应、S230、H170/230、H150/230、彩色新增响应及无损NPZ。全部候选`candidate_not_truth`，不自动认定真实疵病或细划痕，Case04/Case05未执行。
## Case03-C phase 1 completion status (2026-10-08)

The requested Case03-C phase 1 is complete through engineering self-acceptance in
`outputs/case03c/run_20261008_174000/`. Gate A and Gate B passed before the full
sample-26 run. The output includes `core_to_hysteresis.csv`, complete S230 and
H170/230 feature CSVs, `manual_review_template.csv`, a 60-entry stratified review
atlas, feature-validity statistics, resource measurements, report, acceptance
record, and protected historical-input checks.

The verified totals are S=91,937 candidates / 121,467 pixels and H=88,043
candidates / 311,790 pixels. S-to-H mapping and seed-plus-expanded area
conservation passed; 2,110 H candidates have multiple S cores. Manual review
labels are blank by design. No local MAD thresholding, candidate deletion, or
automatic truth classification was used. The complete regression suite passed:
34 tests. Stop here pending human review; do not enter Case03-D, Case04, or Case05.

 
## Case03-C-R1：RAW参考环带可视化修复与特征判别力验证准备

源数据不变：`outputs/case03c/run_20261008_174000/`。独立修订输出：`outputs/case03c_revision/run_20261009_reference_feature_review/`。

- 统一RAW参考环带几何：`src/detection/reference_ring_geometry.py`；`src/detection/candidate_raw_features.py`采用同一计算选择函数，旧环带统计定义不变。
- 新图册 `figures/review_001_reference_corrected.png` ~ `review_060_reference_corrected.png`：分开显示可用环带范围与真正参与统计的至多512个像素；无效参考时，统计采样为空。
- `reference_geometry_audit.csv`核对原Case03-C统计的有效环带数、采样数、中位数与MAD；`patches/`保存对应无损RAW/响应/S/H/选中候选及环带掩膜。
- `feature_distribution_unlabeled.csv`仅用于1px、2～19px、≥20px、亮暗过渡等未标注形态代理的分布分析，不代表判别准确率。
- `manual_review_template.csv`为独立可人工填写副本；有人工确认的`manual_label`时还须把`review_status`设为`reviewed`。标注前`feature_labelled_separability.csv`只能是PENDING_LABELS，禁止自动赋予真值。
- 原标签来源有重复候选ROI，人工评价按`candidate_id`去重，重复候选如果标签冲突将明确报错。
- 重算标注后的探索性分布：`python scripts/revise_case03c_evidence.py --evaluate-only --output-dir outputs/case03c_revision/run_20261009_reference_feature_review --labels <标注CSV路径>`；正负人工候选数各至少5个才输出单特征rank AUC及自助法区间，非外部泛化指标。
- 本轮不更改Black-Hat、不更改230/170 DN、不启用局部MAD、不删除候选、不进入Case04/05。

 
## 样品26九处真实目标人工点选复核工具（2026-10-09）

经用户确认，原`manual_review_template.xlsx`中9处标签对应关系需修正（6处黄色/青色目标为异常，3处RAW可见但分割未完整识别）。新增`scripts/build_case03c_manual_retarget_ui.py`，生成静态离线网页`outputs/case03c_manual_retarget/run_20261009_9roi_target_review_v2/index.html`，所有输出与原图/历史掩膜分离。原始RAW坐标可以在网页点击/拖框后导出`case03c_sample26_user_retarget.csv`；**不以旧红色选中ID默认代表人工阳性**，需用户导出后再运行精确全图组件关联。支持多个目标、JSON备份、阈值命中状态提示。9ROI→27张PNG及嵌入掩膜，经Node JS语法和Chrome离线打开检查、无损像素比对及全工程回归（44 passed in 4.38s）。页面接受用户人工确认，不会自动删除微小候选、修改旧阈值或训练模型。仍不使用局部MAD，也不进行27～30样品检测。


## Case03-C人工点选CSV精确关联与弱暗斑诊断（2026-10-09）

用户提供C:\Users\lixia\Downloads\case03c_sample26_user_retarget.csv，共12条标注、8张review（review_056缺失）。基于Case03-B无损全图掩膜，新增scripts/resolve_case03c_user_retarget.py实现点击点的8连通真组件匹配，按完整bbox+area与Case03-C现有特征CSV唯一对应；新增scripts/analyze_case03c_retarget_local.py用于原RAW+BlackHat+阈值的真实DN局部诊断；新增tests/test_case03c_exact_retarget.py检查映射、无mask点不猜ID、标签去重和欠分割框验证。本轮完整pytest 50 passed in 3.04s。

结果保存在outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v1；5个命中点、4个不同H候选（review_021、024、027、039，其中039黄色与青色点同属同一个H组件），6个未命中点不能强行记成阳性ID，31号30x20框内S230=0、H170=0、BlackHat峰216DN、35px超过170DN但0px超过230DN，形成一个明确的强种子不足/未完整检出例。46号点靠近旧ROI边缘、未画完整框；56号未导出。合并原可信10正39负和本次4个确切正候选后有14正39负，面积/峰值的AUC仅为当前人工选取样本的探索性排序，不可外推全图识别率；且已检出样本AUC不涵盖31等未检出暗斑。全部旧运行源、原始标注未覆盖，阈值230/170及局部MAD设置不修改；下一步针对18/19/24未命中点核对真实目标、46/56补充完整ROI再考虑算法诊断。详细报告：outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v1/retarget_analysis_report.md。


## Case03-C第二版人工复核（2026-10-09）

用户输入C:\Users\lixia\Downloads\case03c_sample26_user_retarget (1).csv（Windows括号前含空格），20条人工标记，13点7框；用户明确更正review_056无问题，退出未检出疑点列表但不当成候选级背景负类。第二版精确分析新目录outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v2，历史v1及原始CSV/Excel/RAW/Case02/03B/03C保留。

利用全分辨率掩膜，18/19暗斑框内分别有151/98个H像素，其中主H候选占97.35%/96.94%；24三个框各对应主导H候选，两个此前只在框选中出现（第三个已点击直接精确命中）。对于由大多数像素关联的四个新H组件只标记“暂定”，不冒充完整人工像素级标签；严格保守14正39负，敏感性扩展18正39负。31框30×20px中H/S均0，Bhat峰216DN，46框24×17px同样H/S为0，Bhat峰194DN，属于值得研究的弱暗区强种子不足案例。新生成7框明细CSV及对照图、标注敏感性AUC、完整工程报告和变更记录；全项目pytest 55 passed in 3.06s。未调整230/170DN阈值，不启用局部MAD、不删候选、不进入Case04/05。下一步优先031和046局部宽缓暗区增强/分割诊断。

 
## Case03-D补充：单像素防盲区与数据质量核查（2026-10-09）

- 88,043个H170/230候选主排序完整输出，A=881，B=7,924，C=79,238，score仅由全图面积与峰值DN各50%的经验百分位得到，**人工标签只在排序后用于探索性统计**。
- 已标注14正39负中12正落在A，1正B，1正C；C中的正候选为原review_045，H_sample26_0379819，面积3px、峰值232DN、排名54,778，人工标签confirmed_dark_spot但备注空白，须核对。A中的已标注负候选为原review_029，H_sample26_0380656，面积25px、峰值271DN、排名321。
- 实际RAW图册A榜前12位中既有明显暗点也有强亮暗过渡/条带边缘响应（例如未标注H_sample26_0428940、H_sample26_0425919）。A组881个里304个（34.5%）被背景过渡代理标记，提醒不能将A视为真实疵病高概率组。
- 全图35,678个面积为1px的H候选**全部落在C组**，可见面积参与主排序会将真正微小异常也一起后置；新增scripts/build_case03d_micro_safety.py作为独立人工抽查队列：micro_single_pixel_full_audit.csv留存35,678条，micro_single_pixel_top100.csv另选最强峰值前100条，figures/atlas_single_pixel_high_peak_audit.png显示RAW/S/H局部。**不自动把小点认定为缺陷，不改变主评分、优先级和任何源掩膜。**
- src/detection/candidate_priority.py为无监督可解释排序函数；scripts/run_case03d.py为工程运行入口，scripts/build_case03d_gallery.py生成RAW图册及全图质心分布示意，tests/test_case03d.py覆盖人工标签不参与得分、跨输入行排序稳定、全量保留1px、名单去重、微点完整归档等检查。
- 本次结果目录：outputs/case03d/run_20261009_190000。case03d_qc_findings.md与manual_recheck_queue.csv提供人工复核与风险列表；Case03-D的独立外部样品检出性能仍PENDING USER。
- 原始RAW、Case02、Case03-B、Case03-C及用户标注文件不做任何覆盖，仍暂停局部MAD与Case04/05；31、46、56按用户当前要求为本阶段非目标区域，**不转成候选级负真值**。


## Case03-D启动方式

在工程根目录运行 python main.py --case 3d --run-id 新运行目录名。禁止与既有运行目录重名；全部结果保存在 outputs/case03d/。本轮最终目录 run_20261009_190000；查看case03d_report.md、case03d_qc_findings.md以及figures目录的RAW候选图册和微点审查图。


## Case03-D-R2：自动疵病候选判别原型（2026-10-09）

根据用户最新目标（自动识别疑似疵病并尽量排除噪声、输出位置/轮廓/数量、仅让人工复核不确定区域），在保持原Case02/03B/03C以及Case03-D评分排序不变的前提下，新建src/detection/candidate_autodecision.py及scripts/run_case03d_autodetect.py等，实现按面积/峰值/点线形态/可靠RAW差异/黑带边缘特征的三分组初版规则。

完整执行命令：python main.py --case 3d-auto --run-id run_20261009_autodetect_final。结果：自动疑似疵病139个（133点状、6线状）、不确定候选6685个、噪声倾向但保留81219个，合计88043个H候选；311790个H候选像素原位保留且全图分类图逐像素守恒。6824个自动疑似与不确定组件导出bitpacked精确二值掩膜与真实连通域边界；未删除任何单像素候选。开发样本人工标签已修正为13正42负，其中10正自动检出、3正不确定，42负中0个自动检出，但此非盲法独立数据，不能当真实召回率/误报率。31、46、56按用户决定本阶段不追求其检出，也不作候选级负样本。全项目pytest 81 passed in 11.36s。

新建离线review页面：outputs/case03d_autodetect/run_20261009_autodetect_final/uncertain_manual_review_batch01/index.html，从6685个不确定候选中分层各20例共100例，用户可直接人工标注暗点、细划痕、背景伪影、不确定并导出CSV和JSON备份；网页Chrome离线渲染通过、JS语法检查通过。此抽样只用于有针对性的算法改进，不能当无偏测试集。

推荐用户先看figures/auto_detected_only_full_view.png（139个自动候选全图轮廓显示）、figures/atlas_detected_top12.png（RAW与精确绿色连通域）、figures/atlas_band_edge_artifacts.png（第2、第5背景伪影）、case03d_autodetect_report.md。模型尚未在独立新样品验证，面积/峰值与背景参考并不保证微小弱疵病不进入噪声倾向组，因此阶段状态为工程原型而不是已达成工业验收。

实施代码不修改旧运行目录：输出在outputs/case03d_autodetect/run_20261009_autodetect_final；src/detection/candidate_autodecision.py（规则）、candidate_contour_export.py（精确轮廓）、scripts/run_case03d_autodetect.py（管线）、scripts/render_case03d_autodetect_fullview.py（全图PNG）、scripts/build_case03d_uncertain_review_ui.py（100例离线标注界面）、tests/test_case03d_autodetect.py（回归）。后续务必基于新样品盲法标注验证真实疵病位置、轮廓、误检率和漏检率后才可声明自动检出效果。


Case03-D自动检出图册默认采用3列：RAW / ALL S/H / ALL AUTO in ROI（带局部编号及当前候选红框）。参见outputs/case03d_autodetect/run_20261009_autodetect_final/CHANGELOG_ATLAS_THREE_PANEL.md。


## Case03-E局部轮廓精修试验

运行`python main.py --case 3e --run-id <新的run目录>`对用户已确认保留的10个RAW异常中心作3种局部背景×2档阈值的精修对照（60组），报告见`outputs/case03e/run_20261010_10roi_boundary_pilot_v1/CASE03E_PILOT_REPORT.md`。本阶段仍依赖人工点击中心，不能宣称已完成全图自动检测或真实疵病尺寸测量；003/010与背景粘连、004/006方法不稳定须人工核对。


## Case03-E2：多候选自动发现与互补融合

使用`python main.py --case 3e2 --run-id <新run-id>`在样品26指定9个RAW固定网格参考窗口中运行H170/230+Gaussian22+Closing61独立多种子分割、融合及精确无损掩膜导出。脚本将自动执行14项验收并出具PASS/FAIL/DEFERRED。查看`outputs/case03e2/run_20261010_multiseed_fusion_v5/CASE03E2_TECHNICAL_REPORT.md`；当前8通过2失败4待验证，尚非整幅RAW自动检测及精确物面尺寸系统。


## H170/230唯一候选源（Case03-E2方向修正）

用户确认不能让Gaussian或形态学独立产生背景伪影候选。现默认`python main.py --case 3e2 --run-id <新ID>`只以原H170/230连通域发现候选、两种局部背景法仅在已有H附近补轮廓；旧独立模式保留为`python main.py --case 3e2-legacy --run-id <新ID>`。新版报告：`outputs/case03e2/run_20261010_H_only_seeded_refinement_v2/CASE03E2_H_SEEDED_REPORT.md`。本轮14项验收9PASS/2FAIL/3DEFERRED；不可将参考ROI结果视为全图真实疵病数量。


## Case03-E2-H5：W005背景连接下有界划痕精修

在现有`--case 3e2`中新增H原种子7px邻域有界轮廓扩展。局部Gaussian/Closing全图阈值区域触边时并不直接全部拒绝，可使用H周围受限且两方法共同支持的边缘像素，但仍标记`needs_review_bounded_extension`。结果：`outputs/case03e2/run_20261010_H_seeded_bounded_consensus_v5/CASE03E2_H_BOUNDED_W005_REPORT.md`；先看`figures/E2_W005_cross_scratch_before_after.png`。
