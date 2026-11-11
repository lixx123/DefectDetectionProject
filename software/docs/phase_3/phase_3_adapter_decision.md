# Phase 3 适配方案（开发前决策）

2026-10-20。修改前工作区干净，冻结提交139a6c9已核对，checkpoint=116b113。Phase 2 schema 1.0保持不变。

## 选择子进程Wrapper

原main.py调用scripts/run_two_level_unified.py/run_unified_raw_input.py；这些模块import config/user_config.py，包含C.OUTPUT_ROOT、DATA_ROOT，以及J4.OUTROOT、J5.OUTPUT_ROOT、old.J4P/J5P、I/II/E等历史输出全局路径。fresh_j5在运行期间临时替换历史路径，J4/J5也临时修改全局输出目录。直接嵌入长期GUI进程会有模块缓存、全局状态和并发污染风险。

选择独立Python子进程，以原工程.venv的依赖执行原函数。新软件core/runtime/engine_worker.py是薄Wrapper：完整导入原模块之后，仅将运行输出C.OUTPUT_ROOT指向新任务engine目录，保留已解析的历史参考源路径；按明确mode调用现有run_raw，不修改阈值或任何数学函数。该路径重定向是输出配置适配，不改原工程文件。

每次attempt使用全新子进程与唯一子目录，运行日志独立。原J4/J5内部路径替换发生在子进程，进程结束即销毁；不得在父进程import原算法。父进程只用领域模型和输出解析器。

## QA与输出

生产AUTO只运行ROI_BH，Execution QA不通过才直接运行FULL，不尝试ROI_J4。验收显式FULL/ROI_BH对照与生产AUTO独立。

Wrapper先用原Band定位/build_plan做预检。ROI计划不安全时保存真实失败证据并退出，不借原脚本内部全图退化伪装ROI成功。成功运行后用原require_computed_response复核实际J4消费窗口与K8B工作区；原函数在检测过程中也保留同样门禁。父适配器检查J4/J5完整性、源追踪及最终表/NPZ/全分辨率mask，不仅信任acceptance里的状态字符串。

所有运行位于新工程output/runtime/<唯一task>/engine/<mode>/，原算法outputs、Phase 0 baseline、原v4均只读。ArtifactReference统一相对本次result.json目录。原引擎原始CSV/日志保留为运行证据，领域JSON不包含机器绝对路径。

## 失败与演进

子进程非零退出、超时、取消、输出缺失和QA失败分别记录；真实错误按阶段/异常证据映射FallbackReason，不全部标UNKNOWN。FULL仍失败则返回FAILED草稿，无final_mode，不能通过validate_final；输入格式错误抛InputValidationError。映射失败不静默返回空缺陷结果。

不引入Repository；inspect返回内存InspectionResult。验证脚本可显式保存JSON。资源存在性、哈希、反向Defect→Candidate及统计双核对在Phase 3实现。

未来可在逐步清除原算法全局状态后替换为直接Python服务，Detector接口与领域协议不变。本轮不迁移/重写算法，也不进入GUI、报告、打包或Phase 4。


## 实施验证补充

原scripts目录为namespace package，新软件验收scripts是regular package。仅sys.path顺序不足以避免遮蔽，已在短生命周期子进程中显式固定原scripts的__path__/module spec，父进程不受影响。真实导入回归测试通过；未改原工程任何文件。
