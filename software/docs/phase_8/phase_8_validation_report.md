# 提交前数据与视觉复核

26_1：32,370候选，RETAINED33/FILTERED4/MERGED9/REVIEW32324/PENDING0；来源J5 15604/K8B16766；最终36、关联42、未关联32328。
26_2：8,332候选，RETAINED33/FILTERED0/MERGED5/REVIEW8294/PENDING0；来源J5 4440/K8B3892；最终35、关联38、未关联8294。
两包source_candidate_count等于实际数，lineage_complete=true；无重复完整Key、无无效最终链接、FILTERED均有reason、MERGED均有原始目标。71个最终对象反向关联均检查，无反向矛盾。14条merged_into保存finalID的限制已如实记录，不改包、不猜候选。
26_1 FILTERED的4条均OUTSIDE_WORK_REGION；26_2无FILTERED，图表按空态显示。
十张截图为真实无RAW历史与明确标注的合成fixtures；视觉检查原因、目标、候选/最终区分、分页、链不完整警告与attempt可读。工程截图QA不代替用户人工审核。

本文件是提交前报告。最终tested_head、final_commit、clean状态与全套门禁请以output/phase8_final/phase_8_verification.json或Codex outputs/Phase8中的最终回执为准；按任务书第88节提交后不修改此目录。

