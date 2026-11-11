# 人工结论语义

- CONFIRMED_DEFECT：确认当前对象具备真实疵病性质；对Candidate不等于声明它是最终集合外的独立漏检。
- FALSE_POSITIVE：人工认为该对象不是真实疵病；原Defect/Candidate永久保留。
- DUPLICATE_OF_EXISTING_DEFECT：与当前结果已有最终Defect重复/附属；必须显式选有效target，Defect不能选自身。空间关联仅优先展示，不自动选中。需要二阶段确认。
- NEW_MISSED_DEFECT：仅Candidate允许，明确表示当前最终集合外的独立新疵病；保存完整初始证据，不生成正式ID或修改Defect[]，需要明确确认。
- UNCERTAIN：已经处理但仍不能判断；可由后续专家追加revision。

Defect允许除NEW_MISSED外四类；Candidate允许五类。非duplicate不能携带target。无效finalID一致性任务允许上述Candidate审核，原错误finalID留在冻结evidence中；不伪装None，不归入普通孤立任务。

对象任务状态PENDING/REVIEWED/UNCERTAIN/STALE与结论枚举分离；UNCERTAIN计入已处理，单列数量。全部处理仍有不确定时明确提示。任务标签只覆盖准入队列，不是整幅图完整GT，不能由此宣称整体准确率/召回率/漏检率。
