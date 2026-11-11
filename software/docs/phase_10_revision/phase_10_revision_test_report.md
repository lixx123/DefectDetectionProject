# 修订测试报告（提交前）

新增26项严格集成/安全测试，完整门禁不mock。保留原639项断言；旧Phase10协议/界面单元测试仅在本模块fixture中隔离新增证据前置条件，以继续验证revision/决策协议；两组旧真实Golden测试改为注入真实正式库绑定，未mock门禁。旧Phase9唯一文案断言按要求“人工复核准入”→“人工复核”。新26项覆盖真实Repository保存、完整加载、RAW安全和提交，不借旧隔离fixture绕过资格。

局部合并回归209项通过；新测试26项全部通过。提交前全量结果以precommit/all_tests.xml为准。最终commit上计划全665 / FAST628 / GOLDEN35 / RELEASE / smoke / pip check，全部串行；这是计划，权威执行值在最终verification。

覆盖：临时结果含RAW仍被UI和服务拒绝；显式staging authority拒绝；正式无RAW只读；SHA/尺寸/位数/端序/格式/缺失文件；同名错内容/异名同内容；流式read上限；read-only文件租约；原始DN与LUT像素；RAW解除/切换/过期返回；后台GUI心跳；保存后真正新正式VM/原字典/任务集合不变/当前RAW重验证；保存失败；重启重新关联；CSV/JSON无路径；空图防御；旧临时目录残留隔离。


## Evidence Fix Only

09 已从真实 26_1 正式结果和正确 RAW 重新渲染；旧图与06重复的问题已定位并修复。详见 phase_10_revision_evidence_fix.md。源码无功能改动，真实132任务仍全部 PENDING、0记录/0标签。最终门禁须在本次提交后的同一干净HEAD完整执行，以外部交付回执为准。
