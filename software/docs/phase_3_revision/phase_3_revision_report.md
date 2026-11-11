# Phase 3 审计修订与正式冻结报告

日期：2026-10-21。实施基线：bc40fc81f17153592f46756ab4514522a3a08a75；真实检测计算基线：6a2f2219e9555d2eef1ba630b5031ca21311a988。

用户确认方案 2 后完成本轮：schema_version 保持 1.0，不新增 FilterReason 枚举，不进入 Phase 4。集中原因/状态映射、配置状态、README 和只读 remap 工具已修订。

## 六组已有真实输出回归

|样本|模式|对象数|总面积 px²|最终 mask 差异像素|validate_final|
|---|---|---:|---:|---:|---|
|26_1|full|36|20356|0|PASS|
|26_2|full|35|17709|0|PASS|
|26_1|roi-bh|36|20356|0|PASS|
|26_2|roi-bh|35|17709|0|PASS|
|26_1|auto|36|20356|0|PASS|
|26_2|auto|35|17709|0|PASS|

六组逐对象 ID、bbox、面积、Feret（零容差）、size_grade、精确 NPZ mask、source membership 均零变化。Defect[]、ROI/Band、Statistics、Execution QA、Result QC、输入、标定、原计算版本/config_hash 及资源引用均做了模型字段完全相等断言。全图 mask 逐像素比较差异均为 0；所有资源 SHA256 和 JSON roundtrip 通过。

候选身份、source、initial_geometry、current_stage、final_defect_id、RAW recovery 事件、fresh/historical/union 数量及历史未重算标志保持不变；允许的变化只在审计解释层。新快照的新 result_id 和 remap provenance 用于区分修订，原有结果文件没有覆盖。

## 审计变化

|样本/模式|FILTERED|REVIEW|RETAINED|MERGED|LOW_EVIDENCE|
|---|---:|---:|---:|---:|---:|
|26_1 full|14921|17407|33|9|0|
|26_2 full|4042|4252|33|5|0|
|26_1 roi-bh|4|32324|33|9|0|
|26_2 roi-bh|0|8294|33|5|0|
|26_1 auto|4|32324|33|9|0|
|26_2 auto|0|8294|33|5|0|

J5:F1:DEFECT_00001 在 FULL 的原始 decision_reason 为 J5_J5_OUTSIDE_WORK；修订后 FILTERED / OUTSIDE_WORK_REGION，filter_message 原值不变。在 ROI/AUTO 中若该 UID 为历史未重算记录，则继续 REVIEW / None，不能冒充本次 fresh 筛除。所有分布及按 stage 的原因分布见 phase_3_revision_comparison.json。

MICRO_HIDE_SUGGESTION...NO_DELETE、MICRO_REVIEW...NOT_PROVEN_NOISE 不因面积小而转为背景噪声或尺寸过滤；实际最终 membership 优先，无明确拒绝时 REVIEW。实际多来源成员使用 MERGED 并指向已有最终对象；合并不会改变成员关系。没有证据的人工结论不生成 USER_REJECTED。

六组未证实硬尺寸/几何筛除实例。未来明确实例使用 OTHER，加 extensions.reference_reason_category = SIZE_OR_GEOMETRY_FILTER；原始 decision_reason 及相关字段无损保留。集中规则见 phase_3_audit_reason_mapping.md。

## 保护与实施边界

没有重跑 Black-Hat、J4、J5、K8 或 RAW recovery；重映射期间直接禁止 subprocess。保护清单 1317 项 SHA256 前后一致，另对六组既有 engine 的 15154 个文件（1475961398 字节）逐一核对前后 SHA256 一致。没有修改参考工程、阈值、domain 或冻结测试。

生产 AUTO 保持 ROI_BH → Execution QA → 失败时 FULL；roi-j4 未进入回退链。production_v1.yaml 只更新 status 为 REFERENCE_ENGINE_CONNECTED，README 明确仍依赖参考工程及其虚拟环境，尚未独立打包。原算法配置 hash 仍描述原真实运行，不伪装成本轮重新计算。

全部 software tests、Phase 1 smoke、pip check 及 remap CLI 检查通过，见本目录测试报告和日志。正式提交 hash 写入 final_commit.txt；这是本轮 Phase 3 修订冻结，完成后停止等待人工审核。

## 结果位置

六组新快照位于 output/phase3_revision/remapped_results/，每个目录的 result.json 配套相对路径 artifacts。交付 zip 将完整保存各结果目录；不包含 RAW 或昂贵中间数组。软件运行仍依赖原参考工程，本次交付不是独立 EXE。
