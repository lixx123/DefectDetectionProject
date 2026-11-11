# Phase 3 真实回归验收报告

2026-10-20。结论：Phase 3适配、真实运行和回归检查PASS；等待人工审核，未进入Phase 4。schema仍为1.0，domain/未修改。

## 六次真实运行

| 帧 | 请求 | 实际模式 | 回退 | 对象 | 面积 px² | 小/中/大 | Band | 实际J4图块 | 新鲜源/联合审计源 |
| --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | --- |
| 26_1 | full | full | False | 36 | 20356 | 1/16/19 | 4 | 1620/1620 | 32370/32370 |
| 26_2 | full | full | False | 35 | 17709 | 0/11/24 | 4 | 1620/1620 | 8332/8332 |
| 26_1 | roi-bh | roi-bh | False | 36 | 20356 | 1/16/19 | 4 | 765/1620 | 17453/32370 |
| 26_2 | roi-bh | roi-bh | False | 35 | 17709 | 0/11/24 | 4 | 765/1620 | 4290/8332 |
| 26_1 | auto | roi-bh | False | 36 | 20356 | 1/16/19 | 4 | 765/1620 | 17453/32370 |
| 26_2 | auto | roi-bh | False | 35 | 17709 | 0/11/24 | 4 | 765/1620 | 4290/8332 |

各次Execution QA、Result QC、validate_final与JSON round-trip均PASS。两次AUTO的engine目录仅含roi-bh，没有full或roi-j4，表明生产没有因验收对照而默认双跑。FULL/ROI显式双跑独立于生产。

ROI的历史未重算源仍保留：首帧14917、二帧4042条；不把联合审计数量当作新鲜计算数量。原40702条历史源UID全部可查，无静默删除。

## 对象、像素与来源

- ROI_BH↔FULL：两帧新增/消失、位置、面积、Feret、等级、来源成员、逐对象mask变化均为0，整图二值mask差异像素0。
- AUTO↔ROI_BH：两帧以上所有物理与来源差异均为0。
- FULL↔冻结v4基线：按精确来源集合匹配，所有对象mask、位置、面积、Feret（按旧CSV精度）、等级与来源一致，整图mask差异像素0。
- 原工程独立verify_two_level_unified另行执行，两帧各765个实际ROI图块的Black-Hat窗口响应、J4源标签/像素差异均为0；WORK/EDGE成员和K8B种子核对通过。
- 已确认四处暗斑297/398、348/370px²，独立原QA逐像素精确匹配；人工负例交集0。既有入选划痕/十字目标包含在基线全mask精确保持检查中，不额外声称对未知真值零漏检。

## 首帧5处顺序ID变化（已如实保留）

旧冻结回放与新鲜流水线对后5个对象的顺序编号不同。没有重编号掩盖差异，也没有修改算法。以稳定candidate/source集合识别同一对象，再独立核对原图bbox与真实mask。变化仅为运行内ID排列，见下表；对应物理量与来源成员无变化。

| 旧v4编号 | 新鲜FULL编号 | 稳定来源 |
| --- | --- | --- |
| F1_FINAL_0032 | F1_FINAL_0033 | B:F1:B04:C0004577 |
| F1_FINAL_0033 | F1_FINAL_0034 | B:F1:B03:C0000739 |
| F1_FINAL_0034 | F1_FINAL_0035 | B:F1:B03:C0001837 |
| F1_FINAL_0035 | F1_FINAL_0036 | B:F1:B03:C0001908 |
| F1_FINAL_0036 | F1_FINAL_0032 | B:F1:B03:C0003615 |

初期按顺序ID直接比较产生的诊断保留在comparison_diagnostics.json，其FAIL是身份匹配策略的假变化，不是最终验收结论；正式逐对象差异见phase_3_roi_vs_full_comparison.json。

## 实施过程与范围

一次子进程scripts命名空间冲突使26_2 ROI启动失败，失败JSON正确为FAILED草稿，validate_final拒绝；修复子进程命名空间后续跑成功，原算法未改。新增真实导入探针防止复发。

六批原始计算输出均由真实Detector.inspect运行产生。最终适配代码增加RAW recovery/J5成员关联后，对这些同一批真实输出再次完整映射到新的verified_final_mapping目录并核验全部资源SHA、门禁与往返；没有覆盖初版JSON或失败草稿，也没有把该映射步骤伪称额外算法重算。最终数据路径见final_acceptance_runs.json和phase_3_verification.json。

FULL1/2引擎实际耗时分别为618.887/257.304秒；ROI/AUTO引擎通常明显更短，完整接口/验证耗时另含来源映射与JSON校验。本报告仅记录本机观测，不承诺性能上限。

145项软件测试、Phase 1 smoke与pip check通过；1317个原算法/基线/冻结协议保护文件哈希不变。原始JSON/NPZ/PNG和全部日志留在output/phase3_validation，Portable数据包包含最终统一结果及所引用资源，不含RAW和完整J4/BH缓存。

## 真实限制

- 71个是当前自动规则入选对象，不等于71个人工真值；本阶段不评价盲测精确率/召回率。
- 原引擎没有可靠点/划痕类型或宽度等时保留None/UNKNOWN，划痕总长不冒充全部Feret之和。
- 当前适配仍依赖原工程及其环境/审核参考资料；不是独立EXE。
- 未开发GUI检测、ImageViewer、报告、数据库、正式Repository或打包。完成后停止，等待人工审核。
