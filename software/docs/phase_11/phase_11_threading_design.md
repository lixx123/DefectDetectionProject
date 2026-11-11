# Phase11 线程与生命周期

保持单InspectionController、QThread和InspectionWorker；没有新线程池/取消框架。submit忙时返回False并记TASK_REJECTED。状态IDLE→RUNNING→SUCCEEDED/FAILED；busy在finished统一恢复。completed/error_detail在GUI线程消费，worker/thread使用deleteLater释放；每次操作新operation_id，不复用旧signal连接。Qt heartbeat、shiboken对象释放、busy时拒绝关闭、过期裁剪丢弃都有真实窗口测试。

| Operation | Main thread / Worker | Can block? | Busy guarded? | Success signal | Failure signal | Cleanup | Stale-result protection |
|---|---|---|---|---|---|---|---|
| open_raw | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error + error_detail | finally finished/deleteLater/busy=False | 只在成功后替换旧RAW/VM |
| detect | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error + error_detail | finally finished/deleteLater/busy=False | 互斥，staging身份 |
| history | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error + error_detail | finally finished/deleteLater/busy=False | 忙结束后才弹列表 |
| load_history | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error + error_detail | finally finished/deleteLater/busy=False | 完整正式校验成功后显示 |
| save | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error + error_detail | finally finished/deleteLater/busy=False | 成功reload才替换VM |
| view | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error + error_detail | finally finished/deleteLater/busy=False | 互斥，保持当前VM |
| detail_frame | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error + error_detail | finally finished/deleteLater/busy=False | result/selection/mode/revision |
| viewer_detail | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error + error_detail | finally finished/deleteLater/busy=False | viewer/revision/provider identity |
| audit_index/query/candidate_frame | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error + error_detail | finally finished/deleteLater/busy=False | epoch/query/image revision |
| admission_result/query/frame | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error + error_detail | finally finished/deleteLater/busy=False | epoch/query/image revision |
| human_session | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error + error_detail | finally finished/deleteLater/busy=False | epoch/result context |
| human_save | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error + error_detail | finally finished/deleteLater/busy=False | epoch/task identity/revision |
| human_raw | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error_detail + 带身份completed失败payload | finally finished/deleteLater/busy=False | epoch/result_id/raw_revision |
| human_image | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error + error_detail | finally finished/deleteLater/busy=False | epoch/task/image revision |
| human_export | worker：I/O/hash/CPU；GUI：控件绘制 | worker可耗时，GUI不等待 | 是，同一controller | completed | error + error_detail | finally finished/deleteLater/busy=False | 冻结状态快照 |

ImageViewer的定时器只收集有界裁剪坐标，实际crop进入共享worker。正在执行时合并最新请求，过期结果不落图。QImage可在worker生成，QPixmap只在GUI创建；单像素DN在空闲时GUI轻量读取；busy期间显示不可用，空闲后自动恢复最近光标DN，避免等待后台RAW租约锁；错误有统一反馈。独立未接controller的ImageViewer保留同步调用兼容；应用主窗口已接controller，其他局部viewer不直接持有整图RAW。

失败打开RAW保留旧结果；thumbnail失败清mmap。历史损坏先拒绝正式加载，审核不可用。保存异常不替换临时VM或授予FormalResultBinding。Repository原子发布与UI reload为原有两个边界：若发布成功但reload/显示失败，已发布包可完整存在；不自动删除正式历史，应修复后从历史结果重新加载。新增测试证明该包完整且VM仍临时。

人工写入由冻结Repository锁与原子替换保证，失败不增revision/PENDING，支持安全重试；真实optimistic conflict/磁盘写失败均测试。RAW关联失败在开始替换时先清旧lease/图像/提交能力。旧RAW返回清lease或忽略错误；不改ReviewAccess/FormalResultAuthority/审核协议。busy时close忽略，完成后清mmap/lease与临时staging再退出，不支持强制取消。
