# Phase 6 revision 测试

全部软件367 PASS（原349原样保留+新增18），新旧UI47 PASS。FAST339、GOLDEN26、RELEASE PASS；smoke和pip check exit0。JUnit和原始日志随附gates/及当前目录。新增测试包含双视图真实crop及DN、z序、mask开关、无RAW、1.5倍/1与2px最小框/四角clamp、measurement中心定位与全量对象不变、超限不分配、重复item替换、Band/ROI排除、正式名称及真实RAW只读显示。

新增鼠标测试隔离全局光标位置，避免相同屏幕位置导致旧QTest不产生移动事件；未修改旧测试、未删除或减弱断言。真实显示测试和截图不调用Detector，不启动算法进程。Golden/旧单元fixture原样执行。

原软件app/application/core/domain/config/repositories/regression/scripts及所有已有tests与基线diff为空；原算法765项SHA保护PASS。所有物理Golden与Repository校验继续PASS。人工验收PENDING，Phase7未开始。
