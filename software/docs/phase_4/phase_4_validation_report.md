# Phase 4 Repository 验收报告

日期：2026-10-21。基线：1aa643d186ab2d5374723786a42193082aee3707。Phase 4 checkpoint：phase4-checkpoint-20261021。

状态：完成 Phase 4，实现 JsonResultRepository 与 Application Service，提交后停止等待人工审核；未进入 Phase 5。

## 实施内容

实现 save/load/list_results/query/find_by_source_sha256/verify/rebuild_index/export_package。正式保存先做 validate_final，完整临时包验证后同卷原子 rename，再完整读取验证；重复 ID 拒绝覆盖，无 delete。索引失败公开 INDEX_UPDATE_FAILED，保留有效包并支持重建。

遍历 domain ArtifactReference 和扩展 portable 引用，校验路径/文件/hash，保留相对路径；归档实际日志、原 hash 匹配的配置快照和恢复来源。manifest 独立于 schema，包内去重，不复制整个 engine、RAW 或未引用大数组。导出检查清单、逐成员 hash、CRC 和 ZIP SHA256。

验收仓库：`D:\疵病检测\DefectInspectionSoftware\output\phase4_validation\repository`。saved_result_count = 2，index_entries = 2，rebuild_status = PASS。output/results 未用作验收库。

|样本|result_id|verify|artifact_count|artifact_total_bytes|对象数|总面积 px²|
|---|---|---|---:|---:|---:|---:|
|26_1|8a363da8-7a3b-4c77-84cf-d13a375c3b15|PASS|57|35859980|36|20356|
|26_2|f15a42a0-c022-47eb-93d8-d0d191939589|PASS|56|12013396|35|17709|

两组 load 后 validate_final PASS，InspectionResult 完全等价，包含 Defect[]、ROI/Band、Statistics、Audit、ExecutionInfo、QualityControl、CalibrationInfo、AlgorithmInfo、ArtifactReference 和 schema。原配置 hash、尺度 3.2 μm/px、最终 roi-bh 和单次 ROI 尝试均保留。缺文件、hash 错误、危险路径、额外文件及缺日志列表均为空。

## 数值文本与语义边界

原冻结 codec 在解码 float 字段时将整数文本转为 float；例如 area_px 297 会再编码为 297.0。两组 result.json 因而不是字节完全相同，但原/新解析后的 JSON 数值内容相同，完整模型也相同。Repository 没有改变算法或物理数值，未为追求字节一致而修改冻结 domain。原 115 个结果目录文件前后 SHA256 不变，正式包的资源字节与原引用 SHA256 一致。

## 历史配置和默认配置处理

历史 Phase 3 运行没有落盘完整配置；没有伪称已存在。冻结配置候选的 canonical hash 与两组原记录均精确匹配：1ddaa23cddeb0adbca24d1b0de2a5d5b094ca3631bb00d7d2284a30aabfb69c7。以 HASH_VERIFIED_HISTORICAL_RECOVERY 归档快照，metadata/config_provenance.json 记录恢复方法及原快照缺失。日志从对应原 AUTO runtime 归档，未伪造。

未来 Detector 只新增一行，落盘其已捕获的实际运行配置；不强制正式持久化。Application Service 在检测前捕获配置并组合 Repository。保持 domain 冻结，因此 InspectionConfig 类的历史默认状态未改；生产服务省略 config 时显式加载 production_v1.yaml，README 明确未来 GUI 不应裸用旧默认配置。旧尺度不因当前 YAML 修改而变化。

## 导出

- 26_1：`26_1_auto_formal_package.zip`，5928613 字节，CRC PASS，SHA256 `a7aae2eb3fad8767208bfba1cfdff6cb3b69b506cad5e9a1be65137dc537f84a`。
- 26_2：`26_2_auto_formal_package.zip`，3541747 字节，CRC PASS，SHA256 `2daab3335516a7d4cf2f37a57868f269d15a266d13c77b4281fe320835270a6a`。

ZIP 根目录包含 result.json、manifest.json、完整 artifacts/logs/metadata，不包含原始 RAW、整个 engine 或大规模临时数组。附 .sha256 文件。导入明确延期 Phase 4.1，没有半实现或不受检 extractall；这是提示词允许的范围选择。

## 验证与保护

- 全部 software tests：255 passed in 84.50s (0:01:24)；原 Phase 3 revision 190 项文件保持不变。
- Phase 1 smoke、pip check、独立模块导入 PASS。
- 原保护 manifest 1317 项文件 SHA256 一致；domain/schema、FilterReason wire enum、旧测试、adapter、pipeline、engine_worker、app/ui 未修改。
- 持久化真实验收期间禁止 subprocess；算法执行次数 0，无 Black-Hat/J4/J5/K8/RAW recovery 重跑。
- 两组既有 revision 目录 115 个文件前后 SHA256 一致，不自动删除 runtime。
- Windows 专项验证了 fsync 写句柄、较短暂存名、真实 junction 防逃逸、临时失败清理和同 ID 并发防覆盖。

结构化证据：phase_4_acceptance.json、phase_4_software_checks.json、phase_4_verification.json。正式提交回执 final_commit.txt 在提交后生成，工作区保持干净。软件代码位于原指定工程；本报告不是人工算法重新验收或独立软件打包认证。
