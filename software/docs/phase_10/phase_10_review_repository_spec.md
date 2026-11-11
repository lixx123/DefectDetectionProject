# 独立HumanReviewRepository

默认output/reviews/<result_id>/active.json指向<session_uuid>.json；旧会话和全部revision保留，无delete API。每个会话文件为{checksum,state}。state包含元数据、冻结任务、原最终ID集合、records和events；summary/latest为派生投影，不作第二份权威文件。

单一权威状态事务避免session/records/summary多文件半提交：同目录临时文件写入→flush/fsync→os.replace；失败清理临时文件，原状态仍有效。active指针同样原子替换且在新会话落盘后更新。崩溃前未replace的临时文件不会作为有效记录加载。文件系统/硬件故障超出本地原子替换保证，不把checksum当作数字签名。

每个result使用OS字节锁（Windows msvcrt，其他fcntl），进程异常结束由OS释放；锁文件不含账户/PID等身份。锁内重读active和当前revision，expected_revision冲突要求重载，不能覆盖另一实例记录。每次submit一个新UUID/revision，旧record永不删除。不同reviewer修改需明确确认；新会话需用户勾选确认，旧会话可按session_id读取。

加载校验合法JSON/checksum/协议、UUID、result/session身份、task集合digest、完整CandidateKey、record与session全部绑定字段、连续revision、带时区时间、reviewer、decision兼容性、target及几何快照。输入的危险路径/目录转义/符号链接被拒绝。独立导出CSV为latest视图，UTF8 BOM并处理公式样式自由文本；JSON含全部state/history和summary。

不调用或改变JsonResultRepository.save，不向正式包新增审核文件。真实验证库与用户默认审核库分开；QA_PENDING_ONLY只创建132条PENDING，没有任何真实审核record。
