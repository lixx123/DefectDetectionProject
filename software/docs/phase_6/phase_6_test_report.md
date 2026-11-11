# Phase 6 测试报告

最终 UI 29/29，全部软件 349/349（旧 320 + 新 29），无失败/错误/跳过。证据 ui_tests.xml、all_tests_final.xml、对应 log。

FAST 322/322，GOLDEN 25/25；RELEASE 自身再次执行 FAST/GOLDEN 并 PASS。两个 reference_probe 仅在全量测试，不执行完整真实检测。Golden Set 仍非盲测集。

UI 覆盖图像/坐标/Fit/1:1/滚轮锚点/平移、独立 overlay 与 final-mask 图层、选择同步、数值排序、缺测量、历史尺度、动态 Band、ROI 缺资源、真实历史36/35对象、后台成功/失败/主线程派发/按钮恢复/关闭保护、临时检测到正式保存、新ID隔离、RAW只读DN及局部真实像素。

中途发现并修正线程回调绑定、测试等待 GIL 饥饿、离屏中文字体、缩放状态读数、最终mask独立图层问题。早期失败不作为通过证据；报告采用最终执行结果。最终源码指纹与 RELEASE 对齐。

smoke 和 pip check 命令均 exit 0。48 项映射见 requirement_checks.json。人工验收 PENDING。
