# Phase 6 工程验收报告

工程 QA 通过；人工界面审核待完成。基线 `ceefc43c0c48b2fffd3e0c68c55df4eb37aa9c6d`，最终源码指纹 `bbb05ef40e23aaebf75ba7f31d7b42ec3d08480f7932d382f811d8099cedc884`。最终提交回执见 final_commit.txt。

## 功能与证据

- 主窗口/ImageViewer/历史加载/表格/双向联动/Band/ROI/线程：PASS。
- 26_1：36 最终对象；26_2：35 最终对象；正式包均完整加载，不依赖原 RAW，不重跑算法。
- 3/4/5 Band fixture、Calibration invalid、AUTO→FULL 成功回退、无 RAW：PASS。
- 开始检测使用冻结 InspectionService 写临时库；用户点击保存才写正式库。新 ID 不覆盖旧结果；后台失败恢复按钮、保留日志。
- 全部软件测试 349 PASS（旧 320 不改断言，新 29）；FAST 322 PASS；GOLDEN 25 PASS；RELEASE PASS；smoke 和 pip check PASS。无 skip。
- Golden 仍覆盖 6 组样本/模式和 2 个正式包，源集合/掩膜/物理量/audit 语义未变化。schema 1.0、AUTO、原工程 765 项保护均 PASS。
- REAL_ENGINE_REQUIRED=false，REAL_ENGINE_EXECUTED=false，真实算法调用数 0。
- 48 项要求逐条证据见 requirement_checks.json；原始日志、JUnit、门禁报告随附。

## 需要说明的地方

现有服务只有 inspect_and_save，与“先检测、后正式保存”的交互存在接口差异；采用临时标准库桥接，未修改 application 或 Repository。两组历史包没有 original_preview，原图显示不可用、DN 为 —，其余视图正常。已有 annotated_image 含烧录内容，不把它伪装成干净原图。

冻结 Phase 5 门禁报告仍有 phase6_started=false 固定标签，本轮未修改判定规则；本阶段事实以 phase_6_verification.json 为准。该遗留标签不影响测试、schema、算法保护或 REAL 影响判定。

## 性能观察与人工审核边界

最终脚本观察：加载前工作集 71.36 MiB，26_1 加载后 215.64 MiB。5 轮切换后工作集 254.09–264.23 MiB；私有提交 811.37–811.47 MiB。清理后工作集 85.94 MiB。未观察到持续线性增长，不能据此证明不存在任何泄漏。

每轮 Band/ROI/最终图切换及至少 10 个对象选择、缩放和平移。此为离屏脚本交互，非人工操作；资源读取在线程中，Band 大 PNG 解码约 4–5 秒，期间窗口事件循环可响应。未做严格 benchmark。6 张截图 1680×1000 已生成并目视检查中文、布局和图层。截图不加入像素 Golden。

人工仍需审核截图、现场窗口手感和实际 RAW 操作流程。工程 QA 不能替代人工接受。本轮停止，不进入 Phase 7。
