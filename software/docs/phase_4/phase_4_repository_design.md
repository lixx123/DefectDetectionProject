# Phase 4 Repository 设计

实施基线 1aa643d186ab2d5374723786a42193082aee3707；Phase 4 checkpoint 指向该提交。只实现 JSON 文件仓库，不做数据库、GUI、审核、ImageViewer、报表或 EXE。

`ResultRepository` 抽象与 `JsonResultRepository` 位于 infrastructure/repositories；存储路径、manifest 和引用资源工具位于 infrastructure/storage。Detector 只检测，Repository 只持久化；Application Service 组合两者，未来 GUI 调用服务。Repository 不导入或运行检测算法。

```python
from pathlib import Path
from infrastructure.repositories import JsonResultRepository

repository = JsonResultRepository(Path("output/results"))
record = repository.save(result, source_run_dir=detector.last_run_dir)
loaded = repository.load(record.result_id)  # 默认 full
report = repository.verify(record.result_id)
history = repository.query(sample_id="26", final_mode="roi-bh")
```

Detector 仅新增落盘内存中已捕获的实际配置 `metadata/config_snapshot.json`，不强制写正式历史库。配置写入不改变算法、AUTO、结果 schema 或 QA。服务提供 `inspect_and_save(image_path, config=None)`，省略配置时加载工程 production_v1.yaml；在检测前捕获配置，在保存时按原 hash 核对。

本轮保留 InspectionConfig 类的历史默认状态，以保持冻结 domain 不变。生产流程必须使用 load_config("configs/production_v1.yaml") 或默认加载它的 InspectionService；未来 GUI 不应裸用旧默认配置。已有历史配置不会因当前 YAML 状态或尺度变化而变化。

save 默认需要实际运行快照，可显式传 config_snapshot，或读取 source_run_dir/metadata/config_snapshot.json；缺失/不匹配则 ConfigSnapshotError，绝不静默读取当前 YAML 替代。配置名、版本、canonical hash、模式、CalibrationInfo 都必须与结果一致。

Phase 3 revision 旧目录没有实际落盘快照。两组 AUTO 的冻结 InspectionConfig 候选 canonical hash 与原记录均为 1ddaa23cddeb0adbca24d1b0de2a5d5b094ca3631bb00d7d2284a30aabfb69c7，精确匹配后以 HASH_VERIFIED_HISTORICAL_RECOVERY 归档，并记录原快照缺失与恢复方法；这是有 hash 证据的历史恢复，不伪称当时已捕获。日志从原对应 AUTO runtime 目录读取，资源从 revision 结果根目录读取，二者可分别通过 log_source_dir/source_run_dir 提供。

原始 InspectionResult 不增加字段、不重写路径。保存后直接完全等价回读。ResultSummary、SaveRecord、VerificationReport、RebuildReport、ExportRecord 都是 repository 类型，不属于 schema 1.0。

导出包含全部 manifest 声明的正式包文件，拒绝覆盖目标 ZIP，逐文件 hash 与 CRC 校验后给出 ZIP SHA256 及 sidecar。import_package 明确延期 Phase 4.1，本轮无半实现，也无 delete()。

索引是可修复缓存，正式包是事实源。查询缓存时核对目录集合、manifest 摘要与 result.json SHA256；失效后从正式结果进行完整门禁/完整性校验再重建。更新失败返回 INDEX_UPDATE_FAILED，包仍有效。rebuild 单个损坏包会跳过并结构化报告，其他包继续。保存/索引使用排他锁；进程异常中止留下的锁/暂存目录不自动删除，避免误删仍活跃任务，需人工核对后处理。相同 result_id 并发只允许一个成功。

异常：RepositoryError、ResultAlreadyExistsError、ResultNotFoundError、PackageIntegrityError、ManifestError、UnsafeArtifactPathError、RepositoryIndexError、ConfigSnapshotError。verify 返回详细报告而非 bool，load 拒绝不合格包。索引自动修复的原因、跳过坏包和更新错误均公开报告。
