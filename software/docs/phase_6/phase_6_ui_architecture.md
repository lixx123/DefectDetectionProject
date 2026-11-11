# Phase 6 UI 架构

MainWindow 管理布局和操作状态；InspectionController 组织稳定服务调用；InspectionWorker 在 QThread 执行 I/O、服务和显示资源解码。ResultViewModel 只读投影最终 Defect[]，不把 audit candidates 放入主表。ImageViewer 只认识 DisplayFrame 和 Overlay，不解析完整领域对象。DefectTableModel 使用数值排序角色，缺测量显示 —。

入口继续使用 `python -m app.main`，app/ 未修改。默认正式库为工程 output/results；历史验证使用 Phase 4 output/phase4_validation/repository。可注入 Repository 和 service_factory 测试。

## 检测与保存接口差异的处理

冻结 InspectionService 仅提供 inspect_and_save，没有单独 inspect。Controller 将标准 JsonResultRepository 指向本次窗口的系统临时目录，调用该服务完成检测、验收并写临时包，加载后显示。用户明确点击“保存正式结果”才调用正式 Repository.save，以临时包里的实际 config_snapshot 和日志作来源。失败草稿不能入库，重复 ID 不覆盖，重新检测使用 Detector 新生成的 ID。

临时包不是正式历史结果，安全关闭时清理；原检测运行目录和开发日志保留。额外临时包写入和重新校验有 I/O 成本，但不改冻结 application/core/repository 语义。窗口忙时不切换任务、不退出，不强杀引擎。所有领域对象只读，没有审核写回。

## 缺少原图的真实情况

两组 Phase 4 正式包 original_preview 均为 null，原 RAW 不要求存在。原图显示“原始图像不可用”，DN 为 —。FINAL 使用中性底图、独立 final-mask 图层和独立 bbox；不把已有带编号 annotated_image 当成干净原图。Band/ROI 从正式引用读取，表格、详情和统计仍有效。未增加假预览，也未修改冻结包。

## 边界

未修改原算法、schema、enum、配置、AUTO、应用服务、持久化实现和 Golden 物理证据。未进入 Phase 7。Phase 5 门禁生成器的 `phase6_started=false` 及文字是原阶段遗留固定标签；本轮阶段事实由 phase_6_verification.json 记录，不改门禁判定来消除该历史标签。
