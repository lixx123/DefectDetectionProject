# Phase 5 测试报告

320 passed in 248.47s (0:04:08)，原 255 项全部保留，新增 65 项，无 skipped。

分层：FAST 295 PASS；GOLDEN 23 PASS；另两个原工程小探针仅完整回归执行。RELEASE 内再次执行 FAST/GOLDEN，组合状态 PASS；没有真实算法重跑。

新增覆盖：精确 source/mask 匹配与 ID/时间白名单；逐字段负向退化、None/零；候选顺序归一；严格资源 hash；墙钟 WARNING；schema/Enum contract；代码影响与 NOT_COMPLETE/FAIL；十类 fallback；双失败拒绝入库；sentinel bridge/AST；缺失 Golden/RAW 明确失败；历史配置不回写；显式 Golden 更新审计；fake REAL 六模式且不声称实算；六组 Golden、两个正式包/index/query/export。

所有 Golden 对象、mask、ROI、audit、stats、execution 与包完整性 PASS；参见 golden_report.json。物理 evidence 未写，源文件前后 SHA 一致。协议与 Enum 未变化；原算法保护 1317 项完整清单无变化，原实现/旧测试 diff 为空。源码指纹与 release report 一致。

FAST/GOLDEN 的选中测试一旦 skip 就 FAIL，不允许缺本地文件后仍报通过。缺 RAW REAL 的 NOT_RUN/非零为预期负向结果，不计作实算通过。Golden 更新拒绝 CLI 的 exit=2 为预期，见 negative_cli_checks.json。

smoke、pip check PASS。原 sentinel=65535 微型探针通过，短 RAW worker 探针只验证导入，不计算昂贵算法。Blind 数据缺失，不作盲测准确率或新 RAW 泛化声明。
