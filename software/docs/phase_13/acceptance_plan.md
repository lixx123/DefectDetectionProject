# Phase13 验收与候选冻结

基线 109c05e6218111d2205979f599fe9e73a5c1744e，开始时 git/diff clean。仅更新 GUI 版本元数据、发布封装/QA 与文档，不改变算法、AUTO、协议、模型、策略、Golden 或人工审核语义。Engine reference 1.0.0 原包逐字节复用。

再次用最终 GUI EXE 真实执行 26_1/26_2，并用现有严格证据比较器对比物理语义和全部 ReviewTask。用户指定同批历史处理过的 27-1、28-1，允许替代未见盲样做重新提取补充验收。明确标记 historical_processed=true、strict_blind=false；known_sample_match=false 与真正盲样是两个独立概念，不混淆。未知路径依据实际 SHA256、冻结 run_raw 的二选一 hash guard、实际 fresh 执行和输出无历史 lineage 归档证明。

盲样质量必须由真实人工判读签收；AI 图像预审不冒充人工评价。提供 LARGE/MEDIUM 全集与 SMALL/高优先级队列的 QA 可视资料及人工评价模板。真实生产审核记录始终为 0。

用户确认异机、正式代码签名均暂无。记录 NOT_AVAILABLE 与真实 NotSigned；不修改任何安全设置。缺少强制异机条件时仅条件验收，不创建最终 v1.0.0 Tag。提供异机部署验收包与操作说明，等待后续真实异机证据，不用本机换目录冒充。

Fail closed 六种实际 EXE 案例：缺少 runner、runner 一字节变化、manifest bundle hash、protocol、schema、supported_input。所有变体只在新建独立 QA 副本修改；正式 Engine 不动。切换 actual A -> stub B -> A，stub 不执行、不交付。旧 Phase4/6-12 通用 schema 包与 Phase12_Engine 包从只读拷贝加载，检查其自身 Engine/AlgorithmInfo；不重新检测/重写历史结果。

最终报告、版本、校验和、补丁及测试证据写入外部 Phase13 目录，避免填报告提交号导致未受测提交。Phase14_started=false。
