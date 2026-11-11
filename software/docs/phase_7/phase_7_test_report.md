# Phase 7 测试报告

新增40项UI/视图模型/真实历史测试，旧388项文件及断言不变；全量428 PASS。FAST397，GOLDEN29，RELEASE PASS；smoke、pip check PASS。无失败、错误、skip。

覆盖三Tab/空状态；字段ID、measurement bbox、面积、Feret、空类型/严重度、Band/ROI、Tooltip；invalid calibration和计量说明；synthetic原始像素/坐标/独立NPZ mask/缺原图preview/损坏SHA/不变性；上一条下一条/单对象/零对象；统计一致性、缺测量不补零、WORK分母、未分类与百分比、动态3/4/5Band；三筛选清除、五种排序、翻页遵守当前可见顺序、筛选不改全量统计、快速选择隐藏旧控件；正式26_1/26_2全对象浏览与统计原值。

UI截图与工程QA不等同人工验收。8张图与ui_observation.json记录真实包读回和结果摘要不变。旧算法单元测试使用原有fake fixtures；没有对真实RAW调用Detector。旧两项reference_probe仅保留原验证行为，不运行完整算法。外部RAW禁读审计报告在raw_access_guard，机器路径扫描在hardcoded_machine_paths.json。
