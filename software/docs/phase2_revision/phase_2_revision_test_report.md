# Phase 2 修订测试报告

日期：2026-10-20。全部新软件测试99项通过（原56项 + 修订新增43项），无失败。
执行命令、退出码、耗时及保护结果见phase_2_revision_verification.json；原始测试输出见logs/all_software_tests.log。

## 任务书20项验收映射

| 项目 | 验证证据 |
| --- | --- |
| 1. ExecutionInfo不再含plan字段 | test_execution_has_no_copied_plan_fields |
| 2. final_plan来自最终成功attempt | test_final_plan_is_actual_attempt_plan_not_a_copy（两个分支） |
| 3. ROI成功返回ROI计划 | 同上，fallback=false |
| 4. FULL回退返回FULL计划 | 同上，fallback=true |
| 5. 无效原因与VALID Band矛盾拒绝 | test_band_geometry_reason_cannot_coexist_with_valid_plan |
| 6. 回退ROIInfo INVALID | test_fallback_preserves_failed_geometry_for_audit |
| 7. 失败Band不得标有效 | 同上；test_invalid_band_fallback_cannot_claim_all_preserved_bands_are_valid |
| 8. 数量不一致拒绝final | test_count_mismatch_is_a_serializable_draft_but_not_final |
| 9. AUTO ROI成功但几何INVALID拒绝 | test_auto_roi_success_requires_valid_plan_geometry（ROI/Band分别测试） |
| 10. AUTO FULL未标fallback拒绝 | test_auto_full_cannot_hide_fallback |
| 11. 首次reason缺失/不同拒绝 | test_full_first_attempt_reason_must_match_fallback（两种值） |
| 12. FULL最终必须成功+PASS | test_full_final_attempt_requires_success_and_pass（状态/QA分别测试） |
| 13. ROI失败FULL成功整个任务可成功 | test_fallback_preserves_failed_geometry_for_audit与示例final gate |
| 14. lineage不完整拒绝final | test_incomplete_lineage_is_not_final |
| 15. 面积总量不一致拒绝 | test_area_sum_mismatch_rejected（px²/um²） |
| 16. 正常ROI示例final PASS | test_valid_examples_pass_final_gate_and_roundtrip，fallback=false |
| 17. 正常FULL示例final PASS | 同上，fallback=true |
| 18. JSON round-trip一致 | 同上、原有单元测试、独立python -S示例 |
| 19. extensions及未知字段保留 | test_unknown_extensions_survive_gate_and_roundtrip及原有测试 |
| 20. Phase 1 smoke仍通过 | logs/phase1_smoke.log，退出码0，phase1_smoke.png目检正常 |

额外验证：无最终模式时final_plan为空；不得在FULL执行后退选先前ROI；计划引用不复制；重复Defect ID及可变审计记录再次校验；面积容差边界；None不补0；合法零缺陷；Execution QA与Result QC独立；必需QC失败不能绕过；失败/未运行任务只能作为草稿；6个已退休顶层字段不得借未知字段兼容机制复活。

## 其他回归

- pip check：PASS，退出码0。
- python -S -m examples.phase2_roundtrip：PASS；未加载第三方检测栈。
- 保护SHA256：1298文件全部相同；保护清单与范围见修订报告。
- 原生产算法未执行，Phase 3未开始。

## 语义与限制

测试验证的是领域协议的一致性，不是生产检测性能或真实mask资源完整性。validate_final不执行资源IO，示例QC声明纯数据自洽。正式资源存在性与哈希将由后续Application/Infrastructure填入Result QC。

复现（新工程根目录）：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.main --smoke-test
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -S -m examples.phase2_roundtrip output/my_new_revision_examples
```

示例输出目录须使用新名称，保留现有草稿与本次冻结示例。schema仍为1.0，本次为冻结前修订。
