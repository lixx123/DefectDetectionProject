# Phase11 异常映射

保留ReviewError/ReviewConflict/RepositoryError等原异常；仅在UI适配。以下均保留完整技术traceback于运行日志；未知异常不向GUI透露str(exc)。已有ValueError输入验证的短单行文本仅在通用验证路径保留，移除绝对路径/Traceback以兼容旧调用。

| Exception / Condition | Error Code | Log Level | User Message | State Rollback / Cleanup | Retryable |
|---|---|---|---|---|---|
| 已知ValueError输入验证（非未知异常） | INPUT_VALIDATION_FAILED | ERROR | 输入数据未通过检查。当前结果不变；检查输入后重试。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| open_raw文件不存在/不可读或InputValidationError | RAW_READ_FAILED | ERROR | 无法读取 RAW。当前结果保留；检查文件存在且可读后重试。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| RAW尺寸检查ValueError/协议标记 | RAW_SIZE_MISMATCH | ERROR | RAW 尺寸不匹配。原结果不变；请选择符合尺寸的文件。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| 冻结validate_raw格式标记 | RAW_UNSUPPORTED_FORMAT | ERROR | RAW 格式不受支持。无法提交审核；请使用 RAW/big/16容器/12有效位文件。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| SHA256/身份不匹配 | RAW_MISMATCH | ERROR | RAW 与正式结果身份不匹配。旧证据已失效；请重新关联正确 RAW，当前不能提交。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| 租约或读取不可用 | RAW_UNAVAILABLE | ERROR | RAW 证据不可用。当前不能提交；检查文件可读后重新关联。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| 检测配置ValueError/ConfigurationError | CONFIG_ERROR | ERROR | 检测配置无效。未产生正式结果；检查配置后重试。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| 明确ROI_DETECTION_FAILED标记 | ROI_DETECTION_FAILED | ERROR | 工作区定位失败。未产生正式结果；请检查输入及配置。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| 检测操作异常 | DETECTION_FAILED | ERROR | 检测执行失败。未保存正式结果；检查输入后可重新检测。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| 历史读取异常 | RESULT_LOAD_FAILED | ERROR | 历史结果加载失败。新结果未加载；检查结果包后重试。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| PackageIntegrityError/RESULT_MISMATCH | RESULT_INTEGRITY_FAILED | ERROR | 正式结果完整性校验失败。拒绝加载或审核；请恢复完整原始结果包。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| save操作异常 | RESULT_SAVE_FAILED | ERROR | 正式结果保存失败。当前临时结果未获得正式审核权限；检查空间和权限后重试。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| 视图/局部资源读取异常 | VIEW_RESOURCE_FAILED | ERROR | 视图资源读取失败。算法结果不变；检查资源后重新切换视图。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| 会话操作异常 | REVIEW_SESSION_FAILED | ERROR | 人工复核会话读取或创建失败。未提交结论；检查审核目录后重试。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| 审核写入I/O异常 | REVIEW_SUBMIT_FAILED | ERROR | 人工复核保存失败。当前任务未标为已处理；重新加载记录后重试。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| ReviewConflict/revision冲突 | REVIEW_CONFLICT | ERROR | 人工复核记录发生冲突。本次未追加结论；重新加载审核记录后重试。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| POLICY_MISMATCH标记 | POLICY_MISMATCH | ERROR | 审核策略不匹配。历史记录只读；使用一致策略后重新加载。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 否，先修复上下文 |
| TEMPORARY_RESULT标记 | TEMPORARY_RESULT | ERROR | 当前是临时检测结果。无法创建正式审核会话；先保存正式结果。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 否，先修复上下文 |
| 已有导出操作异常 | EXPORT_FAILED | ERROR | 导出失败。正式结果与审核记录不变；检查目标位置后重试。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |
| 未映射异常 | UNEXPECTED_ERROR | ERROR | 操作失败，详细信息已写入日志。请检查运行日志后重试；当前不会自动提交结论。详情见日志 | 线程finished清理busy；原子存储不半写；RAW失败解除证据；失败不formalize VM | 是，按提示处理后 |

第二主任务拒绝为WARNING；不存在的可选图像引用沿用明确降级frame.message并写WARNING，不伪造成读取成功。必须资源损坏由worker报ERROR。RAW的既有epoch/result_id/raw_revision完成payload保留：error_detail发失败分类，completed仅作带身份的协议交付，终态FAILED；旧payload丢弃，不误污染新结果。
