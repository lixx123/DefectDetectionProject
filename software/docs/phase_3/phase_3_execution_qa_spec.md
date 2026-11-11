# Phase 3 Execution QA

Execution QA判断某次attempt是否可以被采用，不替代最终结果QC。

| 检查 | 真实依据 |
| --- | --- |
| RAW_dimensions | 原配置宽高×2与文件字节数 |
| RAW_effective_bit_depth | 全文件分块DN最大值在有效位深范围内 |
| RAW_SHA256/RAW_unchanged | 运行前后完整文件SHA256及原引擎记录 |
| Band_locator/geometry | 原locator及build_plan，fallback_reasons必须为空才采用ROI |
| ROI_plan | 实际计划图块+跳过图块=full_tiles |
| ROI_context | 原J4每个实际work窗口被逐一检查；数量等于计划 |
| sentinel | 运行中原函数require_computed_response保留；运行后再次对每个J4消费窗口和全部K8B WORK响应执行原guard |
| J4_completed | 原run_status.J4_COMPLETE，completed=planned=acceptance实际数 |
| J5_completed | J5_COMPLETE、source_J4_tiles吻合、源面积守恒、计划区域完成 |
| source_lineage/final_selection | 实际台账、成员与最终NPZ源集合双向关联及输出验证 |

65535只允许留在未计算区域，不能在实际消费窗口或K8B工作区出现。原guard发现sentinel会抛异常，被归类SENTINEL_CONSUMED；AUTO直接FULL，不能输出ROI正式结果。

Wrapper预检不安全ROI时保留原失败几何/计划并退出，不让原脚本的内部全图退化被当作ROI成功。FULL若仍只有手动几何复核输出、J4/J5不完整或结果安全门禁未过，也不批准正式结果。

失败按真实异常/阶段/错误证据映射BAND_LOCATOR_FAILED、BAND_GEOMETRY_INVALID、ROI_PLAN_FAILED、ROI_CONTEXT_INCOMPLETE、SENTINEL_CONSUMED、J4_EXECUTION_FAILED、J5_EXECUTION_FAILED、SOURCE_LINEAGE_INVALID、QA_FAILED、UNKNOWN_EXCEPTION。详细异常保留独立日志；领域message不嵌入机器路径。

输入错误抛InputValidationError；取消抛InspectionCancelled并保留cancelled.json，不触发FULL。超时杀死当次子进程并记录失败；FULL也失败则返回FAILED草稿，final_mode=None。算法/解析/QC异常不静默忽略。

生产AUTO的尝试序列只有[ROI_BH]或[ROI_BH,FULL]。验收脚本显式FULL+ROI_BH对照属于独立运行，不改变生产策略。旧冻结回放的QA明确标LEGACY_REPLAY，只验证历史资料，不声明新鲜J4/J5/sentinel计算。
