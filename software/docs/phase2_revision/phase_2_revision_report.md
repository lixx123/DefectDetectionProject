# Phase 2 修订与正式冻结报告

日期：2026-10-20（Asia/Shanghai）。状态：修订实现与工程验收完成，等待人工审核；未进入Phase 3。
本次属于schema 1.0冻结前修订，仍保持schema_version="1.0"，不引入1.1。

## 修改与结果

1. ExecutionInfo改为继承Record，删除顶层6个重复计划字段。DetectionPlanInfo唯一事实源为ExecutionAttempt.plan；final_attempt/final_plan为只读property，不序列化、不复制计划。
2. 修复Band失败回退示例：首次ROI_BH计划的Band几何INVALID、ROIInfo INVALID，失败Band.valid=false；保留Band及相对mask引用供审计（方案A），FULL自身计划独立保存。
3. 新增InspectionResult.validate_final()与FinalValidationError，统一正式结果出口检查。草稿仍可构造/编解码，正式保存前由后续Application/Repository显式调用门禁。
4. 明确Execution QA与Result QC职责分离。执行安全决定attempt能否采用；结果QC决定输出是否具备保存/发布完整性。最终二者必须PASS，且validate_final通过。
5. 重生成两份纯数据JSON示例，保存前和加载后均通过validate_final并round-trip一致。

## 门禁范围

- Defect数量与统计一致、ID唯一；重新检查可变对象修改后的嵌套约束。
- 正式结果必须执行SUCCEEDED、最终模式非空、执行QA PASS，最后attempt成功且QA PASS并与final_mode一致。
- AUTO采用ROI_BH只允许一次ROI_BH，ROI/Band计划VALID，ROIInfo VALID且生产Band存在并有效。
- AUTO采用FULL严格ROI_BH→FULL，首次不得成功且PASS，首次reason必须等于fallback_reason，FULL必须成功且PASS。
- BAND_GEOMETRY_INVALID对应首次Band几何INVALID/FAILED及失败ROIInfo；保留的失败Band不得全部伪装为valid=true。
- 审计lineage_complete必须为true，源数、源ID唯一性及最终Defect指向有效。
- 可用的像素/物理面积总量必须与分项求和一致，math.fsum加math.isclose(rel_tol=1e-9,abs_tol=1e-6)。未知值不补0，零缺陷合法结果可以通过。
- Result QC必须独立PASS；validate_final不改写QA/QC状态。

## 范围限制

validate_final为纯数据门禁，不读mask文件、不验证真实资源存在或像素，也不运行算法。后续Application/Infrastructure必须完成真实资源检查后填入Result QC，本轮没有实现Repository。示例中的相对mask路径是数据声明，不代表已经生成真实检测资源。

codec.save_json仍可保存草稿，不自动调用validate_final；不能将codec调用等同正式发布。正式调用顺序是最终Execution QA PASS、Result QC PASS、validate_final通过，再由Application/Repository保存。

原Phase 2旧样例文件不覆盖。退休的顶层6个plan键若出现在旧草案JSON，明确拒绝并提示改用attempts[].plan，避免通用未知字段机制把重复数据源写回；其他未知字段及extensions完整保留。没有正式生产旧schema依赖，不引入推测迁移或1.1。

## 验证

- 全部新软件tests：99 passed in 0.24s（原56项 + 新43项）。
- python -S纯标准库示例：通过，ROI成功与FULL回退均通过正式门禁/JSON往返。
- Phase 1 smoke：启动、保存截图、正常退出，退出码0；已目视检查中文窗口正常。
- pip check：通过，无依赖冲突。
- 1298个保护文件SHA256全部相同，无变化。
- 本轮未执行原算法生产检测，没有修改原算法/阈值/两级ROI/J4/J5/K8/RAW recovery，也没有修改UI或新增生产检测功能。

保护清单在protected_file_manifest.json；包含前轮765个原算法、原v4/基线结果与Phase 1入口保护文件，补充新工程baseline中的源码快照、冻结结果和清单/指标；排除历史测试临时目录，不声称检查了所有历史输出或所有RAW本体。

## 回滚与交付

修订前Git工作区干净，既有Phase 2提交f756e7d已核对；修改前checkpoint为7060762。
正式修订提交hash见同目录final_commit.txt。该回执在提交完成后生成，不纳入Git以避免自身hash循环；代码、文档、示例、测试和验证JSON均在修订提交中。

独立交付目录：docs/phase2_revision/，包含本报告、测试报告、verification.json、两份示例JSON、保护清单、日志、窗口截图和提交回执。
同时更新四份Phase 2设计/字段/序列化/测试文档、README与CHANGELOG。原冻结基线未改。

按任务书停止在Phase 2，等待人工审核，不进入Phase 3。
