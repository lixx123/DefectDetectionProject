# 任务书77节逐项覆盖

测试文件：tests/test_phase8_audit.py。最终门禁证据位于output/phase8_final。

1. 第4个 Tab 存在 → test_fourth_tab_and_empty
2. Audit 页面空状态 → test_fourth_tab_and_empty
3. execution requested/final mode → test_execution_and_fallback
4. fallback used → test_execution_and_fallback
5. fallback reason → test_execution_and_fallback
6. attempts 顺序 → test_execution_and_fallback
7. QA状态 → test_execution_and_fallback
8. source_candidate_count → test_counts_and_dynamic_groups
9. lineage_complete → test_counts_and_dynamic_groups
10. disposition计数和 → test_counts_and_dynamic_groups
11. FilterReason计数 → test_counts_and_dynamic_groups
12. source动态统计 → test_counts_and_dynamic_groups
13. stage动态统计 → test_counts_and_dynamic_groups
14. CandidateKey=(source,id) → test_tuple_identity_and_ambiguous_reverse
15. 同ID不同source可同时存在 → test_tuple_identity_and_ambiguous_reverse
16. candidate table字段 → test_select_details_and_missing_geometry / test_global_sort_and_key / test_counts_and_dynamic_groups
17. initial geometry字段 → test_select_details_and_missing_geometry / test_global_sort_and_key / test_counts_and_dynamic_groups
18. initial_geometry=None → test_select_details_and_missing_geometry / test_global_sort_and_key / test_counts_and_dynamic_groups
19. FILTERED reason展示 → test_select_details_and_missing_geometry / test_global_sort_and_key / test_counts_and_dynamic_groups
20. MERGED merged_into展示 → test_select_details_and_missing_geometry / test_global_sort_and_key / test_counts_and_dynamic_groups
21. REVIEW展示 → test_select_details_and_missing_geometry / test_global_sort_and_key / test_counts_and_dynamic_groups
22. PENDING展示 → test_select_details_and_missing_geometry / test_global_sort_and_key / test_counts_and_dynamic_groups
23. final_defect_id展示 → test_select_details_and_missing_geometry / test_global_sort_and_key / test_counts_and_dynamic_groups
24. invalid final_defect_id安全 → test_invalid_draft_warnings
25. candidate→final defect跳转 → test_bidirectional_jump_clears_hidden_final_filter
26. final defect→candidate反查 → test_bidirectional_jump_clears_hidden_final_filter
27. merged target唯一跳转 → test_merged_ambiguity_and_unique_jump
28. merged target歧义禁止猜测 → test_merged_ambiguity_and_unique_jump
29. disposition筛选 → test_query_filters / test_debounce_clear_size_and_preserved_selection
30. FilterReason筛选 → test_query_filters / test_debounce_clear_size_and_preserved_selection
31. source筛选 → test_query_filters / test_debounce_clear_size_and_preserved_selection
32. stage筛选 → test_query_filters / test_debounce_clear_size_and_preserved_selection
33. linked/unlinked筛选 → test_query_filters / test_debounce_clear_size_and_preserved_selection
34. Candidate ID搜索 → test_query_filters / test_debounce_clear_size_and_preserved_selection
35. 清除筛选 → test_query_filters / test_debounce_clear_size_and_preserved_selection
36. 组合AND筛选 → test_query_filters / test_debounce_clear_size_and_preserved_selection
37. 搜索debounce → test_debounce_clear_size_and_preserved_selection
38. 500分页 → test_debounce_clear_size_and_preserved_selection
39. 页大小切换 → test_debounce_clear_size_and_preserved_selection
40. 分页边界0 → test_page_boundaries / test_large_ui_background_heartbeat_and_no_images
41. 分页边界1 → test_page_boundaries / test_large_ui_background_heartbeat_and_no_images
42. 分页边界499 → test_page_boundaries / test_large_ui_background_heartbeat_and_no_images
43. 分页边界500 → test_page_boundaries / test_large_ui_background_heartbeat_and_no_images
44. 分页边界501 → test_page_boundaries / test_large_ui_background_heartbeat_and_no_images
45. 50,000候选 → test_page_boundaries / test_large_ui_background_heartbeat_and_no_images
46. 全局排序后分页 → test_global_sort_and_key / test_large_global_filter_sort_pagination / test_selected_candidate_key_survives_sort_and_page
47. 筛选后分页 → test_global_sort_and_key / test_large_global_filter_sort_pagination / test_selected_candidate_key_survives_sort_and_page
48. CandidateKey排序后稳定 → test_global_sort_and_key / test_large_global_filter_sort_pagination / test_selected_candidate_key_survives_sort_and_page
49. 选择Candidate详情同步 → test_global_sort_and_key / test_large_global_filter_sort_pagination / test_selected_candidate_key_survives_sort_and_page
50. 快速切换旧图像请求丢弃 → test_stale_image_and_query_requests / test_fast_switch_real_worker_latest_wins
51. synthetic RAW局部 → test_candidate_crop_synthetic_raw / test_candidate_preview_priority / test_no_candidate_geometry_never_uses_final_bbox
52. 无RAW preview → test_candidate_crop_synthetic_raw / test_candidate_preview_priority / test_no_candidate_geometry_never_uses_final_bbox
53. 无任何局部资源 → test_candidate_crop_synthetic_raw / test_candidate_preview_priority / test_no_candidate_geometry_never_uses_final_bbox
54. candidate bbox不使用final bbox伪造 → test_candidate_crop_synthetic_raw / test_candidate_preview_priority / test_no_candidate_geometry_never_uses_final_bbox
55. final bbox叠加语义分离 → test_candidate_crop_synthetic_raw / test_candidate_preview_priority / test_no_candidate_geometry_never_uses_final_bbox
56. audit events空 → test_events_generic_and_empty
57. audit events非固定dict安全 → test_events_generic_and_empty
58. lineage incomplete警告 → test_invalid_draft_warnings
59. Candidate审计操作结果零写回 → test_result_zero_writeback_and_full_stats
60. 26_1正式结果审计 → test_formal_audit_readonly_bidirectional (26_1 / 26_2)
61. 26_2正式结果审计 → test_formal_audit_readonly_bidirectional (26_1 / 26_2)
62. 26_1 disposition总和正确 → test_formal_audit_readonly_bidirectional (26_1 / 26_2)
63. 26_2 disposition总和正确 → test_formal_audit_readonly_bidirectional (26_1 / 26_2)
64. 26_1 Filtered均有原因 → test_formal_audit_readonly_bidirectional (26_1 / 26_2)
65. 26_2 Filtered均有原因 → test_formal_audit_readonly_bidirectional (26_1 / 26_2)
66. 26_1 Merged均有target → test_formal_audit_readonly_bidirectional (26_1 / 26_2)
67. 26_2 Merged均有target → test_formal_audit_readonly_bidirectional (26_1 / 26_2)
68. 26_1 final_defect links有效 → test_formal_audit_readonly_bidirectional (26_1 / 26_2)
69. 26_2 final_defect links有效 → test_formal_audit_readonly_bidirectional (26_1 / 26_2)
70. 26_1反向lineage查询 → test_formal_audit_readonly_bidirectional (26_1 / 26_2)
71. 26_2反向lineage查询 → test_formal_audit_readonly_bidirectional (26_1 / 26_2)
72. Phase7全部测试保持 → 最终全量pytest，原428项保留
73. FAST PASS → 最终FAST / GOLDEN / RELEASE / smoke / pip check
74. GOLDEN PASS → 最终FAST / GOLDEN / RELEASE / smoke / pip check
75. RELEASE PASS → 最终FAST / GOLDEN / RELEASE / smoke / pip check
76. smoke PASS → 最终FAST / GOLDEN / RELEASE / smoke / pip check
77. pip check PASS → 最终FAST / GOLDEN / RELEASE / smoke / pip check
78. machine path scan PASS → 最终machine_paths + 外部RAW拒绝守卫及全部profile
79. external RAW independence PASS → 最终machine_paths + 外部RAW拒绝守卫及全部profile
80. schema1.0不变 → 最终RELEASE schema/AUTO/Repository/Golden/765文件保护与frozen hash manifest
81. AUTO不变 → 最终RELEASE schema/AUTO/Repository/Golden/765文件保护与frozen hash manifest
82. Repository不变 → 最终RELEASE schema/AUTO/Repository/Golden/765文件保护与frozen hash manifest
83. Golden不变 → 最终RELEASE schema/AUTO/Repository/Golden/765文件保护与frozen hash manifest
84. 原算法零变化 → 最终RELEASE schema/AUTO/Repository/Golden/765文件保护与frozen hash manifest
85. algorithm_executions=0 → no_engine_execution观察与Golden门禁；零实算、无Phase9写回
86. Phase9未开始 → no_engine_execution观察与Golden门禁；零实算、无Phase9写回
