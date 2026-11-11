# Phase 6 显示修订与正式冻结报告

工程冻结条件21项全部 PASS，停止于 Phase 6；人工审核待确认。指定基线 `7690c1ed33a4435af4cdf5dc6012a2eeff2678c1`。最终提交回执见 final_commit.txt，发布验证源码指纹 `872a1c54846add6f398230d90e8f57bfa642fc9071eae820a95676da38d840da`。

- FINAL 高倍率真实 RAW 局部：实现；ORIGINAL 保持。阈值0.7，防抖30–40ms，单次≤4,000,000像素，超限回退thumbnail。
- 层序 RAW detail -9 < mask -8 < bbox +10/+15 < label +20；mask开/关不影响RAW detail可用性。
- display bbox：1.5×，最小6×6原始像素（边界clamp前）；measurement bbox、中心、面积、Feret和完整结果零修改。
- 窗口与QApplication正式名称已同步；app/main.py未改动，未改变现有结构、主题或表格。
- 旧349项全部保留且通过，新增18项；全部软件367/367，UI47/47，FAST339/339，GOLDEN26/26，RELEASE、smoke、pip check PASS，无skip。
- Golden保持26_1=36/20356 px²，26_2=35/17709 px²；六组物理对象/掩膜/ROI/Band/audit和两个Repository包对比PASS。
- REAL_ENGINE_REQUIRED=false；algorithm_executions=0；无真实Detector运行。读取RAW用于显示不计作算法执行。旧算法单元测试使用原有fake fixtures，不对真实RAW执行Detector。
- schema_version=1.0，AUTO不变，原算法765项保护零变化，原有349项测试文件零改动，未进入Phase7。

## 真实显示证据

只读组合真实26 (1).raw与Phase4冻结26_1正式包。RAW SHA256与结果input_info一致，显示前后相同；完整InspectionResult字典摘要前后相同。显示脚本显式禁止Detector.inspect及子进程启动。选中真实 `F1_FINAL_0028`，面积36.0px²，measurement bbox `[5100, 2940, 5111, 2945]`，display bbox `[5097.25, 2938.75, 5113.75, 2946.25]`，1000%倍率。检查真实crop像素与原DN的LUT逐点抽样一致。

必需六图及额外mask关闭灰度截图均1680×1000。已目视检查真实背景像素、白色选中框、mask/框顺序、编号和右侧真实测量详情；截图是工程检查，不替代人工接受，也不加入像素Golden。

## 性能观察

5轮×20次缩放/平移/刷新，detail item始终为1。工作集在410.73–410.73MiB，私有提交在814.55–814.55MiB，未见持续增长。清理后工作集261.8MiB；观察脚本仍保留冻结result/vm局部变量，因此不要求降至初始值。非严格benchmark，不能据此证明没有任何泄漏。

详细21项冻结映射见freeze_conditions.json。Phase5门禁的phase6_started=false为原生成器历史固定标签，不代表本轮未实施，未为修饰标签修改判定规则。本轮无需调整冻结协议或算法；停止，等待人工审核。
