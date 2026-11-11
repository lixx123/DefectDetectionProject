# Phase 3 修订前：FilterReason 协议缺口与确认项

日期：2026-10-21。

状态：已完成只读核对并建立 checkpoint；按提示词的 schema 缺口规则停止。本轮未完成修订或正式冻结。

## 当前基线

- 工程：`D:\疵病检测\DefectInspectionSoftware`。
- HEAD：`6a2f2219e9555d2eef1ba630b5031ca21311a988`，开始时工作区干净。
- Checkpoint tag：`phase3-revision-checkpoint-20261021`，指向上述提交。
- 保护 manifest 的 1317 项文件 SHA256 全部匹配。
- 已读取六组现有真实 engine 候选台账；没有重新运行 Black-Hat、J4、J5、K8 或 RAW recovery，没有重新映射结果。

## 缺口

当前 `domain/enums.py` 的 FilterReason 只有：

```text
OUTSIDE_WORK_REGION
BACKGROUND_NOISE
LOW_EVIDENCE
USER_REJECTED
SAFETY_GATE_REJECTED
OTHER
```

其中非工作区、噪声、安全门、人工否定、证据不足和无法归类都有现成类别。缺少提示词第五节 5.3、第十七节第 3 项要求的明确尺寸/几何筛除类别，也没有语义等价项。

`OTHER` 能承载兜底值，但仅凭该枚举，GUI 无法区别“明确尺寸/几何筛除”和“无法可靠归类”。使用扩展字段补充细分类可以避免新增 wire 值，但这需要确认是否满足本次要求；不能自行把它视为一个已有的尺寸/几何等价枚举。

## 真实数据证据与边界

六组 fresh 台账行数分别为：F1 FULL 32370、F2 FULL 8332、F1 ROI_BH 17453、F2 ROI_BH 4290、F1 AUTO 17453、F2 AUTO 4290。

F1 FULL 中 `J5:F1:DEFECT_00001` 的真实字段为：

```text
primary_visibility_layer = J5_OUTSIDE_WORK
decision_reason = J5_J5_OUTSIDE_WORK
final_ID = 空
```

这个问题已有 `OUTSIDE_WORK_REGION` 可以准确表达，无须为它修改 schema。当前 audit mapper 将无最终目标且非 historical-only 的候选统一设为 FILTERED / LOW_EVIDENCE，确实需要修订。

但不能把六组台账中的以下记录当成“缺少尺寸筛除枚举”的实际筛除证据：

- `J5_J5_WORK_SMALL` 是工作区小对象分层，不能仅据 SMALL 推断已过滤。
- `K8C_MICRO_HIDE_SUGGESTION_AREA_1_OR_2PX_PROVISIONAL_NO_DELETE` 明确是建议隐藏、未删除。
- `K8C_MICRO_REVIEW_AREA_3_TO_7PX_NOT_PROVEN_NOISE` 明确是待审、未证明为噪声。

这些记录应结合最终 membership、执行状态与归档信息判断，不能伪造尺寸过滤或噪声结论。六组 fresh 台账中未发现字面上的 `AREA_TOO_SMALL`、`SIZE_FILTER`、`MIN_AREA`、`GEOMETRY_REJECT` 决策原因。因此，本报告区分“本轮要求覆盖的类别缺口”和“现有六组已证实的尺寸筛除实例”；后者未得到证实。

每组完整 reason 分布、目标候选原始字段、台账路径和 SHA256 见同目录 `schema_gap_evidence.json`。

## 建议的最小调整及待确认事项

请确认以下一种处理方式：

1. 严格提供独立结构化枚举：只新增 `FilterReason.SIZE_OR_GEOMETRY_FILTER`，其余枚举不变。它会增加 wire-level 值，需要同时明确 schema 版本与旧消费者兼容策略，不能未经确认继续声称 frozen schema 1.0 完全不变。
2. 保持 schema 1.0：明确允许尺寸/几何原因使用 `OTHER`，并在审计 extensions 中保留明确细分类，例如 `reference_reason_category = SIZE_OR_GEOMETRY_FILTER`。真实原始 reason、stage、visibility、classification 继续无损保存；报告和测试注明这不是现有等价枚举，未来 GUI 必须读取细分类。这需要放宽本轮“稳定 FilterReason 直接表达该类别”的要求。

其余集中映射、待审/合并/归档 disposition、配置状态修正、六组重新映射及回归，均待此项确认后继续。本轮未修改上述功能，未将 schema 缺口报告当作 Phase 3 冻结完成。

## 停止依据

用户指定提示词第十八节：

> 如果已有足够枚举，直接使用。
>
> 如果没有，不要为了方便直接在 enum 中乱加值。
>
> 先输出：filter_reason_schema_gap.md
>
> 然后停止等待人工确认。

这里的停止是对“缺少尺寸/几何等价类别”的保守解释；不是工具审批或文件权限阻塞。未请求修改原算法，未进入 Phase 4。没有执行本轮完整测试、六组 remap、物理差异比较或正式冻结提交，也不将上一轮通过记录冒充本轮验证。
