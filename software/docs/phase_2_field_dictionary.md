# Phase 2 字段字典

本次属于schema 1.0冻结前修订。所有公开计划字段只属于DetectionPlanInfo，经ExecutionAttempt.plan持有；ExecutionInfo不继承计划。

## 统一约定

- bbox为原图像素左闭右开[x0,y0,x1,y1)，x对应列、y对应行。
- 面积area_px/total_defect_area_px为px²，长度/宽度/直径为px；物理面积um²、长度um。
- 物理位置单位由physical_coordinate_unit声明，默认um；原点/映射未知时为空。
- 灰度和blackhat_response为原始DN；比例/对比度无量纲；方向为度。时间戳是带时区ISO-8601字符串，耗时秒。
- ID为稳定字符串；None表示未知/未计算，不能当0。extensions是JSON兼容字典。
- _unknown_fields是内部编解码保留区，不作为专门JSON字段输出。

## Record

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |

## FrozenRecord

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |

## Point

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| x | `float` | 必填 |
| y | `float` | 必填 |

## BoundingBox

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| x0 | `int` | 必填 |
| y0 | `int` | 必填 |
| x1 | `int` | 必填 |
| y1 | `int` | 必填 |

## ArtifactReference

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| path | `str` | 必填 |
| sha256 | `str \| None` | None |
| media_type | `str \| None` | None |
| coordinate_system | `str` | 'ORIGINAL_IMAGE_PIXELS' |

## CalibrationInfo

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| spatial_scale_um_per_px | `float \| None` | 3.2 |
| scale_source | `<enum 'ScaleSource'>` | 'DEFAULT' |
| calibration_id | `str \| None` | None |
| calibration_time | `str \| None` | None |
| valid | `bool` | True |
| reference_plane | `str` | 'USER_DECLARED' |
| metrologically_calibrated | `bool` | False |

## DefectIdentity

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| defect_id | `str` | 必填 |

## DefectGeometry

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| bbox | `domain.common.BoundingBox \| None` | None |
| center | `domain.common.Point \| None` | None |
| area_px | `float \| None` | None |
| area_um2 | `float \| None` | None |
| length_px | `float \| None` | None |
| length_um | `float \| None` | None |
| width_px | `float \| None` | None |
| width_um | `float \| None` | None |
| equivalent_diameter_px | `float \| None` | None |
| equivalent_diameter_um | `float \| None` | None |
| contour_reference | `domain.common.ArtifactReference \| None` | None |
| mask_reference | `domain.common.ArtifactReference \| None` | None |
| area_method | `str \| None` | None |
| length_method | `str \| None` | None |

## Morphology

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| aspect_ratio | `float \| None` | None |
| circularity | `float \| None` | None |
| elongation | `float \| None` | None |
| orientation_deg | `float \| None` | None |
| solidity | `float \| None` | None |
| eccentricity | `float \| None` | None |
| skeleton_length_px | `float \| None` | None |

## Photometry

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| mean_gray_dn | `float \| None` | None |
| min_gray_dn | `float \| None` | None |
| max_gray_dn | `float \| None` | None |
| background_mean_dn | `float \| None` | None |
| background_std_dn | `float \| None` | None |
| gray_difference_dn | `float \| None` | None |
| gray_ratio | `float \| None` | None |
| local_contrast | `float \| None` | None |
| blackhat_response | `float \| None` | None |

## Classification

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| defect_type | `str \| None` | None |
| defect_subtype | `str \| None` | None |
| size_grade | `<enum 'SizeGrade'>` | 'UNKNOWN' |
| severity_grade | `<enum 'SeverityGrade'>` | 'UNKNOWN' |
| confidence | `float \| None` | None |
| classification_method | `str \| None` | None |

## DefectLocation

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| image_x | `float \| None` | None |
| image_y | `float \| None` | None |
| roi_id | `str \| None` | None |
| band_id | `str \| None` | None |
| physical_x | `float \| None` | None |
| physical_y | `float \| None` | None |
| physical_coordinate_unit | `str` | 'um' |
| sensor_x | `float \| None` | None |
| sensor_y | `float \| None` | None |

## DetectionInfo

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| source_channels | `list[str]` | 独立工厂 list |
| candidate_ids | `list[str]` | 独立工厂 list |
| detection_stage | `str \| None` | None |
| merge_history | `list[dict]` | 独立工厂 list |
| algorithm_version | `str \| None` | None |

## Defect

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| identity | `domain.defect.DefectIdentity` | 必填 |
| geometry | `domain.defect.DefectGeometry` | 独立工厂 DefectGeometry |
| morphology | `domain.defect.Morphology` | 独立工厂 Morphology |
| photometry | `domain.defect.Photometry` | 独立工厂 Photometry |
| classification | `domain.defect.Classification` | 独立工厂 Classification |
| location | `domain.defect.DefectLocation` | 独立工厂 DefectLocation |
| detection | `domain.defect.DetectionInfo` | 独立工厂 DetectionInfo |
| review | `domain.review.ReviewInfo` | 独立工厂 ReviewInfo |

## ReviewEvent

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| review_status | `<enum 'ReviewStatus'>` | 必填 |
| reviewer_decision | `str \| None` | None |
| reviewer | `str \| None` | None |
| review_time | `str \| None` | None |
| comment | `str \| None` | None |

## ReviewInfo

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| algorithm_decision | `str` | 'UNSPECIFIED' |
| review_status | `<enum 'ReviewStatus'>` | 'UNREVIEWED' |
| reviewer_decision | `str \| None` | None |
| reviewer | `str \| None` | None |
| review_time | `str \| None` | None |
| comment | `str \| None` | None |
| history | `tuple[domain.review.ReviewEvent, ...]` | () |

## AlgorithmInfo

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| software_version | `str` | '0.2.0' |
| algorithm_version | `str \| None` | None |
| config_name | `str \| None` | None |
| config_version | `str \| None` | None |
| config_hash | `str \| None` | None |
| run_timestamp | `str \| None` | None |
| execution_time_seconds | `float \| None` | None |
| runtime_environment | `dict[str, str]` | 独立工厂 dict |

## QACheck

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| name | `str` | 必填 |
| status | `<enum 'QAStatus'>` | 'NOT_RUN' |
| message | `str \| None` | None |
| stage | `str \| None` | None |
| mandatory | `bool` | True |

## QualityControl

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| status | `<enum 'QAStatus'>` | 'NOT_RUN' |
| checks | `list[domain.execution.QACheck]` | 独立工厂 list |

## DetectionPlanInfo

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| roi_geometry_status | `<enum 'GeometryStatus'>` | 'NOT_EVALUATED' |
| band_geometry_status | `<enum 'GeometryStatus'>` | 'NOT_EVALUATED' |
| planned_tiles | `int \| None` | None |
| full_tiles | `int \| None` | None |
| skipped_tiles | `int \| None` | None |
| legal_source_pixels | `int \| None` | None |

## ExecutionAttempt

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| mode | `<enum 'PipelineMode'>` | 必填 |
| status | `<enum 'ExecutionStatus'>` | 'NOT_STARTED' |
| plan | `domain.execution.DetectionPlanInfo` | 独立工厂 DetectionPlanInfo |
| qa_status | `<enum 'QAStatus'>` | 'NOT_RUN' |
| qa_checks | `list[domain.execution.QACheck]` | 独立工厂 list |
| reason | `domain.enums.FallbackReason \| None` | None |
| message | `str \| None` | None |
| started_at | `str \| None` | None |
| finished_at | `str \| None` | None |
| execution_time_seconds | `float \| None` | None |

## ExecutionInfo

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| requested_mode | `<enum 'PipelineMode'>` | 'auto' |
| attempted_mode | `domain.enums.PipelineMode \| None` | None |
| final_mode | `domain.enums.PipelineMode \| None` | None |
| status | `<enum 'ExecutionStatus'>` | 'NOT_STARTED' |
| fallback_used | `bool` | False |
| fallback_reason | `domain.enums.FallbackReason \| None` | None |
| fallback_message | `str \| None` | None |
| qa_status | `<enum 'QAStatus'>` | 'NOT_RUN' |
| qa_checks | `list[domain.execution.QACheck]` | 独立工厂 list |
| attempts | `list[domain.execution.ExecutionAttempt]` | 独立工厂 list |

## RegionInfo

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| region_id | `str` | 必填 |
| bbox | `domain.common.BoundingBox \| None` | None |
| pixel_count | `int \| None` | None |
| mask_reference | `domain.common.ArtifactReference \| None` | None |
| contour_reference | `domain.common.ArtifactReference \| None` | None |

## BandInfo

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| band_id | `str` | 必填 |
| name | `str \| None` | None |
| bbox | `domain.common.BoundingBox \| None` | None |
| contour_reference | `domain.common.ArtifactReference \| None` | None |
| mask_reference | `domain.common.ArtifactReference \| None` | None |
| mean_gray_dn | `float \| None` | None |
| min_gray_dn | `float \| None` | None |
| max_gray_dn | `float \| None` | None |
| pixel_count | `int \| None` | None |
| valid | `bool` | False |
| review_status | `<enum 'ReviewStatus'>` | 'UNREVIEWED' |

## ROIInfo

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| status | `<enum 'GeometryStatus'>` | 'NOT_EVALUATED' |
| work_region | `domain.roi.RegionInfo \| None` | None |
| nonwork_region | `domain.roi.RegionInfo \| None` | None |
| review_region | `domain.roi.RegionInfo \| None` | None |
| band_count | `int` | 0 |
| band_list | `list[domain.roi.BandInfo]` | 独立工厂 list |
| mask_references | `dict[str, domain.common.ArtifactReference]` | 独立工厂 dict |
| geometry_source | `str \| None` | None |

## InspectionStatistics

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| total_defects | `int` | 0 |
| count_by_type | `dict[str, int]` | 独立工厂 dict |
| count_by_size_grade | `dict[str, int]` | 独立工厂 dict |
| count_by_severity_grade | `dict[str, int]` | 独立工厂 dict |
| count_by_band | `dict[str, int]` | 独立工厂 dict |
| count_by_roi | `dict[str, int]` | 独立工厂 dict |
| total_defect_area_px | `float \| None` | None |
| total_defect_area_um2 | `float \| None` | None |
| scratch_total_length_px | `float \| None` | None |
| scratch_total_length_um | `float \| None` | None |
| review_statistics | `dict[str, int]` | 独立工厂 dict |

## CandidateAuditRecord

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| candidate_id | `str` | 必填 |
| source | `str` | 必填 |
| initial_geometry | `domain.defect.DefectGeometry \| None` | None |
| current_stage | `str \| None` | None |
| disposition | `<enum 'CandidateDisposition'>` | 'PENDING' |
| filter_reason | `domain.enums.FilterReason \| None` | None |
| filter_message | `str \| None` | None |
| merged_into | `str \| None` | None |
| final_defect_id | `str \| None` | None |

## AuditInfo

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| candidates | `list[domain.audit.CandidateAuditRecord]` | 独立工厂 list |
| events | `list[dict]` | 独立工厂 list |
| source_candidate_count | `int \| None` | None |
| lineage_complete | `bool` | False |

## ImageInfo

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| file_name | `str \| None` | None |
| image_reference | `domain.common.ArtifactReference \| None` | None |
| sha256 | `str \| None` | None |
| width_px | `int \| None` | None |
| height_px | `int \| None` | None |
| container_bits | `int \| None` | None |
| effective_bits | `int \| None` | None |
| byte_order | `str \| None` | None |
| input_format | `str \| None` | None |
| sample_id | `str \| None` | None |

## InspectionTask

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| task_id | `str` | 必填 |
| created_at | `str \| None` | None |
| status | `<enum 'ExecutionStatus'>` | 'NOT_STARTED' |
| inputs | `list[domain.task.ImageInfo]` | 独立工厂 list |
| result_ids | `list[str]` | 独立工厂 list |

## IntermediateResults

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| level | `<enum 'IntermediateLevel'>` | 'STANDARD' |
| original_preview | `domain.common.ArtifactReference \| None` | None |
| work_mask | `domain.common.ArtifactReference \| None` | None |
| nonwork_mask | `domain.common.ArtifactReference \| None` | None |
| review_mask | `domain.common.ArtifactReference \| None` | None |
| band_masks | `dict[str, domain.common.ArtifactReference]` | 独立工厂 dict |
| blackhat_preview | `domain.common.ArtifactReference \| None` | None |
| candidate_preview | `domain.common.ArtifactReference \| None` | None |
| final_mask | `domain.common.ArtifactReference \| None` | None |
| annotated_image | `domain.common.ArtifactReference \| None` | None |

## AutoPolicy

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| primary | `<enum 'PipelineMode'>` | 'roi-bh' |
| fallback | `<enum 'PipelineMode'>` | 'full' |

## InspectionConfig

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| config_name | `str` | 'production_v1' |
| config_version | `str` | '0.2.0' |
| pipeline_mode | `<enum 'PipelineMode'>` | 'auto' |
| advanced_debug | `bool` | False |
| auto_policy | `domain.configuration.AutoPolicy` | 独立工厂 AutoPolicy |
| calibration | `domain.calibration.CalibrationInfo` | 独立工厂 CalibrationInfo |
| intermediate_level | `<enum 'IntermediateLevel'>` | 'STANDARD' |
| algorithm_parameters | `dict` | 独立工厂 dict |
| algorithm_parameter_source | `str` | 'UNCHANGED_REFERENCE_ENGINE' |
| status | `str` | 'MODEL_ONLY_NOT_CONNECTED_TO_ENGINE' |

## InspectionResult

| 字段 | Python类型 | 默认值 |
| --- | --- | --- |
| extensions | `dict[str, Any]` | 独立工厂 dict |
| task_id | `str` | 必填 |
| result_id | `str` | 独立工厂 lambda |
| schema_version | `str` | '1.0' |
| input_info | `domain.task.ImageInfo` | 独立工厂 ImageInfo |
| algorithm_info | `domain.algorithm.AlgorithmInfo` | 独立工厂 AlgorithmInfo |
| calibration_info | `domain.calibration.CalibrationInfo` | 独立工厂 CalibrationInfo |
| execution_info | `domain.execution.ExecutionInfo` | 独立工厂 ExecutionInfo |
| roi_info | `domain.roi.ROIInfo` | 独立工厂 ROIInfo |
| defects | `list[domain.defect.Defect]` | 独立工厂 list |
| statistics | `domain.statistics.InspectionStatistics` | 独立工厂 InspectionStatistics |
| intermediate_results | `domain.intermediate.IntermediateResults` | 独立工厂 IntermediateResults |
| quality_control | `domain.execution.QualityControl` | 独立工厂 QualityControl |
| audit_log | `domain.audit.AuditInfo` | 独立工厂 AuditInfo |

## ExecutionInfo只读派生属性

| 属性 | 来源 | JSON保存 |
| --- | --- | --- |
| final_attempt | 最后一次SUCCEEDED且QA PASS、并与final_mode匹配的attempt；final_mode为None则None | 否 |
| final_plan | final_attempt.plan原对象；无最终attempt则None | 否 |

禁止恢复ExecutionInfo顶层roi_geometry_status/band_geometry_status/planned_tiles/full_tiles/skipped_tiles/legal_source_pixels。带这些键的旧草案JSON会明确报错，防止重复事实源。

## 最终门禁与检查职责

InspectionResult.validate_final() → None / FinalValidationError。Execution QA负责流程安全与attempt采用；QualityControl负责结果字段、资源、统计及保存/发布前完整性。详见设计文档及序列化规范。

## 稳定枚举

### PipelineMode

`auto`, `roi-bh`, `roi-j4`, `full`, `legacy-replay`

### FallbackReason

`BAND_LOCATOR_FAILED`, `BAND_GEOMETRY_INVALID`, `ROI_PLAN_FAILED`, `ROI_CONTEXT_INCOMPLETE`, `SENTINEL_CONSUMED`, `J4_EXECUTION_FAILED`, `J5_EXECUTION_FAILED`, `SOURCE_LINEAGE_INVALID`, `QA_FAILED`, `UNKNOWN_EXCEPTION`

### QAStatus

`NOT_RUN`, `PASS`, `FAIL`, `INCOMPLETE`

### ExecutionStatus

`NOT_STARTED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`

### GeometryStatus

`NOT_EVALUATED`, `VALID`, `INVALID`, `FAILED`

### ScaleSource

`USER_CONFIG`, `CALIBRATION`, `DEFAULT`, `UNKNOWN`

### ReviewStatus

`UNREVIEWED`, `CONFIRMED`, `FALSE_POSITIVE`, `UNCERTAIN`

### SizeGrade

`SMALL`, `MEDIUM`, `LARGE`, `UNKNOWN`

### SeverityGrade

`UNKNOWN`, `LOW`, `MEDIUM`, `HIGH`

### IntermediateLevel

`NONE`, `STANDARD`, `DEBUG`

### CandidateDisposition

`PENDING`, `RETAINED`, `FILTERED`, `MERGED`, `REVIEW`

### FilterReason

`OUTSIDE_WORK_REGION`, `BACKGROUND_NOISE`, `LOW_EVIDENCE`, `USER_REJECTED`, `SAFETY_GATE_REJECTED`, `OTHER`
