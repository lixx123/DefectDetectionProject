# CHANGELOG

## Phase 5 系统回归与 Golden Set — 2026-10-21
- 增加 FAST/GOLDEN/REAL/RELEASE profile、明确 marker 与跳过/缺失证据失败策略。
- 建立两张 × 三模式的对象/资源/ROI/audit 黄金元数据与 schema/Enum contract，物理基线不变。
- 统一比较器按精确 source set / global mask 对应对象，允许 ID/时间元数据变化，关键语义变化阻断。
- 建立 AUTO/sentinel、十类回退、FULL 失败拒绝存库、Repository 包与索引导出门禁。
- REAL 显式传入 RAW，默认不实算；要求 REAL 未执行时 NOT_COMPLETE，blind 数据 NOT_AVAILABLE。
- 保留原 255 项测试，不进入 GUI/Phase 6。

## Phase 4 结果持久化与 Repository — 2026-10-21
- 新增 JsonResultRepository：原子保存、不可覆盖、正式门禁、完整资源归档、manifest 校验、历史查询与可修复 JSONL 索引。
- 新增路径/junction 防逃逸、文件 SHA256/大小/覆盖检查、结构化 verify，以及完整 ZIP 导出和 CRC/SHA256 回执。
- Detector 仅新增实际配置运行快照；InspectionService 组合检测与持久化，生产默认加载 YAML，不改变 domain/schema/AUTO。
- 两组既有 Phase 3 revision AUTO 结果零语义变化保存/回读，配置恢复 hash 精确匹配，日志从原运行目录归档；不重新运行算法。
- import_package 延期 Phase 4.1；不提供删除，不进入 Phase 5。

## Phase 3 审计修订与冻结 — 2026-10-21
- 集中维护 FilterReason/CandidateDisposition，修复 J5_OUTSIDE_WORK；未删除/未证实噪声候选保持待审，不再无差别 LOW_EVIDENCE。
- 最终 membership 与可核实合并目标、历史未重算语义和原始决策字段得到保留。
- 用户确认方案 2：schema 1.0 不变；明确尺寸/几何筛除用 OTHER + reference_reason_category。
- production_v1.yaml 状态更新为 REFERENCE_ENGINE_CONNECTED；明确参考工程和虚拟环境依赖。
- 新增只读 remap 工具；六组已有真实输出门禁通过，逐对象/逐像素/统计/来源零物理变化，不重跑算法。
- 完整测试与保护核对通过，停止于 Phase 3，不进入 Phase 4。

## 0.3.0 — 2026-10-20
- Phase 3：GUI无关Detector.inspect真实接口，子进程参考算法适配与每任务隔离。
- 生产AUTO优先ROI_BH，安全/输出拒绝后直接FULL；异常、超时和取消明确记录。
- RAW、ROI/Band、精确mask、Feret、全源/反向lineage、恢复与成员记录、统计和资源SHA映射。
- 26两帧FULL/ROI_BH/AUTO六次真实运行通过；ROI/FULL与冻结基线物理/来源差异0。
- 首帧5个运行内顺序ID排列变化单列，不修改引擎编号；按稳定来源和真实mask匹配。
- 全部145项测试通过，包含冻结99项；原独立逐图块QA、Phase 1 smoke和pip check通过。
- 1317个保护文件0变化；schema 1.0及domain保持冻结。未进入Phase 4。

## Phase 2 修订与协议冻结 — 2026-10-20
- schema保持1.0；ExecutionAttempt.plan为唯一计划事实源，移除ExecutionInfo顶层重复字段。
- final_attempt/final_plan只读引用最终采用attempt，不复制或序列化计划。
- 修复Band几何失败回退示例，保留INVALID定位与问题Band供审计。
- 新增validate_final/FinalValidationError，区分草稿codec与正式结果门禁。
- 明确Execution QA与Result QC职责，核对数量、面积、审计及AUTO回退语义。
- 保留其他未知字段/extensions，明确拒绝旧草案已退休的顶层计划键。
- 全部新软件99项测试通过；Phase 1 smoke、pip check通过；1298个保护文件哈希不变。
- 原算法未执行或修改，Phase 3未开始。

## 0.2.0 — 2026-10-20
- Phase 2：长期领域模型、ROI/Band、候选审计、人工审核不可变快照与历史。
- AUTO策略数据约束：ROI_BH失败直接FULL，ROI_J4/LEGACY_REPLAY仅用于高级调试/回放。
- 用户默认尺度3.2μm/px，像素量保留、面积平方尺度换算，区分用户尺度与计量标定。
- schema 1.0中文JSON往返、未知新增字段保留、显式迁移骨架、相对资源引用。
- 三种YAML配置及语义配置哈希；高灵敏度配置未擅自调整阈值。
- 56项领域单元测试、纯标准库示例、Phase 1窗口smoke和pip check通过。
- 765个原算法/既有输出/Phase 1代码保护文件SHA256不变；原算法未运行。
- 仅完成Phase 2，不进入Phase 3。

## 0.1.0 — 2026-10-20
- Phase 0：盘点原算法，建立源码回滚副本与独立运行基线。
- Phase 1：独立五层目录、中文最小 PySide6 窗口、独立虚拟环境。
- 未进入 Phase 2，未更改算法参数或源代码。

### 验证记录
- 原工程354项测试通过；双帧独立像素QA通过。
- 相对v4：新增/消失/位置/尺寸/分类变化均为0。
- 独立环境pip check和中文窗口实际启动截图通过。
- 277份原文件SHA256前后相同。

## Phase 6 ImageViewer V1

新增独立图元 Viewer、RAW 只读显示、Band/ROI、最终对象表格与双向联动、后台服务及显式正式保存。冻结算法/领域/Repository 保持不变。

## Phase 7 疵病详情与统计分析

新增只读分组详情、原始像素局部图、最终对象统计/尺寸和Band柱图、显示筛选及排序感知导航。冻结领域、Repository、AUTO、Golden和算法保持不变。

## Phase 8 检测过程与候选审计 — 2026-10-21
- 第四页只读审计、真实attempt/QA、双图去向统计、动态source/stage、通用events。
- tuple CandidateKey、后台全局筛选排序、虚拟200/500/1000分页、50000候选响应验证。
- 初始候选局部RAW/preview/中性底图、revision去陈旧请求；初始测量与最终框语义分离。
- 双向lineage与隐藏显示筛选清除；merged_into歧义/缺失目标不猜测。
- 51项新增测试，保留428旧测试；About移除旧Phase6文案。
- 冻结schema/AUTO/Repository/Golden/原算法，不进入Phase9。按最终commit重跑全部门禁并输出独立回执。

## Phase 9 人工复核准入与候选分层 — 2026-10-22
- 新增独立只读策略、确定性四bucket决策与三级优先级、多原因/evidence、Defect优先任务聚合。
- 按用户决定区分HIGH无效链接一致性任务与原始finalID为None的普通孤立任务。
- 第五Tab、全量分类浏览、虚拟分页队列、筛选排序、中文原因解释及跨页局部资源复用。
- 真实26_1为83任务(超建议50，完整保留)、26_2为49任务；71个最终Defect保护，14历史MERGED仅审计。
- 新增78项测试；旧479项保留，仅总页签数量断言4→5。
- schema1.0/AUTO/Golden/Repository/原算法冻结，实算0，人工审核写回未开始。

## Phase 10 人工复核执行与审核记录 V1 — 2026-10-22
- 独立human_review_v1协议、会话/任务/结果/策略摘要绑定、五类人工结论和严格目标校验。
- 与正式结果库分离的原子校验存储，OS文件锁、乐观revision冲突检测、完整历史与会话事件；其他审核者追加需确认。
- 第五Tab内连续审核、保存并下一个、恢复首个PENDING、全局筛选排序、图像身份隔离、空间目标定位及CSV/JSON最小导出。
- 真实任务仅PENDING空会话，所有审核提交QA为合成数据；结果零写回，算法执行0。下一阶段未开始。

## Phase10 Revision — 2026-10-22
- 正式Repository来源能力与服务硬门禁，保存后完整重载并替换VM。
- 异步只读RAW关联、流式SHA256/格式/尺寸检查、Windows只读租约、过期返回隔离与切换释放。
- 无verified RAW禁止提交；复核Tab文案、空图防御、OS唯一测试临时父目录。
- 新增26项严格测试，真实83/49任务及0审核标签保持；算法/领域/Golden/正式Repository/Phase9策略冻结，实算0。
