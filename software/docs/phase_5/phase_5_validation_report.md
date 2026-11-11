# Phase 5 系统回归与黄金样本验收

日期：2026-10-21。审核基线/测试 HEAD：c90b899b1559d8fcc4460499e4ec1c3474646840；checkpoint phase5-checkpoint-20261021。

结论：Phase 5 实施完成，FAST / GOLDEN / RELEASE PASS。golden_set_version=1.0，schema_version=1.0，package_format_version=1.0。最终提交后停止等待人工审核，未进入 Phase 6。

## 分层结果

|检查|结果|证据|
|---|---|---|
|独立 FAST|PASS，295 项，0 skip|fast_profile_report.json|
|独立 GOLDEN|PASS，23 项，0 skip|golden_profile_report.json|
|RELEASE|PASS；FAST + GOLDEN + Repository + schema + AUTO + 原算法保护|release_gate_report.json/md|
|全部 software tests|320 passed in 248.47s (0:04:08)，0 skip|all_software_tests.log / all_tests.xml|
|原测试保留|255 项，8 个原测试文件逻辑未修改|phase_5_software_checks.json|
|Phase 1 smoke / pip check|PASS|对应日志和截图|

65 项新增测试由 57 项小型/负向 fixture 与 8 项 Golden assertions 组成。FAST 排除大型证据与原工程进程；GOLDEN 只读已冻结证据，不启动参考引擎。完整测试另保留两个原工程微型 guard/导入探针，它们不运行生产检测。

## 六组 Golden

|样本|模式|对象数|总面积 px²|对象/source/Feret/grade|mask hash|ROI/Band|audit|
|---|---|---:|---:|---|---|---|---|
|26_1|full|36|20356|PASS|PASS|PASS|PASS|
|26_1|roi-bh|36|20356|PASS|PASS|PASS|PASS|
|26_1|auto|36|20356|PASS|PASS|PASS|PASS|
|26_2|full|35|17709|PASS|PASS|PASS|PASS|
|26_2|roi-bh|35|17709|PASS|PASS|PASS|PASS|
|26_2|auto|35|17709|PASS|PASS|PASS|PASS|

所有最终对象按唯一 EXACT_SOURCE_SET，其次 EXACT_GLOBAL_MASK 匹配，不以顺序 ID 为唯一依据。最终 mask、对象 NPZ、WORK/NONWORK/REVIEW、Band、几何 bbox/valid/mean/min/max DN、Statistics、Execution、QC、Calibration 与 None 语义保持一致。当前 audit mapper 从既有真实 CSV 重映射同样 PASS。

- 26_1 AUTO 最终整图 mask SHA256：`ec7e373469a4d22e3b1e372f1506aef320cc7c547ea99bbf539ddd74b0209672`。
- 26_2 AUTO 最终整图 mask SHA256：`ccfdb22000a1e509746daf9e4ddf80d981508f0cdbe7dd2c1e1b0ef906029499`。

暗斑 26_1 的 297/398 px²、26_2 的 348/370 px² 均保留；各 4 Band，AUTO 仍 roi-bh 无 fallback。原配置 hash 和尺度 3.2 μm/px 保留，线性/平方尺度关系通过。

候选按 UID 排序的完整语义 digest 冻结，另外冻结 fresh/historical/union 数量、disposition/reason 分布、反向追溯与重点 UID。J5:F1:DEFECT_00001 FULL 保持 FILTERED / OUTSIDE_WORK_REGION / 原消息；ROI/AUTO 历史未重算记录保持 REVIEW。NO_DELETE / NOT_PROVEN_NOISE 记录未被伪装成噪声或尺寸过滤。

## Repository 与证据保护

两个 Phase 4 正式包完整 verify/load 后与 AUTO Golden 一致；在独立临时副本库完成 rebuild_index、query 和 export，ZIP CRC/SHA256 PASS。repository_status=PASS，索引 2 项，查询 2 项。没有改写原结果/manifest/index。

Golden 验证前后核对 470 个源证据文件，变更列表为空。既有完整保护 manifest 1317 项 SHA256 一致；发布门禁单独核对原算法范围 765 项，变更列表为空。core/domain/configs/Repository/application/GUI 与原测试逻辑 Git diff 为空，仅新增分层 marker hook。

Git 内保存约 1.5 MB Golden metadata、schema contract、初始化 change audit 和 blind 占位；完整 result、mask、正式 ZIP、RAW 仍位于本地受保护目录，不重复进入 Git。Frozen JSON 文件自身 SHA 用于只读基线完整性；候选顺序、ID、时间等新运行的语义比较另行规范化，不靠整个 JSON 字节判断退化。

## 安全门与发布状态

- AUTO_policy_status=PASS，roi_j4_in_auto=false；实际 scheduler 与两个 consumed-window sentinel guard 的 AST 检查通过。
- fallback_fixture_count=10，pass_count=10；覆盖全部十类原因，均 ROI_BH 拒绝后直接 FULL。
- sentinel_gate_status=PASS；bridge QA 拒绝、真实原 guard 对 65535 的微型探针，以及移除 guard 的负向门禁均通过。
- FULL 也失败则 FAILED/final_mode=None，正式 Repository 拒绝保存。
- 负向比较证明面积、Feret、grade、ROI、audit、config/算法环境、None→0、对象消失及 mask 篡改都会 FAIL；仅顺序 ID/运行时间元数据变化不误判，时间超过 2 倍只 WARNING。
- real_engine_required=false，real_engine_executed=false，algorithm_executions=0。CLI 缺少 RAW 明确 NOT_RUN、非零退出；六模式 fake 演练标记 simulation，未冒充真实执行。
- 需要 REAL 却未运行时 NOT_COMPLETE，真实执行失败或其他门禁失败为 FAIL，均有负向测试。
- 更新工具默认拒绝，--approve 也不能无 --allow-update 覆盖既有元数据；实际 CLI 负向检查确认 Golden 未变。当前只有初次建立元数据，没有更新黄金检测结果。

## 范围与审核边界

Blind Validation NOT_AVAILABLE；这两张含历史审批/归档，只构成 Golden Regression Set，不能证明新 RAW 冷启动泛化。本轮未调阈值、未重跑 Black-Hat/J4/J5/K8/RAW recovery，未进入 GUI、报告、数据库、EXE 或 Phase 6。

发布测试在提交前的工作树执行，release report 记录 tested HEAD、dirty 状态与源码指纹。完整测试确认最终运行代码指纹与 release 一致；final_commit.txt 在提交后提供最终 commit，避免伪造自引用 hash。需要人工审核后再进入下一阶段。
