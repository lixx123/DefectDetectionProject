# Phase 6 线程约定

InspectionController 位于 GUI 线程，每次 operation 创建 QThread 和 InspectionWorker。线程开始运行 worker.run；success 使用显式 QueuedConnection 回到 Controller 的 @Slot(object)，再向 MainWindow 的 @Slot(str,object) 派发。QPixmap 和 QWidget 只在主线程创建/更新，QImage、RAW memmap 读取、Repository 校验、保存和资源解码在工作线程。

finished → thread.quit、worker.deleteLater；thread.finished → 清理引用、thread.deleteLater、busy=false。busy 存续至线程真正结束，防止先收到结果信号就重入下一任务。关闭事件忙时拒绝，禁止 QThread.terminate、杀算法进程。窗口正常退出清理临时库及 RAW 映射。

测试记录 worker Python thread ID 不同于 GUI ID，并验证 GUI completed 回调位于主线程；耗时 fixture 期间 Qt timer 持续触发，异常日志/信号/按钮恢复均检查。测试事件泵使用短 time.sleep 释放 GIL，避免 QTest.qWait 紧循环饿死 Python 工作线程。真实应用 app.exec 使用正常 Qt 事件循环。
