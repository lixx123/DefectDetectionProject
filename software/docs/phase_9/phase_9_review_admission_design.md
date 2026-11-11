# Phase 9 人工复核准入与候选分层 V1

基线18b311bd7408474fb38b282d35d8c3084b73c76a；检查点phase9-checkpoint-20261022。用户已授权本阶段，并在实施中选择异常链接方案1。

Audit REVIEW与Manual Review Queue完全独立。对每个最终Defect和每条Candidate生成运行时Decision；四类AUTO_ACCEPT/AUTO_REJECT/MANUAL_REVIEW/AUDIT_ONLY分别计数Defect和Candidate，不能将历史REVIEW直接交给人工。AUTO_ACCEPT仅表示算法最终接受，不是人工确认。
所有最终Defect只允许AUTO_ACCEPT或MANUAL_REVIEW；Candidate不AUTO_ACCEPT。准入不改变domain、ReviewInfo、disposition、检测统计、ROI/Band、mask、Golden或Repository。

## 架构选择

纯Python派生逻辑放ui/models/review_admission/（model.py、policy.py、rules.py、engine.py），没有Qt、Repository或图像I/O依赖。UI投影在review_queue_view_model.py，展示在review_admission_page.py。
策略YAML放同目录review_admission_v1.yaml，相对模块定位，不放configs/production_v1.yaml。任务书允许只读derived logic置于UI；本安排既区分了准入策略与检测生产配置，也保持现有Release Gate对application/configs冻结层的保守判断。没有更改gate白名单或REAL要求判定。
ReviewAdmissionResult仅运行时派生。QA输出JSON不写入正式结果包。policy_id/version/hash随输出和UI可查，普通操作员无参数编辑器。

## 验收与边界

78项新测试，原479项保留；唯一旧期望变更是第四Tab测试的页签总数4→5，仍验证原第四页和全部原功能。新增跨页公开focus_candidate接口只用于将准入对象定位到既有审计表。
本目录为提交前设计和证据。最终提交后串行运行pytest、FAST、GOLDEN、RELEASE、smoke、pip check，权威回执仅写ignored output/phase9_final和Codex outputs/Phase9。交付镜像docs/phase_9包含final_commit.txt及最终verification，不反向修改已提交文档。
完成后等待人工审核；人工确认/误报/驳回/意见/审核人时间写回未开始。工程QA与用户人工验收分开记录。

