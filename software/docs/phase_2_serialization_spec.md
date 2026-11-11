# Phase 2 JSON与配置序列化规范

## 版本与接口

所有结果根对象必须有 `schema_version: "1.0"`。InspectionResult提供to_dict/from_dict、to_json/from_json、save_json/load_json。最小必填业务字段为task_id；result_id缺省生成UUID，完整保存后保持不变。Defect.identity及defect_id必填。缺失可选字段使用dataclass默认值，None序列化为null。

```python
from domain import InspectionResult
result = InspectionResult(task_id="任务001")
result.save_json("result.json")
loaded = InspectionResult.load_json("result.json")
assert loaded == result
```

save_json默认独占创建，已有文件会抛FileExistsError；显式overwrite=True是编码工具的可选参数，不是重新检测覆盖历史结果的生产策略。父目录须由调用者建立，IO异常向上传递。本接口是任务书要求的便捷编解码API，尚非ResultRepository，也未绑定GUI。

## 编码约定

- UTF-8、ensure_ascii=false、null/true/false采用JSON标准；读文件兼容UTF-8 BOM。
- Enum按稳定value编码；不是Python成员名称。例如PipelineMode.ROI_BH编码为`"roi-bh"`，FallbackReason编码为大写原因码。
- 所有对象按声明类型重建，包括嵌套dataclass、Enum、list、dict、tuple。审核history在JSON是数组，加载后恢复tuple。
- 禁止NaN/Infinity、重复JSON键和类型伪装（如valid="false"）；错误包含字段路径。未知枚举值明确报错，不能默默当作AUTO或其他模式。
- dataclass的extensions是JSON兼容字典，中文和嵌套对象原样保留。不支持直接放NumPy数组、图像、Path、datetime、set或任意Python对象。时间戳用带时区的ISO-8601字符串，耗时单位秒；调用方提供真实采集时间，本轮不伪造运行时间。
- ArtifactReference.path可接受Path作为构造输入，但会规范为POSIX相对路径字符串。JSON内所有标准资源引用相对result.json所在目录；不自动将任意绝对路径字符串转换成相对路径。
- float按Python/JSON正常数值精度保存，不为了显示而四舍五入。数据相等使用dataclass值相等；不保证原JSON空白/键顺序保持。

## 扩展兼容

同一schema 1.0中，所有标准记录可忽略但保留未知新增字段；本次冻结前已明确退休的ExecutionInfo顶层plan字段除外，见下文。内部_unknown_fields不输出为专门字段；保存时将新增字段放回原对象层级。已声明字段始终优先。审核/重新标度的模型方法同样保留未知字段。

extensions不与未知字段混合，extensions中的内容保持原样。缺少可选项可加载；缺少必需身份字段、非法枚举、类型错误不会被“兼容性”静默吞掉。

domain/migrations/MigrationRegistry提供register(source,target,fn)和migrate(payload)。加载结果前执行迁移，深拷贝输入，不修改原payload。没有登记的旧版本、未来版本或缺失版本会抛SchemaVersionError；不能擅自将旧算法summary.json视为schema 1.0。

本轮没有实际历史领域schema可迁移，故默认registry为空；单元测试用0.9→1.0演示接口，不注册伪造生产迁移。迁移必须返回声明的目标版本；重复步骤、自迁移和循环链被拒绝。

## 配置协议

configs/loader.py以yaml.safe_load载入InspectionConfig，以独占创建safe_dump写出配置。字段/Enum/可选值规则与领域codec一致。配置只定义模型；不会更改原算法全局参数或运行生产检测。

生产：pipeline_mode=auto、advanced_debug=false、auto_policy.primary=roi-bh、fallback=full。
调试：advanced_debug=true时可选roi-j4/full/roi-bh/legacy-replay。debug.yaml示例选择roi-j4，其AUTO策略字段仍保持roi-bh→full，不表示roi-j4进入AUTO。

InspectionConfig.config_hash()为完整模型（含默认值、未知字段和extensions）的规范JSON SHA256：UTF-8、键排序、紧凑分隔符。不是YAML原始字节哈希；改注释或键顺序不改变语义哈希。改空间尺度/模式等会改变哈希。

空间尺度保存在calibration.spatial_scale_um_per_px。来源默认DEFAULT，非默认数值自动标USER_CONFIG；推荐显式with_user_scale设置，尤其是主动设回3.2时。所有阈值配置本轮为空引用，algorithm_parameter_source=UNCHANGED_REFERENCE_ENGINE，不能据此宣称已绑定原算法。

## 示例与资源限制

examples/phase2_roundtrip.py生成ROI成功和FULL回退两份示例JSON，每份包含ROI/Band、Defect、尺度、统计、审计和attempts；每次运行应使用新的输出目录，避免覆盖。示例没有执行任何检测，资源路径也不代表已有真实图像文件。

本阶段不读取/转换已有算法结果，也不检查引用文件是否存在或校验其像素；这些属于后续适配、存储和安全QA责任。


## schema 1.0冻结前修订规则

本轮仍为schema_version="1.0"，未发布1.1。ExecutionInfo JSON中删除roi_geometry_status、band_geometry_status、planned_tiles、full_tiles、skipped_tiles和legal_source_pixels。所有DetectionPlanInfo数据只存于attempts[].plan。final_attempt/final_plan是只读property，不进入JSON。其他未知字段和extensions原样保留；这6个退休字段若在旧草案JSON顶层出现，加载/重存均报明确ValueError，不能作为未知新增字段回写。

roi_success_result.json与fallback_result.json已在docs/phase2_revision重新生成；原output/phase2_protocol_examples保留为冻结前草案，不覆盖、不自动迁移。

正式发布调用顺序：完成真实Execution QA → 完成Result QC（含必要资源IO验证）→ result.validate_final() → Repository正式保存。codec的save_json/load_json不隐式调用validate_final，以保留草稿/失败状态记录能力；示例显式在保存前和加载后调用validate_final。

validate_final通过返回None，失败抛FinalValidationError，且不修改对象。采用attempt的执行QA与结果整体QC必须分别PASS；面积比较为math.isclose(rel_tol=1e-9, abs_tol=1e-6)，所有分项存在时才核对可选总量。None不自动补0。

回退Band失败示例保留失败ROI/Band：首次ROI计划band_geometry_status=INVALID、ROIInfo.status=INVALID、问题Band.valid=false；FULL自身的plan和成功QA独立记录。失败几何是审计信息，不能被GUI解释为通过生产安全检查。
