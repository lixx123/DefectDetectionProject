# 滤光片疵病检测软件 V1.0.0 Windows 工程候选发布版 — Phase13

**本软件已集成独立检测引擎。用户无需安装 Python、开发 .venv 或源码工程。打开符合规格的 RAW 后可以直接执行自动检测。** 当前 Engine 为 reference v1.0.0，Engine Protocol 1.0，输出 schema 1.0。实际部署验收平台为 Windows 11 x64。

## 操作流程

1. 完整解压 DefectInspectionSoftware 文件夹到当前用户可写目录，双击 DefectInspectionSoftware.exe。不要只复制 exe；必须保留 _internal、engines、configs 和 resources。
2. 查看主界面“检测引擎：reference v1.0.0 · 已就绪”，或“帮助 → 关于”。引擎缺失、损坏或不兼容时会禁用检测；仍可加载历史结果和浏览 RAW。
3. 打开 RAW：11276×9200，大端 uint16 容器、12位有效数据。打开后确认“RAW 已就绪”，点击“开始检测”。算法在独立进程运行，界面后台 worker 负责等待，不要强行关闭或同时发起第二个任务。
4. 完成后查看 Band、最终疵病框/编号与列表；滚轮缩放、拖动平移，F 适应窗口，1 原始像素比例。点击行或框定位疵病。
5. “疵病详情”“统计分析”“检测过程 / 审计”展示当前新检测结果。审计中的既有数据限制/lineage告警不会被隐藏。检测结果不是独立盲法物理真值，人工复核仍有必要。
6. 点击“保存正式结果”；成功后结果位于 output/results，可以通过“历史结果”重新加载。临时结果未保存前没有正式审核权限。
7. 人工复核：填写审核者并打开会话；关联 SHA256 匹配的原始 RAW，查看真实局部灰度。人工结论独立保存在 output/reviews，算法结果保留。QA 不代替生产审核。
8. 结果自身的 Engine 版本显示在主窗口结果信息区，历史结果不会因当前 Engine 改变而重新运行；旧 schema1.0 结果仍可加载。

## 离线 Engine 更新、切换和回滚

关闭 GUI。新算法应形成新的 engine_version、algorithm_source_sha256、config_version 和回归证据，不能直接修改当前版本的阈值/文件。

在 PowerShell 中执行（无需 Python；如单位脚本策略阻止运行，请联系 IT 核准，不要绕过策略）：

```powershell
powershell -File .\tools\install_engine.ps1 -Command list
powershell -File .\tools\install_engine.ps1 -Command install -Package '新Engine包目录'
powershell -File .\tools\install_engine.ps1 -Command select -EngineId reference -EngineVersion 1.0.0
```

安装工具先完整复制并校验到新目录，最后原子切换 engines/current.json；旧 Engine 保留。回滚就是 select 旧版本。重新启动 GUI 后查看状态。正式发布只附带 reference v1.0.0；测试 stub 不会交付。不要手工覆盖正在使用的 Engine，也不要在 GUI 中改算法阈值。

## 错误、日志和文件保护

引擎不可用时恢复完整兼容包或回滚。日志：output/runtime/gui_errors.log；每次检测的 ENGINE_<UUID> 目录含 request、process_receipt、engine_receipt、engine_execution.log，以及各 AUTO attempt 日志和资源。失败保留 traceback；先看界面错误码，再查日志。启动异常另见 output/runtime/launcher_error.log。

不要手工删除结果 manifest、附件、人工审核 active/session 文件或 Engine manifest/runtime/payload。迁移先关闭软件并备份整个 output。输入 RAW 只读，未随发布包附带。checksums.sha256 校验静态发布文件；主 ZIP 校验放在 ZIP 旁，避免自引用。


## 发布与安全状态

当前为未签名工程发布版（ENGINEERING_RELEASE_UNSIGNED），部分 Windows 安全策略可能阻止运行。遇到 Smart App Control / WDAC / 单位安全策略拦截，请联系单位 IT 核准运行环境或使用正式签名分发包；不要关闭系统安全功能。GUI 与 Engine 的真实签名状态、SHA256 以随包验收清单为准。

本轮用户指定同批历史处理过的其他 RAW，仅用于重新计算与未知样本路径补充验收，不视为严格未见盲样。异机验收尚未提供，因此当前不是完整 V1 正式验收冻结，不创建最终 v1.0.0 Git Tag。既有 AlgorithmInfo 的 0.2.0 属于冻结算法/配置版本，GUI 发布版本 1.0.0 与其分开记录。


### 滤光片 Excel 台账

保存正式结果时输入 Filter_ID（1–64位字母、数字、-、_、.）及可选备注，取消则不保存。Filter_ID 位于新结果 extensions.filter_metadata；同一滤光片可以有多次检测，Result_ID 是台账唯一键。历史包永不补写、旧包没有 Filter_ID 时留空。

正式 InspectionResult = Source of Truth；Excel = Derived Ledger / Index。output/defect_ledger.xlsx 无需 Office 即可生成。Filter_Summary 一结果一行，Defect_Detail 仅包含正式 LARGE/MEDIUM，SMALL 不写明细，不重新分级。相对 Result_Folder 用于随软件迁移追溯。日期按 UTC 写入真日期单元格。物理单位取每份结果 valid 的声明尺度，Scale_Source / Metrologically_Calibrated 区分配置尺度与计量标定；缺失或无效时物理单位留空。Feret 只导出已有 MAX_FERET 测量。独立人工复核尚未安全聚合，台账 Review_Status 为 PENDING，不代表人工验收。

菜单“打开检测台账”使用系统默认程序。“同步/重建检测台账”从所有校验通过的正式包恢复台账；坏包会报错，不会静默遗漏。Excel 被打开锁定或 I/O 失败时，正式结果仍保留，提示失败并记录日志，关闭 Excel/WPS 后重试。同步使用互斥锁、临时文件、fsync、原子替换和最近一个有效备份 defect_ledger.backup.xlsx。

Final_Judgement / Standard_Version / Performance_Link / Notes 可在台账中维护；保存并关闭 Excel 后同步，将这些注释保存到独立 ledger_annotations.json。删除/损坏 XLSX 可据正式包及该注释文件重建；尚未同步的手工编辑不能从正式包恢复。旧结果可在 Excel 补录 Filter_ID 并将 Filter_ID_Source 设为 LEDGER_OVERRIDE，再同步留档；新结果 Filter_ID 始终以正式元数据为准。迁移时复制整个 output（包含 results、reviews 和 ledger_annotations.json），不要只复制 Excel。
