# Phase 4 manifest 协议

package_format_version = 1.0，与 InspectionResult.schema_version = 1.0 独立。manifest 不注入 domain。

字段：schema_version、result_id、task_id、saved_at（含时区 UTC）、software_version（原检测软件版本）、algorithm_version、config_name、config_version、config_hash、source_file_name/file_name、sample_id、source_sha256、final_mode、fallback_used、defect_count、total_area_px、artifact_count、artifact_total_bytes、package_files、config_snapshot_origin、missing_logs。

package_files 每项为 relative_path、sha256、bytes、role。role 为 result/artifact/log/config/config_provenance。按相对路径排序，不包含绝对路径；artifact 计数与字节数仅汇总唯一引用资源，不将 result/config/log 算入 artifact。

manifest 不列自身 SHA256，避免循环自引用；清单精确覆盖包内其余正式文件。它不是数字签名；SHA256 用于文件一致性与损坏检测，不宣称能抵御连同 manifest 一起重写的恶意伪造。

manifest 元数据与 result 逐字段核对，资源集合/预期 SHA 与 ArtifactReference 核对，配置快照的 canonical hash 与结果原记录核对。历史结果的 algorithm_info/software_version/config_hash 保持原值，不改写成本轮软件或新 YAML 的值。

result.json 保存自身 domain 语义；saved_at、索引和存储来源均在仓库协议中，不改变审计、物理量或 ArtifactReference。
