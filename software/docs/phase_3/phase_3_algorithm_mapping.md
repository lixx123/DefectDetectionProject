# Phase 3 真实算法与领域映射

协议仍为Phase 2冻结schema 1.0，domain/未修改。Detector同步返回内存InspectionResult，不依赖Qt，不实现Repository。

## 真实入口与隔离

core/detector.py提供Detector.inspect(image_path, config)。ReferenceEngineAdapter使用原工程.venv，以engine_worker子进程调用现有run_two_level_unified.run_raw(mode=full/roi-bh/roi-j4)。仅在完整import历史源常量后重定向当次OUTPUT_ROOT，J4/J5内部输出也由原函数指向此任务。无阈值、算法函数或几何逻辑修改。

生产AUTO只尝试ROI_BH，任一安全/输出门禁不通过则直接FULL。高级显式模式只执行请求模式，不暗中回退。LEGACY_REPLAY必须与冻结RAW内容SHA256完全相符，只解析Phase 0结果，不伪称重新计算上游。

默认参考源是软件工程的同级DefectDetectionProject，可通过Detector(reference_root=..., python_executable=..., output_root=...)配置；目前仍依赖原工程及其审核/历史参考资料，尚非独立EXE。

## 输入与算法身份

RAW尺寸、有效位深、字节序从原配置AST读取常量，不在父进程import原算法。仅支持原uint16大端格式；检查文件字节数、逐块最大DN及完整SHA256。ImageInfo保存file_name/sha256/像素格式，不保存绝对输入路径。sample_id是文件名的样本号提示，不据此应用人工审批；原引擎审批由RAW哈希绑定。

AlgorithmInfo包含source-sha256关键源码manifest摘要、软件版本、配置语义hash、带UTC+08:00时间戳、耗时和真实运行环境。legacy使用冻结源码manifest摘要。运行日志及原始引擎证据可以包含实际路径，统一领域JSON中的资源引用均相对result.json。

## Defect

| 引擎数据 | 领域语义 |
| --- | --- |
| final_ID | identity.defect_id |
| bbox_xyxy_exclusive + NPZ bbox | geometry.bbox，原图左闭右开坐标 |
| NPZ mask前景数与CSV面积一致 | area_px；不使用bbox面积，孔洞不计、重叠拒绝 |
| max_Feret_detector_px | length_px，MAX_FERET_PIXEL_CENTERS，非中心线长度 |
| mask_path/raw_mask_npz实际本地文件 | mask_reference相对引用和SHA256 |
| source_uids/历史来源列表/NPZ sources | detection.candidate_ids和source_channels |
| RAW_recovery_gate_audit关联来源 | audit.events及detection.merge_history |
| grade | size_grade；severity_grade保持UNKNOWN |
| human_confirmed_darkspot | 原RAW绑定历史审批，review CONFIRMED；不伪造审核人或时间 |

独立复核每个mask的像素数、最大Feret、bbox、来源集合和对象不重叠，并与整图二值mask逐像素核对。旧CSV长度保留4位小数时允许0.000051px误差；新鲜输出值保持其原始精度。独立Feret计算只做QA，不替代引擎数值或修改算法。

位置是最终bbox中心，明确标FINAL_BBOX_CENTER_NOT_CENTROID，不冒充质心。Band可从引擎字段/真实Band-ID栅格中心查询获得。无宽度/方向/灰度指标则None，不猜测。物理尺寸仅由config.calibration换算，适配器没有另写空间尺度常量。用户声明尺度不等于完成物面标定。

## ROI/Band

直接读取band_geometry.json、region_type_fullres.png和band_id_fullres.png。区域码为0 NON_WORK、1 SHIELD、2 WORK_CORE、3 BAND_EDGE_REVIEW；work=2、nonwork=0/1、review=3。导出对应二值mask及每Band core mask供未来显示；只是按原标签拆分资源，不重新定位Band。

Band bbox/pixel_count来自原标签，mean/min/max DN按原RAW与Band core统计。原线性边界/质量样本记录保留在extensions，并引用真实geometry文件。生产valid表示执行安全验证通过，不等于人工物理验收；review_status仍未审核。

Band失败回退时保留失败ROIInfo及Band.valid=false供审计。legacy导出没有ROI资源则保留NOT_EVALUATED/None，不伪造。

## 来源与审计

读取ALL_SOURCE_DISPOSITIONS或旧ALL_ORIGINAL_J5_AND_B_SOURCE_DISPOSITIONS_NO_DROP；联合ALL_HISTORICAL_SOURCE_DISPOSITIONS_NO_DROP/HISTORICAL_ALL_SOURCE_LINEAGE_UNCHANGED，逐源UID去重。原源数、源bbox/面积、阶段、最终去向和处理理由均保留。

新鲜J5来源与global_object_membership核对；旧final_group_membership与最终NPZ source_uids核对；RAW recovery记录逐行关联来源和最终Defect。源→Defect与Defect→至少一个源都必须成立，否则拒绝采用。历史归档未重算者明确标historical_only_not_recomputed，不能作为“本次新扫描”计数。

source_candidate_count是联合审计UID总数，另记录fresh_source_count/historical_source_count。ROI边界额外局部源允许显式加入，绝不靠截断隐藏原历史源。非最终候选是算法门控结论，不等价人工噪声真值。底层CSV、恢复记录、J5成员和身份映射均保留资源引用。

## 统计与资源

从映射后的Defect[]汇总数量、等级、波段、ROI、面积、审核统计，再与引擎acceptance核对。没有可靠点/划痕类型时类型为UNKNOWN，scratch_total_length为None，不能把所有Feret相加冒充划痕中心线总长。

每个最终NPZ、二值整图、标注图和重要审计资源均须存在并保存SHA256。外部legacy资源复制到本次目录并复验哈希；本次engine内资源使用相对路径。可选中间图级别NONE也不删除关键测量/审计资源。

最终Execution QA PASS、Result QC PASS后调用validate_final；JSON保存由调用者/验证脚本显式完成。失败结果为FAILED草稿且final_mode为空，无法通过正式门禁，不静默返回“零疵病通过”。
