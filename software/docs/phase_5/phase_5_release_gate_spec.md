# Release Gate

FAST + GOLDEN + Repository + schema contract + AUTO/sentinel + 原算法保护全部成功，才可能 PASS。选中测试不得跳过；Golden 必须覆盖六个 sample/mode 和两个正式包。

状态：PASS、PASS_WITH_WARNINGS、FAIL、NOT_COMPLETE。REAL_ENGINE_REQUIRED=true 且没有真实执行证据时 NOT_COMPLETE；真实失败或其他门禁失败则 FAIL。默认 release 不自动启动算法，明确写 real_engine_required/executed/NOT_RUN。需要人工显式 --execute-real --raw-root 或独立 --profile real；fake 不满足 REAL 证据。

影响判断基于冻结基线 commit 到当前工作树（含未跟踪文件）。core/domain/configs/application 与未知路径保守要求 REAL；tests/docs/regression/已知回归脚本/pytest.ini/README/CHANGELOG/ui 等已知非算法路径可不要求。--require-real 可强制提高要求，不能降低自动判定。原算法保护失败直接阻断发布。

每次 release 输出 JSON/Markdown，包含 tested Git HEAD、dirty 标志、baseline、变更路径和 tested_source_fingerprint；以及 FAST/GOLDEN、Repository、schema、AUTO、原算法保护、样本、差异、warning、REAL 状态与最终结论。开发验收在提交前运行，报告中的 HEAD 是已审核基线 + 明确工作树指纹，不冒充最终提交；final_commit.txt 在提交后关联最终 commit。普通 CI 应在稳定 checkout 运行。

黄金数据和正式包损坏会 FAIL；Golden 缺失不以 skip 放行。REAL 缺少 RAW 为 NOT_RUN 并返回非零。当前 Golden 含历史人工信息，blind validation NOT_AVAILABLE；本门禁不代表盲测、GUI 或 EXE 发布验收。

原 255 项测试保持，新增负向测试证明对象/资源/协议/策略变更能够拒绝。完整测试额外运行既有两个原工程小探针，保护 sentinel=65535 的实际 guard；FAST 则通过 bridge QA 拒绝与十种失败 fixture、实际 scheduler/worker AST 断言验证安全回退。
