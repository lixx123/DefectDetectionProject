# Phase 7 工程验收

工程QA通过，等待人工审核；停止，不进入Phase8。基线 `6f0fd69560a2155d477009ee792613acef371a2f`，验证源码指纹 `ecf2071a349752de4381bdddf9114a738a73ccc2d43848537573a61f8e2f8f56`。提交与clean回执见final_commit.txt/交付清单。

## 已实现

检测、疵病详情、统计分析三页；详情按五组字段显示当前最终对象，带真实像素局部/框/mask三模式、字段Tooltip和本次尺度说明。无RAW不阻塞数值；可显示既有当前对象NPZ mask，不伪造灰度。只读合并历史不扩展完整Audit页。

统计以存储statistics为摘要事实源并与最终对象核对；尺寸、Band、类型、ROI汇总来自同一最终集合，两个原生数量柱图。缺测量保留None；可信WORK分母缺失显示—，不用整图面积。invalid Calibration屏蔽物理量，0对象安全。

尺寸/Band/类型可组合筛选，表格和框同步；统计始终全量。ID/面积/Feret/尺寸/Band排序后按proxy可见顺序翻页，SelectionController共享defect_id。局部I/O复用后台worker，代次键忽略过期返回。截图检查发现的快速换对象控件叠影已修复并增加测试。

## 实际正式结果

- 26_1：36对象/20356px²，逐个浏览36，尺寸/Band/类型计数和均36；LARGE筛选19，清除恢复36。
- 26_2：35对象/17709px²，逐个浏览35，尺寸/Band/类型计数和均35；筛选和清除通过。
- 原RAW不可用仍可查看详情数值、当前对象mask、全量统计。完整结果前后摘要相同，零写回。动态3/4/5 Band、单对象、0对象、未分类、无效尺度、缺测量及损坏mask SHA均覆盖。

## 自动门禁

新UI40/40、全部软件428/428（旧388原样保留），FAST397/397、GOLDEN29/29、RELEASE、smoke、pip check全部PASS，无skip。新增56项要求映射见requirement_checks.json；原始JUnit与日志随附。

REAL_ENGINE_REQUIRED=false，REAL_ENGINE_EXECUTED=false，algorithm_executions=0。普通验收继续启用外部RAW禁读审计，外部访问尝试0。源码机器路径生产/永久测试均0命中。schema1.0、AUTO、Repository、Golden基线及原算法765项保护均不变。旧ImageViewer及ResultViewModel保持不变，app/application/core/domain/config/infrastructure/regression/scripts无diff。

## 审核边界

8张1680×1000截图已生成并目视检查，真实历史包71个对象经过脚本交互；人工接受仍待用户确认。局部RAW验证使用synthetic数据，不依赖工程机器真实RAW。合并历史仅当前Defect只读文本区；没有完整候选审计、审核写回、Excel/PDF报告、数据库或打包。

已保留Phase6门禁标签的历史原始输出，本阶段状态以phase_7_verification.json为准。Phase8_started=false。
