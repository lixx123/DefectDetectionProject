# Phase 8 只读检测过程与候选审计

基线：167979f0f867f4de22d040116991fa4a9dee80bd。检查点：phase8-checkpoint-20261021。
第四页“检测过程 / 审计”保持前三页功能，增加候选表/详情、全量去向统计、运行 Attempts/QA、既有事件四个子页。
页面只读，无确认、驳回、等级修改、删除或写回；不进入 Phase 9。

运行头部直接投影 requested_mode、按 attempts 原顺序的 mode/status/QA/reason、final_mode、fallback、状态和QA。完整 ExecutionInfo JSON保留计划、几何状态、checks、消息和sentinel证据。无尝试时明确为空，不根据requested推断实际执行。
候选表占据主体；固定数量详情控件与局部图置于右侧。FILTERED原因、MERGED目标、原始extensions可见；长字段可滚动/查看完整值。两张原生Qt统计图位于“全量去向统计”，不是阶段流水瀑布。

原RAW缺失不影响候选/统计/跳转/事件。只为当前选中候选且审计页活动时加载局部资源，复用InspectionController worker；epoch/query revision/image key拒绝旧返回。所有索引与查询在worker执行，无每条候选Widget或批量图像/mask解码。

本目录设计和截图为提交前证据。依据任务书第88节，最终提交后重新运行全部门禁，最终回执仅写 output/phase8_final/ 和 Codex outputs/Phase8/，不回写已提交文档。后者交付目录包含 docs/phase_8/ 镜像、final_commit.txt、最终verification、十张截图、日志与归档。
工程QA不等同人工验收；完成后等待人工审核。
