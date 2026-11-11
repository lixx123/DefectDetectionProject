# Golden Set 1.0

独立版本：golden_set_version=1.0；InspectionResult schema_version=1.0；package_format_version=1.0，三者不混用。

tests/golden/golden_manifest.json 保存 GOLDEN_26_1/GOLDEN_26_2，各有 expected_full/expected_roi_bh/expected_auto。来源是人工审核通过的 Phase 3 revision 六组结果（1aa643d...）与 Phase 4 正式包（c90b899...），不是本轮新计算结果。

每例记录 RAW 文件名/hash、schema、baseline source/commit、algorithm source hash、config hash 和经原 hash 验证的冻结配置。对象冻结 source membership、bbox、area、Feret、grade、band/ROI、NPZ SHA 和精确全局像素签名，以及全部其他既有缺陷字段（包括 None）。最终整图 mask、WORK/NONWORK/REVIEW、Band mask/geometry/DN 和全部正式资源 SHA 均检查。

26_1：36 对象，20356 px²，4 Band，AUTO roi-bh、无 fallback；暗斑 297/398 px²。26_2：35 对象，17709 px²，4 Band，AUTO roi-bh、无 fallback；暗斑 348/370 px²。

Audit 不冻结候选 JSON 顺序，按 (source,candidate_id) 排序后计算完整语义 digest；同时保留 fresh/historical/union 数量、disposition/reason 分布、lineage_complete、RAW recovery 事件、重点 UID 和微小待审分布。FULL 的 J5:F1:DEFECT_00001 必须 FILTERED / OUTSIDE_WORK_REGION，原 message J5_J5_OUTSIDE_WORK；ROI/AUTO 若为历史未重算则保持 REVIEW / None。NO_DELETE/NOT_PROVEN_NOISE 候选不自动筛掉。当前 mapper 用真实 CSV 重新生成 Audit，与冻结语义对比，不重算检测。

Golden 元数据、schema contract、blind 占位与初始化审计在 Git；约 1.5 MB 的 metadata 不含完整大 JSON、mask、ZIP 或 RAW。实际 evidence 在本地 output/phase3_revision/remapped_results、既有 engine 输出、output/phase4_validation/repository。所有引用相对工程根目录；manifest 无机器绝对 RAW 路径。缺少本地证据时 GOLDEN 明确 FAIL，不用 skip 伪装 PASS。

普通测试/runner 无写 golden 的功能。scripts/update_golden_baseline 默认拒绝；初始化要求 --approve --reason，覆盖既有元数据还要求 --allow-update，未来可提供 --candidate-manifest。生成带旧/新 commit、算法 hash、对象/mask/Feret/ROI/audit 比较与批准原因的 golden_change_report.md/json；不改物理 evidence。Schema 不匹配先停止，不通过 Golden 更新偷偷变更 wire。当前仅按用户授权建立初始元数据，没有改变任何黄金检测结果。

历史配置快照保留原 MODEL_ONLY_NOT_CONNECTED_TO_ENGINE 标签对应的 canonical hash；它是当时配置历史，不代表当前适配器未连接。当前生产 YAML 仍 REFERENCE_ENGINE_CONNECTED，Golden/REAL replay 为可比性使用冻结配置；不读取当前 YAML 覆盖历史尺度。

只读基线文件本身另用 SHA 防止被覆盖；新结果比较按 UID 排序、数值规范化后比较语义，不将候选 JSON 顺序或相同数值的 int/float 表达误判为检测差异。
