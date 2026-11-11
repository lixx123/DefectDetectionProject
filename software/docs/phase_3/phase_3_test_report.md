# Phase 3 测试报告

2026-10-20：全部新软件 **145 passed**，包含冻结Phase 2全部99项；新增46项（Adapter 36、真实输出/原guard/命名空间8、差异比较2）。完整命令与退出码见software_guard_verification.json，日志见all_software_tests.log。

## 分层验证

- Level 1：小型fixture测试CSV→Defect、ROI/Band、审计、统计、QC和反向来源；AUTO的10种原因均直接FULL、不经过ROI_J4；FULL失败只能成为草稿；取消传播不触发FULL；使用自定义尺度5证明没有在适配器重新硬编码空间比例。
- Level 2：真实冻结26两帧解析，36/35、20356/17709、297/398/348/370验证，完整32370/8332源，实际RAW recovery与成员关联通过。
- Level 3：26两帧各FULL、ROI_BH、AUTO，共六次真实从RAW运行，全部正式门禁与JSON往返PASS；AUTO只运行ROI_BH。
- 原函数sentinel探针：65535真实触发require_computed_response异常并归类SENTINEL_CONSUMED；正常真实运行中每个实际J4消费窗口与K8B WORK区域均调用原guard。
- 原工程独立ROI/FULL QA：两帧各765图块的BH/J4源像素、成员、种子、最终mask及四处人工批准精确保留，差异0。

## 任务书34项覆盖

| 要求 | 证据 |
| --- | --- |
| 1/2 Detector与内存InspectionResult | test_detector_returns_real_model_and_maps_measurements及六次真实inspect |
| 3/4 FULL与ROI真实运行 | final_acceptance_runs.json四次显式运行 |
| 5/6/7 AUTO优先ROI、失败直FULL、无ROI_J4 | 两次真实AUTO目录+test_auto_rejected_roi_goes_directly_to_full（10原因） |
| 8 sentinel映射 | 原guard真实小探针、worker每窗口检查、失败分类与AUTO测试 |
| 9/10 Band/J4/J5错误分类 | test_failure_classification_uses_stage_evidence |
| 11/12 输入与算法身份 | 全RAW SHA/尺寸/位深及关键源码manifest hash、实际环境 |
| 13/14 ROI与Band真实 | 原geometry JSON、ID/region PNG，原RAW core灰度统计 |
| 15/16/17/18 数量面积Feret等级 | 真baseline解析、NPZ独立复核与逐对象差异 |
| 19 空间尺度 | 默认配置与test_config_scale_is_used_without_modifying_pixel_results |
| 20/21 完整/反向lineage | 联合全源台账、J5/恢复关联及missing-source拒绝测试 |
| 22/23 统计汇总与原summary | aggregate(Defect[])及QC summary故障注入 |
| 24/25 Execution QA/Result QC | 真实J4/J5/计划/guard证据与NPZ/整图/资源SHA检查 |
| 26/27 final门禁/JSON | 六份最终统一结果保存加载相等并再次validate_final |
| 28 相对ArtifactReference | 全部最终引用文件存在/哈希验证与统一对象字符串路径检查 |
| 29/30 四处暗斑 | 原独立QA两帧approved_masks全为pixel_exact_single_match |
| 31 既有划痕不丢 | 全部冻结最终mask精确保持；不扩展到未标注真值 |
| 32 原算法保护 | 1317保护文件0变化，domain及旧测试/Phase 1 git diff为空 |
| 33 Phase 1 smoke | phase1_smoke.log退出0，截图目视正常 |
| 34 Phase 2全部99 | 原测试文件未改且全部仍在145通过中 |

## 过程问题及修复

- 新软件regular scripts包遮蔽原namespace scripts，真实启动被拒绝为失败草稿。修复仅在子进程显式固定原scripts命名空间，补真实导入测试。
- 初期跨legacy/fresh按顺序ID比较误报5个对象变化；改为精确来源集合/真实mask匹配，并保留5处编号映射。没有把物理变化隐藏成编号变化，所有mask/来源都独立验证。

真实六次数据没有触发安全FULL回退；回退链通过fixture及真实sentinel函数探针验证，不能表述为两帧出现了自然sentinel故障。Full failure/cancel均为测试注入场景，有清晰标识。

Phase 1 smoke、pip check、验收CLI help均退出0。未修改原算法或冻结领域协议，未进入Phase 4。最终提交见final_commit.txt。
