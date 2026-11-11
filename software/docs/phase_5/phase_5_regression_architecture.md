# Phase 5 分层回归架构

基线 c90b899b1559d8fcc4460499e4ec1c3474646840，checkpoint phase5-checkpoint-20261021。新增独立 regression/，不修改 core、domain、configs、Repository、GUI 或已有 255 项测试逻辑。旧测试通过 tests/conftest.py 仅添加 marker。

|层|入口|依赖|实际行为|
|---|---|---|---|
|FAST|--profile fast|Git 内代码、小 fixture 和小型黄金元数据|unit/interface/schema/config/AUTO/mapper/QA/Repository/security/application service；不读大 RAW，不启动原工程进程|
|GOLDEN|--profile golden|本地冻结六组结果、engine CSV 证据、Phase 4 两包与 Git 内黄金元数据|当前解码器/门禁/审计 mapper、对象/mask/ROI/audit/Repository/index/export 校验；不运行算法|
|REAL_ENGINE|--profile real --raw-root ...|显式提供 SHA 匹配 RAW 和原算法环境|两张 × FULL/ROI_BH/AUTO，新任务目录，比较冻结结果；本轮未执行真实算法|
|RELEASE_GATE|--profile release|FAST + GOLDEN + 协议 + AUTO + 保护清单|按影响判定 REAL 是否必需，输出明确发布状态|

注册 marker：unit、integration、golden、real_engine、repository、security、slow、release_gate，另有 reference_probe。FAST 的选择式为 `not golden and not real_engine and not reference_probe`；GOLDEN 为 `golden and not real_engine and not reference_probe`。原有两个 tiny sentinel/短 RAW 导入探针不进入 FAST 或 GOLDEN，仍在完整旧测试中执行；探针不计算 Black-Hat/J4/J5。

统一入口 `python -m scripts.run_regression_suite --profile fast|golden|real|release`，默认每次生成独立 output/regression/<timestamp_profile_uuid>。--output-dir 必须为新目录，拒绝覆盖既有报告。pytest 基础临时目录使用短名称避免 Windows MAX_PATH。输出 JUnit 和日志，选中测试出现任何 skip 或零测试即 profile FAIL。

GOLDEN fixture 在运行期间禁止 subprocess.Popen；只有读取现有输出与小型审计重映射。两个正式包先完整校验，再复制到临时库做索引重建/query/export，原 Golden result、mask、manifest 和 index 都不写。前后核对证据 SHA256。

REAL 使用 manifest 内经原 config_hash 验证的冻结模式配置，不以当前 YAML 冒充历史运行配置。RAW 路径仅由 --raw-root 提供，manifest 只包含文件名/hash。缺 RAW 或 SHA 不符为 NOT_RUN，命令返回非零；fake 演练标注 simulation=true、real_engine_executed=false、algorithm_executions=0。本轮只做 fake 六模式流程和缺 RAW 负向检查。

schema contract 是正式字段名、类型、required/nullable 及全部 Enum wire values 的小型快照，不把 Python 源码 hash 当作协议。原算法保护仍使用既有 SHA manifest；发布门禁仅选取原 DefectDetectionProject 范围，避免将未来允许修改的 GUI 源码误认作原算法。当前阶段另核对既有完整 1317 项保护清单。

Golden Regression Set 含历史审批与归档，不能证明新 RAW 的冷启动泛化。tests/validation/blind_manifest.json 明确 NOT_AVAILABLE，无虚构盲测样本。本轮不进入 Phase 6。
