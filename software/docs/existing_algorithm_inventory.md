# 现有算法工程盘点（2026-10-20）

## 范围和证据
原工程：`D:\疵病检测\DefectDetectionProject`，本轮不修改算法、配置、测试或原始数据。
源码277文件逐文件SHA256及回滚副本位于 baseline/source_manifest.json、baseline/source_snapshot/。
原目录不是Git仓库（git status返回128），采用上述独立快照冻结；新软件单独建立Git。
原AGENTS历史停止条款以本次用户明确授权的Phase 0/1范围为准，不扩展到软件Phase 2。

## 1. 主入口
`main.py --case unified-final --sample 26 --run-id <唯一新名称>`：重执行最终判定/RAW恢复，复用冻结J4/J5上游。
`main.py --case unified-final --fresh --input <RAW> --run-id <唯一新名称>`：从RAW完整重算，调用 scripts/run_unified_raw_input.py。
`--roi-mode full|roi-j4|roi-bh --input <RAW>`：调用 scripts/run_two_level_unified.py。今日新增的两级ROI调度分支，参数位于 TWO_LEVEL_ROI；本次不将可选分支替换默认基线。

## 2. 主要文件和依赖边界
main.py、config/user_config.py；scripts/run_unified_final_revision.py（最终选择/导出）、run_unified_raw_input.py（完整RAW链路）、run_case03_unified_final_detector_26_1_2.py（历史源/审核加载）、run_case03j4_fullscan.py、run_case03j5_global_merge.py、verify_unified_revision.py。
主要算法模块位于 src/detection，RAW位于 src/io/raw_reader.py，最终标注位于 src/visualization/unified_final_boxes.py。
旧代码具有模块全局路径和历史输出依赖，不能直接作为无状态服务搬入GUI。后续需在基线确认后定义适配边界。
完整源码和主要脚本已冻结，而不是只复制主入口。

## 3. 输入格式和样本
260624批次：无头RAW，11276×9200，每像素16bit容器、大端，有效12bit；每文件207478400字节。
验证输入：`D:\疵病检测\疵病实测数据\260624批次表观（5片）\26 (1).raw`、`26 (2).raw`。
截图/JPG/普通8bit预览不能作为该算法定量输入，其他格式需后续明确适配。

## 4. RAW读取
src/io/raw_reader.py 的 RawReadConfig/read_raw 先验证长度，以 >u2 读取，转原生uint16并reshape(height,width)，不进行8bit归一化。
完整链路亦使用原12bit DN，显示预览不参与定量。原始文件只读，本轮保存SHA256。

## 5. 像元尺寸
config/user_config.py 的 PIXEL_SIZE_UM=3.2，为探测器像面μm/px。
物面倍率/标定未确认；正式统计为px、px²，不能直接将3.2用于样品物面尺寸换算。

## 6. ROI
case03k8a_band_locator.py 从行稳健灰度统计定位两侧有暗槽包围的透射平台，动态波段数量，输出WORK/CORE/REVIEW边界；不是固定手画ROI。
新 two_level_roi.py 根据算法halo、外围恢复上下文和几何工作区调度计算，使用65535未计算哨兵并拒绝消费未计算响应；不把CORE边界当作原算法硬截断边界。
当前基线按默认双帧复核入口运行，未重新执行这条可选ROI加速分支。

## 7. Black-Hat
blackhat.py、multiscale.py；椭圆核3/5/9/15/31，对原uint16 DN做closing减原图，逐像素max融合。
完整RAW运行prepare_fused采用分块和两次形态学所需halo，避免分块接缝改变结果。

## 8. 固定/局部阈值
历史固定H170/230为低170、高230的强种子双阈值，保留相连弱响应。
K8B按波段median/MAD生成自适应阈值，见 case03k8b_perband_trial.py。
历史阈值研究并非当前唯一生产规则；本轮不调整参数。

## 9. 候选生成
H双阈值8连通组件 + K8B波段A/B候选，J4以256px核心、64px halo扫描1620块/帧。
源ID、像素mask、波段和来源保留，不以最终显示框生成测量面积。

## 10. 噪声筛除
F candidate_local_noise.py：RAW参考环带、相对对比度、MAD显著性；G case03g_joint_gate.py保护已有精修和附近强结构；H case03h_background_texture.py结合DoG、大小、方向保护；K8C case03k8c_noise_review.py给出微点/背景/待审建议。
最终按UNIFIED_FINAL门限选择，微点未入主图仍在完整源台账。

## 11. 暗斑恢复
case03e2_hseeded.py 以H种子约束Gaussian22/Closing61，case03e2_bounded_rescue.py处理有界恢复。
K8D调用RAW外围3/2/1.5MAD和稳态安全门控；unified_proposal_selection.py选择稳定证据。
unified_raw_recovery.py使用真实源并集、RAW背景残差连通支持、增长/距离/短轴等门控恢复多段对象；人工批准mask不可变，失败退回源并记原因。

## 12. 划痕关联
case03j_fragment_association.py、case03j_continuous_contour.py；方向/间隔/RAW DoG证据，拒绝含糊多重关联。
最终J5方向性小划痕有专门保护；不能把历史推断连接像素当实测疵病面积。

## 13. 跨窗口合并
case03e2_window_stitch.py、case03j5_seam_match.py及run_case03j5_global_merge.py，真实像素相交、接缝方向和RAW证据，非仅按中心距离或bbox相交合并。
最终精确OR和源归属消除重复像素，保留全源去向。

## 14. 尺寸
mask前景计数为面积，孔洞不计/重复像素只计一次；case03i_size_grade.py 的 max_feret_centers_px 按像素中心凸包最远距离计最长Feret，不是弯曲中心线长度。
框放大1.5倍仅显示，不参与面积/长度；单像素空间最小长度1px。

## 15. 分级
SizeGradeConfig：面积>=250px²或Feret>=45px为LARGE；否则面积>=40px²或Feret>=15px为MEDIUM；其余SMALL。
属于暂定几何尺寸等级，不是工业严重度或合格判据。当前软件阶段尚无独立severity模型。

## 16. 结果和最新基线
历史最新已交付：outputs/CASE03_UNIFIED_FINAL_DETECTOR_26_1_26_2_20261019_v4。
本次新运行：outputs/SOFTWARE_PHASE01_BASELINE_20261020_01，已复制进新工程baseline/results/unified_26。
每帧包含最终图、CSV、EXACT_FINAL_BINARY_MASKS/*.npz、全分辨率PNG、全源审计、恢复门控、局部证明、acceptance。
36/35自动对象，面积20356/17709px²；两帧源台账32370/8332行。四处人工批准面积297/398/348/370px²。
与v4逐对象ID/位置/面积/Feret/等级/来源一致，全分辨率mask SHA256一致。其他入选对象不自动成为人工真值。
暗斑、划痕、大/微小候选包含在现有测试和全源台账中；没有发现独立盲测真值集，因此不声明所有微小缺陷或划痕零漏检。

## 17. 第三方包
原requirements：numpy、opencv-python、scipy、scikit-image、pandas、matplotlib、pytest；准确已安装版本见 baseline/metrics/original_requirements_lock.txt。
新软件另有PySide6、PyYAML、openpyxl，安装在独立.venv，完整版本见requirements-lock.txt。
ReportLab/PyInstaller属于后续阶段，本轮不打包、不实现报告。

## 验证与后续边界
当前原工程354项pytest通过，独立像素QA通过；结果不等价于物理检出率验收。
277份原源码/配置/测试/文档的SHA256前后相同。Phase 2前须人工确认基线、工程结构及可选ROI分支后续适配范围。
