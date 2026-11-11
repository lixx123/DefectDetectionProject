# DefectDetectionProject｜26_1最新疵病识别算法开发程序报告执行规划

## 一、目标

以 `26 (1).raw` 为唯一贯穿示例，严格按照当前最新生产链路 `roi-bh` 的真实程序调用顺序，编写一份“算法开发程序报告”。

报告不是历史时间线，也不是论文式概述，而是回答：
1. 为什么做这一步；
2. 程序实际怎么做；
3. 输入是什么；
4. 输出是什么；
5. 关键参数是什么；
6. 失败时怎么处理；
7. 为什么下一步需要它。

## 二、报告主线

严格沿以下主线核对源码并撰写：

```text
main.py
→ RAW输入与QC
→ K8A工作带定位
→ 两级ROI计划与可信性判断
→ ROI Black-Hat
→ J4原网格稀疏调度与局部检测
→ J5跨tile全局合并
→ K8B工作带候选补充
→ K8C/K8D证据筛选与RAW外围恢复
→ 历史/新鲜来源关联与不静默丢源
→ Unified Final对象整合与去重
→ 精确mask尺寸计算
→ 最终矩形框渲染
→ 独立QA
```

历史Case03A～K只在“为什么保留/淘汰某方法”时作为旁注，不进入主流程编号。

## 三、源码审查清单

按执行顺序读取并核对：
- `main.py`
- `config/user_config.py`
- `scripts/run_two_level_unified.py`
- `src/detection/two_level_roi.py`
- `src/detection/case03k8a_band_locator.py`
- `src/detection/blackhat.py`
- `scripts/run_case03j4_fullscan.py`
- `scripts/run_case03j5_global_merge.py`
- `src/detection/case03j5_seam_match.py`
- `scripts/run_unified_raw_input.py`
- `src/detection/case03k8b_perband_trial.py`
- `src/detection/case03k8c_noise_review.py`
- `src/detection/case03k8d_group_stability.py`
- `src/detection/unified_raw_recovery.py`
- `src/detection/unified_proposal_selection.py`
- `src/visualization/unified_final_boxes.py`
- `scripts/verify_two_level_unified.py`
- 对应测试与26_1最新输出证据

## 四、关键参数只写生产主链相关项

至少包括：
- RAW：11276×9200、16 bit大端容器、有效12 bit
- Black-Hat：3/5/9/15/31 px
- Hysteresis：H170/H230
- J4：core=256 px、halo=64 px
- K8A：工作带定位主要阈值、边缘拟合与可信性门控
- Two-level ROI：review margin、minimum algorithm halo、实际算法半径
- ROI-BH：chunk、extra RAW halo、65535未计算哨兵
- J5：跨tile关联关键距离/方向/DoG约束
- K8B/C/D：分带阈值、RAW证据和安全恢复关键参数
- 尺寸：面积=exact mask像素数；长度=max Feret
- 显示：矩形框与mask测量分离

不在正文堆叠与主链无关的历史实验参数。

## 五、26_1贯穿数据

优先引用最新已验证结果：
`outputs/K8A_TWO_LEVEL_FINALGUARD_26_1_ROI_BH_20261020_v2`

记录：
- K8A工作带数量与几何
- ROI计划
- 1620→765 tile调度变化
- Black-Hat计算范围
- J4/J5对象数量变化
- K8B/K8C/K8D阶段数据
- 最终对象36个
- 最终面积20356 px²
- 已确认暗斑297/398 px²
- F1_FINAL_0029=3469 px²
- 独立QA全部差异为0

## 六、报告章节结构

1. 工程目标与输入数据定义
2. 主程序入口与运行模式
3. RAW读取与QC
4. K8A工作区域自动定位
5. 两级ROI计划与安全外扩
6. ROI多尺度Black-Hat
7. J4局部检测
8. J5跨tile全局对象化
9. K8B分工作带补充
10. K8C/K8D证据筛选与RAW安全恢复
11. Unified Final融合、去重和来源审计
12. 精确mask与尺寸计算
13. 最终显示与结果文件
14. 独立QA与安全门禁
15. 26_1完整运行数据流总结
16. 当前算法边界与后续可扩展项

## 七、写作要求

- 完全按真实代码执行顺序。
- 每一步必须给出“目的→程序→输入→算法→参数→输出→异常分支→与下一步关系”。
- 不把工程自测通过等同于真实Recall/Precision。
- 不把3.2 μm/px直接解释为样品物面尺寸。
- 不把显示框面积当成疵病面积。
- 不把W005写成生产工作区目标。
- 不把NON-WORK候选静默删除；明确说明“生产不报告，但历史来源保留审计”。
- 代码名、函数名、文件名以当前源码为准，不凭记忆补写。
- 若代码与旧文档不一致，以当前源码+最新26_1实跑证据为准，并在报告中注明。

## 八、验收标准

正式报告完成前必须满足：
- 主链调用关系已逐文件核对；
- 26_1最新输出与源码逻辑能一一对应；
- 关键参数均可追溯到配置或代码；
- 每个阶段均能说明输入与输出；
- fallback、sentinel、source audit等安全逻辑明确；
- 不出现“历史阶段名称替代当前真实执行步骤”的混淆。
