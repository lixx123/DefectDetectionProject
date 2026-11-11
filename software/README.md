# 滤光片疵病检测软件

当前完成 Phase 0/1 骨架、Phase 2 schema 1.0、Phase 3 真实算法适配与审计冻结，以及 Phase 4 JSON Repository。GUI 仍保持骨架；不含数据库、报告或 EXE 打包。

## 统一真实检测接口

在本工程独立虚拟环境中：

```python
from core.detector import Detector
from configs.loader import load_config

config = load_config("configs/production_v1.yaml")
detector = Detector()
result = detector.inspect(raw_path, config)
result.validate_final()
# 显式 codec 保存是运行记录；正式历史使用下方 Repository。
result.save_json(detector.last_run_dir / "result.json")
```

生产AUTO只运行roi-bh，QA拒绝才直接full；roi-j4不进入回退链。每次检测生成独立output/runtime任务目录和日志，返回内存InspectionResult。FULL仍失败时返回FAILED草稿，无法通过validate_final；输入错误/取消有明确异常。

算法计算由原工程独立子进程完成；默认依赖同级DefectDetectionProject及其.venv/历史审核资料。可用Detector(reference_root=..., python_executable=..., output_root=...)配置。未重写或修改原算法，尚非脱离参考工程的独立软件包。

尺度从config.calibration读取，默认用户声明3.2μm/px；面积按平方尺度换算，原始px量保留。该声明不等于完成物面计量标定。长度为最大Feret，不能当作划痕中心线；未提供类型/宽度/方向等保留None/UNKNOWN。

## 测试与验收

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.main --smoke-test
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m scripts.run_phase3_validation --input '你的RAW路径' --modes full roi-bh auto
```

最后一条是显式开发验收双跑，不是生产策略。普通生产调用Detector.inspect使用AUTO即可。运行需要真实原格式RAW与参考工程依赖，可能耗时数分钟。

配置的算法参数本阶段保持原引擎值；非空algorithm_parameters覆盖会被拒绝，不擅自引入高灵敏度阈值。production_v1.yaml 的 status 为 REFERENCE_ENGINE_CONNECTED：当前已经通过适配器连接真实 reference engine，仍依赖 DefectDetectionProject 及其虚拟环境，尚未完成独立打包；该状态不表示 GUI、独立 EXE 或生产发布完成。

## 文档

- docs/phase_3/phase_3_adapter_decision.md：开发前方案、全局状态与子进程隔离。
- docs/phase_3/phase_3_algorithm_mapping.md：真实量测、ROI、来源和统计映射。
- docs/phase_3/phase_3_execution_qa_spec.md、phase_3_result_qc_spec.md：两类质量检查。
- docs/phase_3/phase_3_regression_report.md：两帧实际运行与对象/像素差异。
- docs/phase_3/phase_3_test_report.md、phase_3_verification.json：测试和保护证据。
- docs/phase2_revision/：冻结领域协议修订，domain/保持不变。
- baseline/：受保护的Phase 0算法快照与双帧基线。

资源引用相对result.json；原始引擎CSV/日志是审计证据，不作为GUI接口。未知指标不填0，历史归档候选不冒充本次新扫描。

完成Phase 3后停止，等待人工审核，不进入Phase 4或GUI开发。

## Phase 3 审计语义修订

集中映射位于 core/adapters/audit_reason_mapper.py。最终 membership 优先；历史未重算记录继续保留归档语义。NO_DELETE / NOT_PROVEN_NOISE 等待审记录不会仅因面积小被判为噪声或尺寸过滤。原始 decision_reason 及 stage、visibility、classification、execution disposition 保存在审计字段中。

保持 schema_version = "1.0"。明确尺寸/几何筛除使用 FilterReason.OTHER，并在 extensions.reference_reason_category = "SIZE_OR_GEOMETRY_FILTER" 保存细分类；未新增 wire enum。未来 GUI 应读取细分类。没有最终目标不等于明确过滤，无法确认的候选保留 REVIEW；合并必须具有可核实的最终目标。

只读重映射入口：`python -m scripts.remap_phase3_results --help`。它只读取已有输出，不启动检测算法，输出至新建目录，并记录原结果及未重算 provenance。修订验证见 docs/phase_3_revision/。

## Phase 4 正式结果持久化

```python
from pathlib import Path
from infrastructure.repositories import JsonResultRepository
from application.inspection_service import InspectionService

repository = JsonResultRepository(Path("output/results"))
service = InspectionService(detector, repository)
record = service.inspect_and_save(raw_path)  # 默认显式加载 production_v1.yaml
result = repository.load(record.result_id)
integrity = repository.verify(record.result_id)
history = repository.query(sample_id="26", final_mode="roi-bh")
```

也可在 Detector.inspect 后调用 repository.save(result, source_run_dir=detector.last_run_dir)。Detector 只新增本次实际配置快照，不强制保存正式库。Repository 先执行正式门禁，在同卷临时目录归档引用资源、日志和经原 config_hash 验证的配置，完整校验后原子发布；重复 result_id 拒绝覆盖。结果目录不可变，index.jsonl 是可重建缓存。

schema/domain 保持 1.0 冻结，因此 InspectionConfig 类的历史 status 默认值暂保留；生产流程必须 load_config("configs/production_v1.yaml")，或使用默认加载它的 InspectionService。未来 GUI 不应裸用旧默认配置。历史 CalibrationInfo 不因全局尺度修改而变化。

load 默认 full；可显式 verify="light"。verify 返回结构化完整性报告；list_results/query/find_by_source_sha256/rebuild_index 提供历史查询及修复。源日志缺失会显示警告，不伪造；原配置缺失/不匹配则拒绝正式保存。历史资料可由调用者提供经原 hash 验证的恢复快照并记录恢复来源，不能用当前 YAML 替代。

export_package(result_id, zip_path) 产生相对路径正式 ZIP、CRC 校验与 SHA256。导出包解压时应放入以 result_id 命名的新目录，保留完整 artifacts/logs/metadata；本轮不提供 import_package 或 delete，导入明确延期 Phase 4.1。

只读真实验收入口：`python -m scripts.validate_phase4_repository`，只使用已存在的两组 Phase 3 revision AUTO 输出，写入独立 output/phase4_validation/repository。结果完全等价；冻结 codec 的 int→float 数值规范化可能改变 JSON 文本字节，不改变数值、模型或资源。

设计、布局、manifest、完整性、测试与验收报告见 docs/phase_4/。Phase 4 完成后停止等待人工审核，不进入 Phase 5。

## Phase 5 统一回归门禁

```powershell
.\.venv\Scripts\python.exe -m scripts.run_regression_suite --profile fast
.\.venv\Scripts\python.exe -m scripts.run_regression_suite --profile golden
.\.venv\Scripts\python.exe -m scripts.run_regression_suite --profile release
# 仅人工显式触发昂贵实算：
.\.venv\Scripts\python.exe -m scripts.run_regression_suite --profile real --raw-root "你的RAW目录"
```

FAST 不需要生产 RAW/原引擎进程；GOLDEN 读取既有六组冻结证据与两个正式包，需保留本地受保护 output 资料，不启动算法。任何缺失、选中测试 skip 或真实语义差异都会失败。报告写入独立 output/regression/ 目录，--output-dir 可指定新目录。

release 默认不自动运行 REAL，按代码影响给出 required/executed；若需要 REAL 但未执行则 NOT_COMPLETE，不伪称 PASS。手动 --require-real 可强制要求，--execute-real --raw-root 可显式组合真实验收。REAL 的 RAW 缺失或 hash 不符会 NOT_RUN/非零退出。

Golden Set 1.0 和 schema contract 在 tests/golden；大结果、mask、正式 ZIP 和 RAW 不重复进 Git。普通测试无自动更新 baseline；更新工具默认拒绝，要求显式批准、原因和更新审计。Golden 含历史人工审批，Blind Validation 暂 NOT_AVAILABLE，不据此声称新 RAW 冷启动泛化通过。

完整设计、比较白名单、发布策略与验收见 docs/phase_5/。完成后停止等待人工审核，不进入 Phase 6。

## Phase 6 ImageViewer

使用工程 `.venv\Scripts\python.exe -m app.main` 启动；`--smoke-test` 保持支持。
Ctrl+O 打开 RAW，自动检测在后台执行；结果先临时显示，Ctrl+S 才写正式库 `output/results`。
历史按钮加载正式库，双击查看。F 适应窗口，1 原始像素比例，滚轮缩放、拖拽平移。
若原 RAW/preview 不可用，仍可查看最终框、mask、Band、ROI、表格和详情，DN 显示 —。
审核只读，Phase 7 未开始。工程验证和待人工审核项见 `docs/phase_6/`。

## Phase 7 详情与统计

加载结果后可在“检测 / 疵病详情 / 统计分析”三个页签查看。检测页支持尺寸等级、Band、类型筛选与清除；详情上一条/下一条遵守当前可见排序。详情局部图有灰度、框、mask三种模式；无原RAW时仍显示正式包可用mask和全部数值。统计始终为全量最终结果，不受筛选影响。全部只读，未实现审核写回或正式报告导出。

## Phase 8 检测过程与候选审计

第四页“检测过程 / 审计”提供只读运行attempt/QA、全量候选去向统计、虚拟分页表、组合筛选、全局排序、候选初始几何局部图、候选↔最终疵病双向追溯和原始事件JSON。默认每页500条，搜索200ms防抖；候选身份为(source,candidate_id)。
无RAW时可使用包内preview或中性底图；不会借最终bbox伪造候选初始几何。未解析的merged_into原样保留并禁用候选跳转。现有两包14条merged_into实际为finalID的限制见docs/phase_8。
所有操作不写回结果，不运行检测算法。Phase8新增51项QA，原428项保留；最终提交后在干净HEAD重新运行全部回归。设计/提交前证据在docs/phase_8，权威最终回执在ignored output/phase8_final及Codex交付目录。Phase9未开始，等待人工审核。

## Phase 9 人工复核准入

第五页“人工复核准入”将Audit REVIEW与人工ReviewTask分离。固定只读派生策略位于ui/models/review_admission/review_admission_v1.yaml；四bucket分别计数Defect/Candidate，人工队列支持类型/优先级/原因/Band/Source筛选、全局排序、详情及跨页定位，其他bucket仍可浏览。
无效非空finalID保留原值并生成HIGH Candidate一致性任务；普通孤立Candidate任务要求原始finalID为None。有效关联候选聚合到Defect主任务。所有最终Defect保留在AUTO_ACCEPT/MANUAL_REVIEW中。
两组真实任务83/49，26_1为TARGET_NOT_MET、26_2达标；全部保留，不Top-N截断。仅评估工作量和可解释风险，不宣称准确率/召回率。设计和提交前证据见docs/phase_9；最终commit上的串行验收回执在output/phase9_final及Codex交付目录。人工审核写回尚未开始。

## Phase 10 人工复核执行与审核记录 V1

第五Tab保持五个顶层页签，在“人工复核准入”内提供“复核队列 / 准入统计”。填写审核者后创建/恢复独立会话；五类人工结论写入output/reviews，不改变正式InspectionResult或算法疵病统计。选择任务、核对原对象和空间关联，选择结论后“保存并下一个”；重复目标/新增漏检需明确确认。表格/图像聚焦时1–5选择对应结论，Enter提交；输入框内数字仍作为文本输入。
每次提交原子持久化、按任务递增revision，历史全部保留；其他审核者修改须明确确认。恢复时停在首个PENDING；结果/策略/冻结任务不匹配为只读。UNCERTAIN计入已处理但单独统计，可后续追加专家revision。独立人工统计与CSV/JSON导出不能视为完整GT或整体准确率/召回率。
真实26_1/26_2仍为83/49任务，自动QA仅创建空会话、132条全部PENDING，没有人工标签。原算法、schema1.0、AUTO、正式Repository、Golden及Phase9策略冻结。设计和提交前证据见docs/phase_10；最终提交串行验收写output/phase10_final和Codex交付目录。完成后等待人工审核，下一阶段未开始。

## Phase10 Revision 正式结果与RAW证据

第五Tab改为“人工复核”。临时检测结果先保存正式包，成功后新VM绑定SaveRecord.result_dir；历史正式结果从配置的结果库完整校验加载。关联原始RAW按钮只做运行时只读关联，SHA256、尺寸和big/16/12格式通过后才可提交五类结论。无RAW可查看/恢复会话但不能提交，重启需重选RAW。RAW路径不进入审核协议或正式包。设计见docs/phase_10_revision，最终门禁回执在output/phase10_revision_final和Codex交付目录，下一阶段未开始。
