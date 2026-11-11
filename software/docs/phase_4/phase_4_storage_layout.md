# Phase 4 存储布局与发布

```text
output/runtime/<run_id>/                  检测工作目录；不自动删除
    metadata/config_snapshot.json        本次实际内存配置
    logs/inspection.log
    engine/...                           不整包归档
output/results/                          可配置；未来正式库默认相对路径
    .save_<result_id>.lock                保存排他锁，完成后移除
    .tmp_<nonce>/              同卷暂存，只清理本调用拥有的暂存
    <result_id>/
        result.json                      schema 1.0，语义不变
        manifest.json                    独立存储协议
        artifacts/...                    保持原相对路径
        logs/...                         实际运行日志
        metadata/config_snapshot.json
        metadata/config_provenance.json
    index.jsonl                          可重建缓存
```

验收专用 root 是 output/phase4_validation/repository/，绝不污染 output/results。使用 Phase 3 revision 的 26_1_auto 和 26_2_auto；不重新计算算法。

保存顺序：validate_final → 检查 result_id/配置 → 排他锁 → 同卷暂存 → 校验并复制所有正式/扩展 ArtifactReference → 实际配置和日志 → result.json → manifest → 重新读取完整校验 → os.rename 发布 → 再次完整校验 → 更新索引。

不提供 overwrite；已有 ID 必须报 ResultAlreadyExistsError，历史修订使用新 ID。同一 RAW hash 可以对应多个 ID。结果目录发布后 Repository 视为不可变；不对正式目录执行删除或更新。

所有写入均关闭并 fsync，再进行同卷目录 rename。读者只能看见完整正式目录。常规发布前失败只清理本次 .tmp_ 目录，不留正式半成品；索引失败不能撤销有效包。外部修改发生在发布后而导致复核失败时保留可诊断的正式目录并报 PackageIntegrityError，不以回滚名义永久删除历史结果。此实现针对本地文件系统进程并发，不承诺断电下所有磁盘/网络卷控制器的事务持久性。

只复制显式引用文件、实际运行日志及配置元数据；同包同 path/hash 只复制一次，不跨包去重。未知扩展中的 {path, sha256} 资源同样纳入覆盖检查。整个 engine、未引用 RAW、J4 tile 和 fused_blackhat.npy 不会自动进入包。
