# Phase 4 完整性与安全检查

1. 正式 save 必须通过 result.validate_final：Execution QA 与 Result QC 都 PASS，FAILED/draft 拒绝。
2. 遍历所有模型引用与 portable 扩展引用；要求有效 SHA256。缺失、非文件、hash 不匹配、冲突路径和大小写别名均拒绝。
3. 相对路径拒绝 ..、绝对路径、盘符/ADS、UNC、反斜线混淆、空段、设备名、尾部点/空格、控制字符。逐级拒绝 symlink/junction，resolve 仍须位于根目录内。result_id 限定安全单组件。
4. 临时包和正式包分别重新读取 result.json、validate_final、核对 ID/schema/manifest、所有 hash 和资源覆盖。result/config/provenance 必须列入清单；额外文件、缺文件、hash 错误、危险路径都报告 FAIL。
5. verify 输出 status、result_json_valid、validate_final、manifest_valid、missing_files、hash_mismatches、unsafe_paths、unexpected_files、errors，另明确 missing_logs/warnings。缺失原日志不伪造，包可有效但显示 INSPECTION_LOG_MISSING。日志存在但被删/篡改属于完整性 FAIL。
6. load 默认 full；light 仍解码结果、执行正式门禁、核对元数据、result.json SHA、资源路径/存在性及配置 hash，只省略其他所有文件 SHA 重算。需要全部字节校验时使用 full 或独立 verify。
7. export 首先完整 verify，ZIP 仅包含安全清单中的文件，检查 ZIP CRC、每个成员 SHA/大小、清单一致性，再给 ZIP SHA256。禁止默认包含 RAW/整个 engine；禁止覆盖 ZIP。import 延期，不使用不受检的 extractall。
8. 本轮测试包括真实 Windows junction 逃逸、同 ID 并发保存、注入复制/索引失败、包文件篡改、配置漂移、坏包隔离与索引修复。运行既有 Phase 3 小型参考探针不等于重跑真实算法；持久化验收直接禁止 subprocess。
