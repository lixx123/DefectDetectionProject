# Phase 2 领域模型与生产策略设计

日期：2026-10-20。schema 1.0冻结前修订并形成冻结实现；待人工审核。仅数据协议、配置和状态校验，未进入Phase 3。

## 结构和选择

使用标准库dataclass与StrEnum，不引入Pydantic。domain不依赖Qt、OpenCV、NumPy或PyYAML；configs/loader.py是独立YAML适配器。纯Python示例可用 `python -S -m examples.phase2_roundtrip <新的输出目录>` 执行。

InspectionResult聚合ImageInfo、AlgorithmInfo、CalibrationInfo、ExecutionInfo、ROIInfo、Defect[]、InspectionStatistics、IntermediateResults、QualityControl和AuditInfo。InspectionTask单独记录任务状态及历次result_id。所有新增检测都应生成新result_id，模型默认UUID；不把重新检测解释为覆盖上一次结果。

Defect按identity/geometry/morphology/photometry/classification/location/detection/review/extensions分组；size_grade和severity_grade使用不同枚举。没有计算的指标用None，不能用0代替缺失值。Defect不自动从面积/长度猜测类型或工业严重度。

## 生产与调试

正式配置 `pipeline_mode: auto`，AutoPolicy固定primary=roi-bh、fallback=full。没有roi-j4中间步骤。普通配置禁止显式非AUTO模式；只有advanced_debug=true时才允许roi-bh、roi-j4、full和legacy-replay。

ExecutionInfo.requested_mode是请求；attempted_mode保留第一次尝试，AUTO只能为ROI_BH；final_mode是最终采用的模式。状态尚未完成或失败时final_mode=None。fallback_used是采取安全回退的事实，不能据此将整个任务标成FAILED。

ExecutionAttempt[]按时间顺序保留各次运行的模式、状态、QA、计划、原因和耗时。ROI安全检查失败但full通过时：任务SUCCEEDED、最终QA PASS、final_mode=FULL；首次ROI失败QA仍在attempts[0]中。full也失败则任务FAILED、final_mode=None，保留回退原因和full失败详情。允许在预检阶段记录ROI失败，不假装J4已执行。

QACheck提供name/status/message/stage/mandatory。总体PASS不能带有尚未通过的必需检查。模型允许尚未填入具体检查的摘要状态；Phase 3必须接入真实安全检查，不能把默认空列表当作已经验证了所有安全条件。

ExecutionAttempt.plan是DetectionPlanInfo的唯一事实源。ExecutionInfo直接继承Record，不再含几何状态、图块数或legal_source_pixels等计划字段。final_attempt是最后一次成功且QA PASS、并与final_mode一致的attempt；final_plan只读返回该attempt.plan的原对象引用，不复制数值、不序列化property。final_mode为空时二者为None。最终门禁还要求该attempt就是最后一次尝试，不能执行FULL后再采用之前的ROI。planned_tiles+skipped_tiles=full_tiles（字段齐全时强制），legal_source_pixels不是缺陷面积。

枚举FallbackReason覆盖任务书要求的10种原因。fallback_message保存具体异常说明。新增原因需要增加枚举并维护协议兼容性，不用自由字符串替代稳定原因码。

LEGACY_REPLAY只表示历史复现/基线验证，不能成为AUTO的实际模式。本轮没有改动原入口，也未将新策略接入原算法；它是未来生产协议，而非现已实现的生产功能。

## 尺度和测量

用户默认空间尺度3.2μm/px，唯一Python默认常量位于domain/calibration.py的“用户输入变量区”；三种YAML显式提供同一配置值。推荐修改YAML或调用CalibrationInfo.with_user_scale()，不改算法函数。

默认scale_source=DEFAULT，valid=true表示用户声明的换算尺度在数值上可用，不表示完成物面计量标定。reference_plane=USER_DECLARED、metrologically_calibrated=false保留这一区别。用户改为非默认值会标USER_CONFIG；即使主动设回3.2，with_user_scale也保留USER_CONFIG。该方法清除过期calibration_id/time及计量标定标志。经过正式标定的来源可标CALIBRATION，但本轮不生成标定证据。

DefectGeometry.with_calibration()只由像素量生成物理量：长度/宽度/等效直径乘尺度，面积乘尺度平方。尺度valid=false时清空这些衍生物理值，像素值不变。未计算宽度等仍为None。序列化加载不自动重算旧尺寸；改变尺度后必须显式生成新几何量/新结果，禁止让旧结果悄悄改变。

物理坐标physical_x/y默认单位um，另带physical_coordinate_unit；只有建立坐标原点/映射后才赋值，不能只凭3.2直接假定物面位置。长度算法和面积算法分别记录在geometry.length_method/area_method，防止把Feret当中心线长度或bbox面积。

## ROI、资源和审计

ROIInfo保存工作/非工作/复核RegionInfo、BandInfo[]及相对资源引用；band_count必须与列表长度相同，band_id在结果内唯一。Band和缺陷坐标都在原图像素坐标系，bbox为左闭右开[x0,y0,x1,y1)，不随显示缩放。

ArtifactReference只允许相对于result.json所在目录的路径，支持可选SHA256、媒体类型和坐标系。禁止机器绝对路径、盘符、UNC、URL或..跳出目录。原RAW若不随结果搬运，ImageInfo保留file_name/sha256，image_reference可空；后续由应用定位源文件，不能在JSON中偷塞绝对RAW路径。

IntermediateResults的NONE/STANDARD/DEBUG仅控制中间图像保留级别，不能删除关键候选审计或最终量测必需的mask引用。引用声明不意味着文件存在，资源落盘/哈希验签由后续Infrastructure承担。本阶段示例里的mask路径是演示引用，不附带真实检测mask。

CandidateAuditRecord保存源ID、初始几何、处理阶段、去向、过滤原因、合并目标和最终Defect ID。FILTERED必须有FilterReason；MERGED必须有目标。AuditInfo包含完整候选记录与通用事件；当lineage_complete=true时，源数量必须与记录数相等、(source,candidate_id)不得重复、final_defect_id必须存在。该结构只能校验所提供的数据自洽，不能替代原算法的逐源像素QA。

ReviewInfo为冻结dataclass，reviewed()返回新快照，algorithm_decision不可通过普通字段赋值改写。history以元组追加ReviewEvent，不移除旧人工结论。它是应用约束而非防篡改安全系统；后续Repository还需保存历史版本。extensions与未知新增字段在审核/重新换算后仍保留。

## 对任务书合理性问题的处理

1. 默认3.2可执行，但不能把它直接称为已标定物面比例。以用户声明尺度和计量标定标志区分，无需阻塞本次开发。
2. “回退后采用full”需以full完成且QA通过为前提；模型额外表达full失败/取消，避免错误成功。
3. 本轮没有灵敏度参数验证依据，因此high_sensitivity仅完成同结构配置，没有新设门限，也不宣称实际提高灵敏度。
4. 未来未知字段可以保留，但未知运行模式/原因枚举不应静默接受，未知schema需显式迁移。详细兼容规则见序列化规范。

Phase 2完成后按提示词停止，等待人工确认，不进入Phase 3。


## 正式结果冻结门禁

新增InspectionResult.validate_final()，成功返回None，失败抛FinalValidationError（ValueError子类）。不修改对象、不补统计、不将None补0、不读取资源文件、不运行算法，也不会自动将QA或QC改为PASS。构造与JSON codec仍允许中间/草稿对象，因此save_json是编码便捷接口，并不代表发布；后续Application/Repository正式保存前必须先调用门禁，本轮不实现Repository。

门禁重跑可变模型的嵌套类型及构造约束，再检查：Defect数量/ID、执行成功和最终attempt、AUTO严格顺序和回退原因、生产ROI/Band有效性、审计链完整与指向、面积总和、Result QC PASS。正式结果必须同时满足Execution QA PASS、Result QC PASS与validate_final PASS；失败任务可保留草稿但不能通过门禁。

AUTO采用ROI_BH必须恰有一次ROI_BH尝试，ROI和Band几何VALID、ROIInfo VALID且存在有效生产Band。本轮BandInfo列表按生产参与集合解释；非生产/失败几何留在失败定位审计中。AUTO采用FULL必须依次ROI_BH、FULL，首次不得成功且PASS，其reason必须与fallback_reason相同，FULL必须成功且PASS。回退不等于软件故障。

当原因是BAND_GEOMETRY_INVALID，首次plan.band_geometry_status必须INVALID或FAILED；ROIInfo同样INVALID/FAILED，保留band_list等几何（方案A），至少将有问题的Band.valid标false。FULL计划是独立的attempt.plan；它不因未采用ROI就伪造ROI几何VALID。其他原因触发FULL时仍可保留实际合法的ROI信息，不一律清空或标无效。

审计lineage_complete必须为true且源数与记录一致，来源/ID不重复，所有非空final_defect_id都在当前结果内。面积统计采用最终对象实测面积直接求和；所有分项非None且总量提供时，math.fsum后以rel_tol=1e-9、abs_tol=1e-6比较。像素与物理面积分别检查。分项缺失时跳过无法判断的和，不推断为0；显式零缺陷且审计完整是合法结果。

## 执行安全QA与结果QC边界

Execution QA决定attempt是否可采用：Band/ROI合法性、计划/halo/context完整性、sentinel安全、J4/J5执行与source lineage及回退条件。ExecutionInfo中的QA是最终采用执行的摘要；失败首次ROI的QA仍独立保存。

Result QualityControl决定结果是否可正式保存/发布：defects/statistics、输出字段、mask和其他资源存在、审计链、序列化和后续存储前完整性。两者可复用QACheck值类型，但检查范围与状态不互相替代。validate_final执行可在纯数据层判定的独立一致性检查；资源存在性/哈希由后续Application/Infrastructure验证并填写Result QC。本轮示例的QC仅声明纯数据自洽，示例相对资源并不存在，不代表已验证真实文件发布条件。

## 草案兼容与冻结

本次属于schema 1.0冻结前修订，保持1.0，不引入1.1。原Phase 2草案顶层6个plan字段已退休，若旧JSON仍包含则明确报错并提示使用attempts[].plan，防止被通用未知字段保留机制重新写回。没有静默丢弃或猜测合并冲突值；既有草案文件保留，正式示例在docs/phase2_revision独立重生成。其他未知新增字段与extensions仍保持原位往返兼容。
