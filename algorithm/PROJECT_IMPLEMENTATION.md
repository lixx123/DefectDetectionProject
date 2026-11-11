# 工程实现与变更记录

本文件持续记录每个阶段的实现、验收和未确认事项。算法参数如有修改，必须同步追加记录。

## 当前状态

- 当前阶段：Case03-A-R1阈值候选、严格零方差和真实密度可视化修订
- 工程目录：`D:\疵病检测\DefectDetectionProject`
- 旧Case01配准：停止作为主流程，历史结果保留
- 下一阶段：停止，等待用户对Case03-A-R1密度图、统计和原尺寸patch进行视觉验收；不得自动进入Case03-B

### Case02实际运行记录（最终运行）

- 最终运行目录：`outputs/case02/run_20260930_153727/`。
- 代表图：样品26~30的第1帧，共5张；5/5完成，统一使用3/5/9/15/31 px椭圆结构元。
- 输出核对：`blackhat_statistics.csv`共30行（5张×5尺度+5张融合），每张图均有原始预览、5个尺度响应、max融合、胜出尺度图和Top-20 patch材料。
- 数值核对：原始输入保持12 bit DN；Black-Hat响应为非负`uint16`；未发现NaN、负值或dtype溢出；各尺度最大值存在差异。
- 代表图融合峰值DN：样品26/27/28/29/30分别为1110/1107/1158/1134/1729；Top-N胜出尺度以31 px为主。
- Top-N位置已写入`outputs/case02/run_20260930_153727/samples/*/patches/top_patches.csv`，每条记录含中心坐标、峰值响应、胜出尺度和人工复核代理类别。
- 代理统计：boundary_like_proxy=0，local_response_proxy=100，manual_review_required=0。该代理规则不能替代人工确认；原始预览中可见强水平黑带，因此“强边界是否主导”仍为`PENDING USER`，不宣称当前基线检测效果良好。
- 内存估算：顺序释放策略下峰值约890.4 MiB，详见`memory_estimate.json`；若现场可用内存不足，后续再评估tile+halo，不在本阶段擅自改变算法。
- 验证：`pytest -q --basetemp .pytest_tmp_case02_verify`为`7 passed`；默认系统临时目录在本机权限不足，因此使用工程内临时目录完成复核；Case00回滚复核20/20通过；`main.py --case 1`拒绝执行旧配准入口。
- 本阶段到此停止，等待用户确认5张代表图、多尺度响应和Top-N patch后再进入后续阶段。

## Case00 实际执行记录（2026-09-30）

### 日期/时间

2026-09-30 10:27~10:29（Asia/Shanghai）。成功运行目录：
`outputs/case00/run_20260930_102836/`。

### 新建/修改文件

- 工程规范与说明：`AGENTS.md`、`README.md`、`PROJECT_IMPLEMENTATION.md`、`requirements.txt`。
- 用户配置：`config/user_config.py`、`config/__init__.py`。
- 主入口：`main.py`。
- RAW与显示输出：`src/io/raw_reader.py`、`src/io/image_writer.py`、`src/io/__init__.py`。
- 质量体检：`src/qc/image_statistics.py`、`src/qc/profile_analysis.py`、`src/qc/__init__.py`。
- 工具：`src/utils/paths.py`、`src/utils/logger.py`、`src/utils/__init__.py`。
- 测试：`tests/test_raw_reader.py`。
- 运行时创建：工程内独立虚拟环境 `.venv/`，没有修改系统 Python。

### 算法与实现

1. 通过文件名的前两个数字组解析样品编号和帧编号，确认样品26~30、每片1~4帧，共20帧。
2. 使用16 bit大端 dtype `>u2` 读取无文件头RAW，检查文件字节数，再 reshape 为 `9200×11276`。
3. 原始统计直接在 `uint16` DN数组上计算：min/max/mean/median/std、0.1%/1%/50%/99%/99.9%分位数、零值、4095饱和、>4095溢出。
4. 直方图按0~4095逐DN保存，溢出单列单独记录，不静默截断。
5. 8 bit预览只用于显示，使用线性映射并缩小到最大边长2048；原始DN统计和预览文件严格分离。
6. 行/列平均曲线从原始DN计算，分别保存CSV和PNG。

### 输入数据

`D:\疵病检测\疵病实测数据\260624批次表观（5片）` 下20个RAW文件；每个实际大小均为207478400 Byte。

### 输出结果与核心数值

- `input_manifest.csv`：20行，全部文件大小检查通过，解码形状均为 `11276×9200`。
- `frame_statistics.csv`：20行；所有帧 `overflow_gt_4095_count=0`，最小DN范围87~92，最大DN均为4095，均值范围约851.599~1054.925 DN。
- `histograms.csv`：每帧4096个有效DN箱及溢出记录。
- `previews/`：20张8 bit PNG；`profiles/`：20个行/列曲线CSV和20张PNG。
- `config_snapshot.json`、`acceptance.md`、`acceptance_summary.json`、`logs/case00.log` 均已保存。
- 工程单元测试：`pytest -q` 返回 `2 passed`，覆盖大端解码和错误文件大小检查。

### 运行问题与修改

第一次运行目录 `run_20260930_102758` 在第1帧读取成功后，因Windows/OpenCV直接写中文路径导致预览写出失败；未覆盖原始数据。随后将 `src/io/image_writer.py` 改为“OpenCV内存编码 + pathlib二进制写盘”，在新目录 `run_20260930_102836` 全量运行成功。

### 一级验收结果

`run_20260930_102836/acceptance.md` 中的可执行检查全部 PASS：20帧发现、文件尺寸、解码/reshape、有效12 bit范围、输出完整性和原始DN/8 bit隔离均通过。预览的空间结构人工视觉复核仍标记为 `PENDING USER`，因为它需要用户结合设备现场预期确认。

### 下一阶段计划

停止在Case00，等待用户验收。只有用户明确回复“通过/继续Case01”后，才实施同视场1/2和3/4的配准；本次没有执行Case01及以后任何算法。

### 尚未确认事项

- 用户是否确认大端解码和当前预览中的黑带/边界空间结构符合设备现场预期。
- 44所数据的尺寸、有效位深、像元尺寸和采集设置仍未确认。
- 厂家平面玻璃结果的红/绿标记含义、尺寸单位和判定规则仍未确认。

## Case01：同视场关系与平移配准

### 日期/时间

2026-09-30 11:06~11:41（Asia/Shanghai）。最终结果目录：
`outputs/case01/run_20260930_113443/`。

### 本阶段目标

处理每个样品的1↔2和3↔4两组同视场关系，验证平移配准是否能改善固定结构重合，并保存位移、相关性、差分和有效重叠区域。当前不引入旋转、缩放或非刚性变换。

### 新建/修改文件

- 新建：`src/registration/overlap_mask.py`、`src/registration/pair_registration.py`、`src/registration/__init__.py`。
- 新建：`src/visualization/overlay.py`、`src/visualization/__init__.py`、`tests/test_registration.py`。
- 修改：`main.py` 增加Case01入口、10组配对流程和验收生成；`config/user_config.py` 增加配准参数。
- 运行输出：`registration_summary.csv`、`pairs/*/pair_metadata.json`、`before_overlay.png`、`after_overlay.png`、`difference.png`、`overlap_mask.png`、`acceptance.md`。

### 算法与参数

1. 保留相位相关作为诊断项。由于图像存在重复横向黑带，首版相位响应受周期结构干扰，不能单独作为位移结果。
2. 主流程使用“行/列平均剖面粗位移候选 + 原始DN缩略图局部二维NCC搜索细化”的平移模型；保留多个候选，避免单个周期峰强行决定结果。
3. 所有位移只施加于配准输出图；原始RAW只读，后续定量仍必须回到原始DN。
4. `REGISTRATION_MAX_SIZE=2048`、`REGISTRATION_HIGHPASS_SIGMA_PX=15`、`REGISTRATION_MIN_NCC_AFTER=0.85`、`REGISTRATION_MIN_NCC_IMPROVEMENT=0.0005`、剖面候选数3、局部搜索半径4个缩略像素。
5. `REGISTRATION_MAX_ABS_SHIFT_PX=1000` 是可配置的工程守门值，不是物理结论；超过该值的配对标记为不适合重复性分析。

### 输入与输出

输入仍为260624批次20帧RAW，按1/2和3/4组成10组。最终运行10组均输出完整证据：

- `registration_summary.csv`：10行，记录phase/profile位移、原始像素/μm位移、NCC、RMSE、边缘双影代理、重叠率和状态。
- `pairs/`：10个配对目录，每个目录4张图和1个JSON元数据。
- 6组标记为 `usable_for_repeatability`：26(1/2)、26(3/4)、27(1/2)、28(1/2)、28(3/4)、29(1/2)。
- 4组标记为 `not_suitable_for_repeatability`：27(3/4)超过±1000 px守门值；29(3/4)和30(3/4)相关性不足；30(1/2)最终NCC低于0.85。它们不会被后续自动用于重复性分析。

### 一级验收

`outputs/case01/run_20260930_113443/acceptance.md` 和 `acceptance_summary.json`：10组输入均处理、位移和指标均有限、每组4类图像齐全、可用配对的NCC/RMSE改善通过、可用配对的边缘双影代理均未增加、不可靠配对未被强行使用；总体一级自验 PASS。

### 运行问题与修改过程

- `run_20260930_110616`：首组输出差分图时发现缩放参数错误，未完成；修复`overlay.py`后重跑。
- `run_20260930_110701`：首版相位相关受周期黑带干扰，只有1组可用；诊断确认剖面粗搜索后二维原始DN NCC可显著改善，因此改为剖面辅助二维NCC。
- `run_20260930_112703`：发现配置文件重复定义±500 px覆盖了新参数；清除重复定义并将守门值依据实际配准位移调整为±1000 px。
- 合成已知平移测试和原有RAW读取测试最终共 `3 passed`。

### 未确认事项与下一步

- 用户需要视觉确认10组配准前后叠加图和差分图，尤其确认大位移配对没有因横向黑带周期造成错峰。
- 当前只验证平移；若用户发现明显旋转/缩放，必须暂停，不得直接进入复杂变换。
- 等待用户明确回复“通过/继续Case02”后，才进入有效ROI与背景建模。

## Case00：工程初始化与 RAW 读取确认

### 阶段目标

建立可回溯的 Python 工程骨架，按已确认的 260624 参数读取 20 帧 RAW，输出每帧统计、直方图、行/列平均曲线和 8 bit 显示预览，并完成一级自验收。

### 实现方式

- 使用 `numpy.fromfile(..., dtype='>u2')` 按 16 bit 大端字序读取，转换为原生 `uint16` 后 reshape 为 `(9200, 11276)`。
- 有效 DN 检查范围为 0~4095；原始数组保留为 12 bit 物理量，不在读取模块中做 Gamma、CLAHE 或直方图均衡。
- 8 bit预览按 `DN / 4095 × 255` 线性映射，用于显示；预览统一缩小到配置的最大边长，不参与定量。
- 行/列平均曲线从原始 DN 数组计算，保存 CSV 和 PNG。
- 直方图保存 0~4095 每个 DN 的计数，并单独记录 4095 饱和计数和大于 4095 的溢出计数。
- 每次运行生成独立时间戳目录和 `config_snapshot.json`，不覆盖历史输出。

### 关键参数及来源

- `RAW_WIDTH=11276`、`RAW_HEIGHT=9200`、`RAW_DTYPE=uint16`、`RAW_ENDIAN=big`、`EFFECTIVE_BITS=12`：来自用户提供的实施提示词。
- `PIXEL_SIZE_UM=3.2`：来自用户提供的实施提示词，本阶段只记录，不进行物理尺寸计算。
- `EXPECTED_RAW_BYTES=207478400`：由 11276 × 9200 × 2 计算，与实际文件大小核对。

### 输入数据

`D:\疵病检测\疵病实测数据\260624批次表观（5片）`，样品 26~30，每片 1~4 帧，共 20 帧。

### 输出结果

运行结果写入 `outputs/case00/run_YYYYMMDD_HHMMSS/`。具体文件以运行目录中的 `input_manifest.csv`、`frame_statistics.csv`、`histograms.csv`、`previews/`、`profiles/`、`acceptance.md` 为准。

### 验收指标

1. 20 个输入文件全部发现且每个文件字节数等于 207478400。
2. 每个文件可按 11276 × 9200 reshape。
3. 解码统计记录有效 DN 范围、分位数、零值、4095 饱和与溢出情况。
4. 每帧存在直方图、行/列曲线和 8 bit 预览输出。
5. 原始 DN 与显示预览分开保存，预览不进入定量统计。
6. 工程入口、配置、日志和参数快照存在。

### 验收状态

本记录由运行生成的 `acceptance.md` 给出本次具体 Pass/Fail 证据。一级自验通过后，必须等待用户验收；不自动进入 Case01。

## 回滚旧Case01并实施Case02：单张图多尺度Black-Hat暗异常增强

### 日期/时间

2026-09-30（Asia/Shanghai）。

### 回滚记录

- 检查确认当前活动 `main.py` 已恢复为Case00基线；无可用Git仓库，因此不使用版本回滚。
- 活动工程中未保留旧 `src/registration/` 配准源码和配准入口；`main.py --case 1` 明确拒绝执行旧配准。
- 旧 `outputs/case01/` 保留为历史追溯目录，不作为Case02输入或依赖。
- `config/user_config.py`中移除旧配准专用参数；当前仅保留RAW、Case00及新Black-Hat配置。
- `src/visualization/`仅新增本阶段`defect_response.py`，不恢复旧配准overlay/difference模块。

### 阶段目标

对样品26~30的第1帧分别独立执行Black-Hat 3/5/9/15/31 px增强、逐尺度统计、max融合、胜出尺度图和Top-N patch提取。不使用第二帧、配准、帧间差分、多帧平均、8 bit定量、CLAHE/Gamma、Gabor/LoG/DoG/Frangi或最终阈值分类。

### 新增/修改文件

- 新增：`src/detection/blackhat.py`、`src/detection/multiscale.py`、`src/detection/__init__.py`。
- 新增：`src/visualization/defect_response.py`、`src/visualization/__init__.py`。
- 新增：`tests/test_blackhat.py`。
- 修改：`main.py`增加Case02入口与单图逐尺度流程；`config/user_config.py`集中增加Black-Hat和Top-N参数；`AGENTS.md`、`README.md`和本记录更新回滚/当前阶段说明。

### 算法与内存方案

- 结构元统一为椭圆，尺寸为3、5、9、15、31 px，分别约对应9.6、16、28.8、48、99.2 μm。
- 每个尺度使用原始`uint16` DN执行`Closing(I)-I`，用`cv2.subtract`避免uint16下溢；响应保存为压缩NPZ，PNG只用于人工显示。
- 融合为逐像素最大响应，并保存1-based胜出尺度图。
- 原始图、closing临时数组、单尺度响应、融合响应和uint8胜出图不同时保留五个尺度响应；每个尺度保存/统计后删除并触发垃圾回收。
- 工程估算主数组峰值约为 `4×11276×9200×2 + 11276×9200×1 ≈ 0.78 GiB`，未计OpenCV内部工作区；若实际内存不足，下一步再按最大半径实现tile+halo。

### 输入与输出

- 代表图：样品26、27、28、29、30的第1帧，统一参数。
- 运行目录：`outputs/case02/run_YYYYMMDD_HHMMSS/`。
- 每张图输出原始8 bit预览、5个尺度的NPZ/PNG、融合NPZ/PNG、胜出尺度NPZ/PNG、Top-N原始DN/响应DN patch及CSV。
- 全局输出：`blackhat_statistics.csv`、`memory_estimate.json`、`config_snapshot.json`、`acceptance.md`、`acceptance_summary.json`和日志。

### 测试与验收

- 新增暗点、暗线、常量图、uint16边界和max融合测试；与Case00读取测试合计应为7项pytest。
- Top-N中边界类/局部响应类使用代理规则统计，不能作为Ground Truth；强边界是否主导需用户视觉复核。
- 本阶段完成后必须停止，不进入Case03阈值分割；验收结论以本次运行目录的`acceptance.md`为准。

### 未解决问题

- 高分辨率全图形态学的实际峰值内存和耗时需要在首次运行中验证。
- 黑带、强边界和白色标记可能主导Top-N响应；不能在本阶段擅自删除或做背景校正。
- 需要用户确认5张代表图的多尺度响应和Top-N patch后，才能讨论下一阶段。

### 未确认事项

- 预览图的空间结构是否符合现场预期，需要用户结合原图进行视觉确认。
- 本阶段不对 44所数据、平面玻璃厂家结果做混合计算。
- 本阶段不判断具体是划痕、麻点还是其他缺陷类型。

## Case02检测效果验证与补充修订（2026-10-08）

### 修改文件与原因

- `scripts/validate_case02.py`：新增独立验证入口，读取既有Case02 NPZ/CSV，按单样品、逐尺度顺序完成数组核查、Top10跨尺度候选、融合Top20、联系图、局部图册、统计报告和人工审核表。
- `tests/test_case02_validation.py`：新增候选坐标边缘排除和16 px空间匹配回归测试。
- `config/user_config.py`：仅增加联系图最大边长、逐尺度TopN、匹配半径和图册列数等可选诊断参数；未修改Black-Hat默认尺寸、结构元形状或融合策略。
- `main.py`：修正文档字符串，明确验证逻辑在独立脚本中。
- `AGENTS.md`、`README.md`：同步当前为Case02效果验证阶段，并补充验证命令。
- `OPEN_SOURCE_REFERENCES.md`：记录开源项目追溯；未核实名称不编造URL或许可证，当前未直接复用外部源码。
- 复核修订：发现验证脚本初版把胜出尺度图的1~5索引误当作3/5/9/15/31 px统计，已修正为索引到实际px的映射并在`run_20261008_095027`重跑；同时配置SimHei用于中文图注，未改变数值处理。

### 执行命令与结果

- `\.venv\Scripts\python.exe -m compileall -q main.py scripts src tests`
- `\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest_tmp_case02_validation`：`10 passed`。
- `\.venv\Scripts\python.exe scripts\validate_case02.py`：读取`outputs/case02/run_20260930_153727/`，成功生成验证目录`outputs/case02_validation/run_20261008_095027/`。
- 验证结果：5个样品、30条尺度/融合统计、250条逐尺度Top10候选、100条融合Top20候选、100行空白人工审核模板、60张PNG图件。

### 主要诊断发现

- 融合Top20的31 px获胜比例：样品26/27/28/29/30均为20/20，即100%；这只说明当前max融合的Top20排序偏向31 px，不能解释为实际疵病尺寸。
- 全图胜出尺度分布并不等同于Top20：31 px在五张图中约占88.7%~89.5%，15 px约4.6%~5.1%，9 px约1.5%~1.7%，5 px约1.0%~1.1%，3 px约0.5%~0.5%；说明大尺度峰值排序与全图逐像素胜出分布不同，需人工结合图册判断。
- 16 px匹配半径下，3/5/9 px Top10与融合Top20匹配数分别为0/0/0、0/0/0、0/0/1、7/7/8/7/7、10/10/10/10/10（按样品26~30顺序）；不同尺度候选位置差异明显，不自动解释为漏检或真实缺陷转移。
- 基线原始预览和新联系图均显示重复水平黑带/强背景结构以及亮色方块/十字标记样结构；脚本将已知黑带/标记区域保持为`unknown`，没有自动剔除或把代理类别写成真值。

### 输出与回退

- 诊断报告：`outputs/case02_validation/run_20261008_095027/case02_validation_report.md`。
- 验收记录：`outputs/case02_validation/run_20261008_095027/acceptance.md`。
- 人工审核：`manual_review_template.csv`和`review_guide.md`；标签全部留空。
- 回退方法：删除/停用新增验证脚本、诊断参数、验证测试和验证输出目录即可；原`outputs/case02/run_20260930_153727/`、原始RAW和Case02核心代码未被覆盖。`OPEN_SOURCE_REFERENCES.md`为独立追溯文档，可单独移除，不影响主流程。

### 当前状态

本轮仅完成Case02验证与最小文档/诊断补充，未进入Case03、未调整阈值、未剔除黑带区域、未修改Black-Hat核心参数。真实疵病与背景干扰的区分仍为`PENDING USER`，等待人工审核后再接受下一阶段指令。

## Case03-A全图阈值分割与鲁棒阈值对照（2026-10-08）

### 阶段边界

本阶段严格限定为Case03-A，读取既有`outputs/case02/run_20260930_153727/`中的`uint16`响应NPZ，不重新计算Black-Hat，不修改Case02、RAW或Case02独立验证目录`outputs/case02_validation/run_20261008_095027/`。本阶段完成后停止，不进入Case03-B、Case04或Case05。

### 新增实现

- `src/detection/thresholding.py`：固定阈值`response_dn >= threshold_dn`、bool掩膜统计、packbits无损保存/还原。
- `src/detection/local_robust_threshold.py`：256 px网格、stride=4采样、Median/MAD、`max(120, median + k*1.4826*MAD)`、全边界网格统计、双线性插值和条带输出。
- `src/visualization/segmentation_diagnostic.py`：响应/固定阈值/局部阈值/叠加联系图和典型点patch。
- `scripts/run_case03a.py`：独立Case03-A入口、输入清单、全参数统计、主掩膜、资源估算、报告和验收输出。
- `tests/test_case03a.py`：固定阈值边界、MAD=0、网格边界、插值形状、packbits round-trip和阈值并集测试。
- `config/user_config.py`：集中记录Case03-A输入批次、样品、尺度、固定阈值、k值、floor、网格和诊断点参数。

### 固定参数与输出策略

- 样品26~30，第1帧，尺度3/5/9/15/31 px。
- 固定阈值统计150/200/250/300 DN，主固定阈值200 DN。
- 局部鲁棒统计k=3/5/7，主k=5，floor=120 DN，网格256 px，采样stride=4 px。
- 仅保存主固定200 DN和主局部k=5的全分辨率掩膜；掩膜以packbits压缩NPZ保存，并在保存后立即还原逐像素核对。
- 不执行连通域、轮廓、形态学、面积过滤、TopN截断、ML分类或黑名单剔除；不计算真实疵病Recall/F1。
- 诊断点包含提示词指定的样品26/30历史坐标，并补充低响应背景点和条带边界点；这些坐标仅用于可视化诊断，不作为人工真值。

### 运行与验收记录

- 小样本预运行：`outputs/case03a/smoke_20261008/`，样品26完成；35条阈值统计、8100个局部网格单元、10个主掩膜、5组典型点patch，packbits round-trip通过。
- 完整运行：`outputs/case03a/run_20261008_112000/`，处理5个样品×5个尺度；以该目录的`acceptance.md`、`acceptance_summary.json`和`case03a_report.md`为阶段证据。
- 编译与测试命令：`\.venv\Scripts\python.exe -m compileall -q main.py scripts src tests`；`\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest_tmp_case03a_clean`，结果为`16 passed`。
- 通过条件：固定/局部统计行数完整、主掩膜shape和bitorder可还原、边界网格存在、原始输入和Case02目录未写回、Case03-B未执行。真实缺陷效果仍标记为`PENDING USER`。

### 开源参考追溯

按本阶段提示词在`OPEN_SOURCE_REFERENCES.md`记录MicroDefectCV、opencv-defect-detection和casting-defect-opencv的准确链接。本工程未复制或导入这些项目源码，许可证未完成法律核验的条目保持“待核验”。

### 当前状态

Case03-A代码、真实数据运行、测试和阶段自验收完成后停止；等待用户查看最终运行目录中的联系图、阈值统计和典型点patch。不得自动进入Case03-B。

## Case03-A-R1补充修订：阈值与可视化（2026-10-08）

### 阶段边界与回滚

本轮严格限定为Case03-A-R1。既有Case03-A A0运行`outputs/case03a/run_20261008_112000/`、Case02响应`outputs/case02/run_20260930_153727/`、Case02验证和RAW均只读；所有新结果写入`outputs/case03a_revision/`。删除/停用R1新增代码、配置、测试和该输出目录即可回滚，不影响A0或更早阶段。本轮未进入Case03-B、Case04或Case05。

### 实现与参数

- `src/detection/local_robust_threshold.py`增加`min_excess_dn`、严格`>`和median/MAD分别插值连续场；默认参数仍保持A0旧版兼容。
- `src/visualization/segmentation_diagnostic.py`增加density块平均、any-hit提示、互斥类别守恒、密度叠加、R1联系图和A0/A1/A2原尺寸patch。
- `scripts/run_case03a_revision.py`新增A0只读基线、A1每尺度固定候选扫描、A2样品26中心2048区域27组筛查及3组代表参数五样品对照、区域/网格/交并统计、运行资源日志和保护目录SHA256/清单核对。
- `tests/test_case03a_revision.py`新增常量0/100/130/300 DN阴性、强单点阳性、点/线/缓坡/网格交界、不同固定阈值、density均值、any-hit放大和交并守恒测试。
- `config/user_config.py`集中记录A1候选、A2筛查/代表参数、分区和诊断窗口；没有把任何候选写成正式最优阈值。

### 完整真实数据运行

- 小样本：`outputs/case03a_revision/smoke_20261008_r1/`，样品26完成，保护核对通过，视觉抽查通过。
- 完整运行：`outputs/case03a_revision/run_20261008_141000/`，样品26~30、第1帧、5种尺度完成。
- 统计规模：A1阈值扫描175条，A2单样品筛查135条，A2五样品代表统计75条，区域密度900条，网格摘要100条、网格明细162000条，交并统计50条，代表掩膜100个，原尺寸patch33组。
- 技术自验：`acceptance_summary.json`为`overall_self_check=true`；保护目录`unchanged=true`；density缩略图均值最大绝对误差`7.51e-05`；交并类别精确守恒。
- 资源与命令：`runtime_statistics.csv`记录25个样品/尺度运行单元、耗时和内存快照；实际命令写入日志和`acceptance_summary.json`。
- 测试：AST语法检查通过；`\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\Users\lixia\Documents\Codex\2026-09-30\d\.pytest_tmp_case03a_r1_final`为`21 passed`。

### 诊断结论边界

- 样品26旧A0的3px局部候选和31px固定候选已按上/中/下区域给出改前/改后真实像素比例、density图和256px原尺寸patch；所有诊断区域标记`candidate_not_truth`。
- 3px局部A0及部分A2方案的`floor_dominated_grid_fraction`超过99%，报告醒目标记为接近绝对下限的退化情形；不得据此宣称局部自适应已经解决。
- A1/A2均为候选敏感性实验，未自动选择正式阈值；真实疵病效果、Recall/F1和视觉验收仍为`PENDING USER`。

### 当前状态

Case03-A-R1代码、合成测试、样品26试运行、5样品真实运行和一级技术自验收完成；现在停止，等待用户验收，不进入Case03-B。
## Case03-B completion record (2026-10-08)

Case03-B was implemented and self-accepted in `outputs/case03b/run_20261008_152500/`.
The implementation reads Case02 `fused_response_dn` read-only for samples 26-30, frame 1.
S uses `R >= TH` for TH 220/230/250 DN. H uses 8-connected support/seed hysteresis for
(TL,TH)=(150,230) and (170,230) DN. No morphology, area filtering, or Top-N deletion is used.
The scalable component implementation is `src/detection/tiled_components.py`; local synthetic
and sample26 patch validation passed before the full run. The full run produced 2,254,801
candidate rows, lossless packed masks, low-only H masks, and the sample26 fused-vs-31px
comparison. Regression tests: 25 passed. Case02, RAW, Case03-A and Case03-A-R1 protected
snapshots are unchanged. Case04 and Case05 were not executed; stop at Case03-B.


## Case03-B局部人工复核图册补充（样品26）

- 原始Case03-B全图运行：`outputs/case03b/run_20261008_153500/`；本次任务由用户明确要求完善样品26的固定阈值与双阈值局部对照，保留历史文件。
- 新代码：`scripts/build_case03b_sample26_gallery.py`；参数：`config/user_config.py`追加`CASE03B_GALLERY_*`，13处指定ROI坐标、类别及256/512px窗口。
- 使用只读RAW（big-endian uint16有效12bit）、Case02 `fused_response_dn`和Case03-B三个无损packbits全图掩膜；逐像素截取，不重新做窗口内H生长，避免窗口外种子导致的错漏。
- 3组方法：S230、H170/230、H150/230。显示内容：RAW、Black-Hat、三掩膜及差异三色叠加；黄为S230、青为H170新增、洋红为H150再新增。不在ROI图上堆叠全量编号。
- 输出：`outputs/case03b_gallery/run_20261008_sample26_review/`；3张汇总图、13张六面板、13个原始RAW/响应DN/掩膜无损NPZ、`roi_statistics.csv`、`gallery_report.md`、`acceptance.md`。
- 特征示例：三暗斑位置（9437,1075）256px：S230=1289、H170/230=2015、H150/230=3649候选像素。低阈值扩大异常轮廓的同时也增加背景点，不能直接判断H150优于H170。
- 注意：十字/短线、条带边缘结构只是候选或系统标记，未证实为细划痕；`middle_low_response`窗口三种方法都为0，不代表其他区域没有异常。
- 新测试：`tests/test_case03b_gallery.py`；需要验证整体pytest，输出原数据/旧掩膜保护仅表示所检查文件大小及mtime保持一致；真实疵病人工审核仍待完成。
- 不引入局部MAD、不修改Case03-B既有分割、不进入Case04/Case05。

- 本阶段最终复测：`python -m pytest -q --basetemp .pytest_tmp_case03b_gallery_final`，**30 passed in 1.16s**。典型暗点和条带候选图册已可用，图册人工真实性审核仍待用户完成。
## Case03-C phase 1 implementation record (2026-10-08)

Implemented the first phase of candidate association and human-review preparation.
The implementation is split across `src/detection/candidate_association.py`,
`src/detection/candidate_shape_features.py`, `src/detection/candidate_raw_features.py`,
`src/visualization/candidate_feature_atlas.py`, and `scripts/run_case03c.py`, with
configuration in `config/user_config.py` and the `main.py --case 3c` entry point.

Execution order was enforced: synthetic Gate A, historical 13-ROI Gate B, then
sample-26 full-image processing. Formal output is
`outputs/case03c/run_20261008_174000/`. It records exact S230/H170-230 association,
complete candidate features, RAW ring descriptors and validity flags, 60 blank
manual-review entries with atlas figures/patches, resource usage, report, and
acceptance evidence. Verified totals: S 91,937 / 121,467 pixels; H 88,043 /
311,790 pixels; 2,110 multi-core H candidates; 66,399 valid RAW references.

The final self-check is PASS and the full regression suite is 34 passed. The
implementation does not use local-MAD thresholding, delete candidates, or assign
automatic truth labels. Existing data and historical outputs are protected. This
phase ends at human review; no later Case03, Case04, or Case05 phase was entered.

 
## Case03-C-R1修订记录（2026-10-09）

用户明确要求优先解决：①RAW参考环带显示范围错误；②缺少人工标签导致特征判别力未经验证。实现`src/detection/reference_ring_geometry.py`作为环带/抽样像素单一来源；将RAW参考数值函数复用该来源，保持原环带半径12px、最多512像素的采样行为。新增`scripts/revise_case03c_evidence.py`、`scripts/regenerate_case03c_revision_figures.py`、`src/detection/feature_discrimination.py`、`tests/test_case03c_revision.py`。单独输出`outputs/case03c_revision/run_20261009_reference_feature_review/`，保留旧运行及全部候选、全部原始分割数据。

实际结果：重新渲染60张参考图，已复核图一号环带候选1782像素、真正抽样512像素；图七环带候选1224像素、抽样512像素。所有复核ROI的环带数量/采样数量、有效RAW中位数及MAD与既有Case03-C CSV一致；标注后特征判别力评价脚本已建立，但目前没有人工确认标签，**真实疵病与背景噪声的可分性仍是PENDING_LABELS**。任一类别人工独立候选不足5或缺少有效特征时不计算AUROC，不以形态或RAW灰差直接判定真疵病。前期60个图册条目含58个独立候选，其余重复或背景ROI不作独立真值。当前不执行27~30样品及后续阶段。

 
## Case03-C：人工复核9个候选位置修订（2026-10-09下午）

用户明确复核：review_018/019/021/027为青色扩展区域存在视觉异常，review_024为黄色与青色均存在，review_039为黄色区域存在；其对应的原红色选中候选不应直接继承这些阳性标签。review_031为左下角、review_046为右下角、review_056为左侧**原RAW肉眼可见但S230/H170未形成完整对应候选**的暗区。原Excel人工记录保持不变。

只读核对Case03-C局部无损NPZ并新建 `outputs/case03c_label_analysis/run_20261009_user_clarification_v2/`：
- `review_60_user_clarifications.csv` 60条记录及9条用户确认的ROI级标注；
- `visible_undersegmented_3_regions.csv` 根据用户圈图估算的3处原RAW坐标/局部掩膜响应（坐标仅粗略，非精确像素真值）；
- `reconciliation_summary.json` 与 `user_clarification_report.md`。

本次不随机把黄色/青色像素指派给现有红色`candidate_id`；准确组件编号仍需像素点选/框选。当前可用于明确红色候选级探索性AUC的标签仍为10正39负，等同上一轮敏感性分析保守组；不宣称AUC提升。三处未完整检出的暗斑需纳入ROI漏检/欠分割验证，不能算成`background_artifact`或继续调阈值后无记录丢失。现阶段不修改Case02、S230、H170/230、Case03-C数值特征，也不启用局部MAD。

 
## 样品26九处真实目标人工点选复核工具（2026-10-09）

经用户确认，原`manual_review_template.xlsx`中9处标签对应关系需修正（6处黄色/青色目标为异常，3处RAW可见但分割未完整识别）。新增`scripts/build_case03c_manual_retarget_ui.py`，生成静态离线网页`outputs/case03c_manual_retarget/run_20261009_9roi_target_review_v2/index.html`，所有输出与原图/历史掩膜分离。原始RAW坐标可以在网页点击/拖框后导出`case03c_sample26_user_retarget.csv`；**不以旧红色选中ID默认代表人工阳性**，需用户导出后再运行精确全图组件关联。支持多个目标、JSON备份、阈值命中状态提示。9ROI→27张PNG及嵌入掩膜，经Node JS语法和Chrome离线打开检查、无损像素比对及全工程回归（44 passed in 4.38s）。页面接受用户人工确认，不会自动删除微小候选、修改旧阈值或训练模型。仍不使用局部MAD，也不进行27～30样品检测。


## Case03-C人工点选CSV精确关联与弱暗斑诊断（2026-10-09）

用户提供C:\Users\lixia\Downloads\case03c_sample26_user_retarget.csv，共12条标注、8张review（review_056缺失）。基于Case03-B无损全图掩膜，新增scripts/resolve_case03c_user_retarget.py实现点击点的8连通真组件匹配，按完整bbox+area与Case03-C现有特征CSV唯一对应；新增scripts/analyze_case03c_retarget_local.py用于原RAW+BlackHat+阈值的真实DN局部诊断；新增tests/test_case03c_exact_retarget.py检查映射、无mask点不猜ID、标签去重和欠分割框验证。本轮完整pytest 50 passed in 3.04s。

结果保存在outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v1；5个命中点、4个不同H候选（review_021、024、027、039，其中039黄色与青色点同属同一个H组件），6个未命中点不能强行记成阳性ID，31号30x20框内S230=0、H170=0、BlackHat峰216DN、35px超过170DN但0px超过230DN，形成一个明确的强种子不足/未完整检出例。46号点靠近旧ROI边缘、未画完整框；56号未导出。合并原可信10正39负和本次4个确切正候选后有14正39负，面积/峰值的AUC仅为当前人工选取样本的探索性排序，不可外推全图识别率；且已检出样本AUC不涵盖31等未检出暗斑。全部旧运行源、原始标注未覆盖，阈值230/170及局部MAD设置不修改；下一步针对18/19/24未命中点核对真实目标、46/56补充完整ROI再考虑算法诊断。详细报告：outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v1/retarget_analysis_report.md。


## Case03-C第二版人工复核（2026-10-09）

用户输入C:\Users\lixia\Downloads\case03c_sample26_user_retarget (1).csv（Windows括号前含空格），20条人工标记，13点7框；用户明确更正review_056无问题，退出未检出疑点列表但不当成候选级背景负类。第二版精确分析新目录outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v2，历史v1及原始CSV/Excel/RAW/Case02/03B/03C保留。

利用全分辨率掩膜，18/19暗斑框内分别有151/98个H像素，其中主H候选占97.35%/96.94%；24三个框各对应主导H候选，两个此前只在框选中出现（第三个已点击直接精确命中）。对于由大多数像素关联的四个新H组件只标记“暂定”，不冒充完整人工像素级标签；严格保守14正39负，敏感性扩展18正39负。31框30×20px中H/S均0，Bhat峰216DN，46框24×17px同样H/S为0，Bhat峰194DN，属于值得研究的弱暗区强种子不足案例。新生成7框明细CSV及对照图、标注敏感性AUC、完整工程报告和变更记录；全项目pytest 55 passed in 3.06s。未调整230/170DN阈值，不启用局部MAD、不删候选、不进入Case04/05。下一步优先031和046局部宽缓暗区增强/分割诊断。

 
## Case03-D补充：单像素防盲区与数据质量核查（2026-10-09）

- 88,043个H170/230候选主排序完整输出，A=881，B=7,924，C=79,238，score仅由全图面积与峰值DN各50%的经验百分位得到，**人工标签只在排序后用于探索性统计**。
- 已标注14正39负中12正落在A，1正B，1正C；C中的正候选为原review_045，H_sample26_0379819，面积3px、峰值232DN、排名54,778，人工标签confirmed_dark_spot但备注空白，须核对。A中的已标注负候选为原review_029，H_sample26_0380656，面积25px、峰值271DN、排名321。
- 实际RAW图册A榜前12位中既有明显暗点也有强亮暗过渡/条带边缘响应（例如未标注H_sample26_0428940、H_sample26_0425919）。A组881个里304个（34.5%）被背景过渡代理标记，提醒不能将A视为真实疵病高概率组。
- 全图35,678个面积为1px的H候选**全部落在C组**，可见面积参与主排序会将真正微小异常也一起后置；新增scripts/build_case03d_micro_safety.py作为独立人工抽查队列：micro_single_pixel_full_audit.csv留存35,678条，micro_single_pixel_top100.csv另选最强峰值前100条，figures/atlas_single_pixel_high_peak_audit.png显示RAW/S/H局部。**不自动把小点认定为缺陷，不改变主评分、优先级和任何源掩膜。**
- src/detection/candidate_priority.py为无监督可解释排序函数；scripts/run_case03d.py为工程运行入口，scripts/build_case03d_gallery.py生成RAW图册及全图质心分布示意，tests/test_case03d.py覆盖人工标签不参与得分、跨输入行排序稳定、全量保留1px、名单去重、微点完整归档等检查。
- 本次结果目录：outputs/case03d/run_20261009_190000。case03d_qc_findings.md与manual_recheck_queue.csv提供人工复核与风险列表；Case03-D的独立外部样品检出性能仍PENDING USER。
- 原始RAW、Case02、Case03-B、Case03-C及用户标注文件不做任何覆盖，仍暂停局部MAD与Case04/05；31、46、56按用户当前要求为本阶段非目标区域，**不转成候选级负真值**。


## review_045最新人工更正

用户已重新查看`figures/atlas_known_positive_low_priority.png`，确认`review_045`（`H_sample26_0379819`，排序第54,778名，3px）为背景伪影；此前A榜第2名`H_sample26_0428940`和第5名`H_sample26_0425919`亦被用户确认背景伪影。三条人工复核追加至`case03d_incremental_human_reviews.csv`，原始人工Excel、全量Case03-D排序、旧14正39负报告保留作为历史版本。新增更正结果独立保存在`manual_label_revision_after_review045`，保守组为13正42负，暂定框组为17正42负，排序参数未改。旧报告的14正39负不能当成最新样本计数。


## Case03-D-R2：自动疵病候选判别原型（2026-10-09）

根据用户最新目标（自动识别疑似疵病并尽量排除噪声、输出位置/轮廓/数量、仅让人工复核不确定区域），在保持原Case02/03B/03C以及Case03-D评分排序不变的前提下，新建src/detection/candidate_autodecision.py及scripts/run_case03d_autodetect.py等，实现按面积/峰值/点线形态/可靠RAW差异/黑带边缘特征的三分组初版规则。

完整执行命令：python main.py --case 3d-auto --run-id run_20261009_autodetect_final。结果：自动疑似疵病139个（133点状、6线状）、不确定候选6685个、噪声倾向但保留81219个，合计88043个H候选；311790个H候选像素原位保留且全图分类图逐像素守恒。6824个自动疑似与不确定组件导出bitpacked精确二值掩膜与真实连通域边界；未删除任何单像素候选。开发样本人工标签已修正为13正42负，其中10正自动检出、3正不确定，42负中0个自动检出，但此非盲法独立数据，不能当真实召回率/误报率。31、46、56按用户决定本阶段不追求其检出，也不作候选级负样本。全项目pytest 81 passed in 11.36s。

新建离线review页面：outputs/case03d_autodetect/run_20261009_autodetect_final/uncertain_manual_review_batch01/index.html，从6685个不确定候选中分层各20例共100例，用户可直接人工标注暗点、细划痕、背景伪影、不确定并导出CSV和JSON备份；网页Chrome离线渲染通过、JS语法检查通过。此抽样只用于有针对性的算法改进，不能当无偏测试集。

推荐用户先看figures/auto_detected_only_full_view.png（139个自动候选全图轮廓显示）、figures/atlas_detected_top12.png（RAW与精确绿色连通域）、figures/atlas_band_edge_artifacts.png（第2、第5背景伪影）、case03d_autodetect_report.md。模型尚未在独立新样品验证，面积/峰值与背景参考并不保证微小弱疵病不进入噪声倾向组，因此阶段状态为工程原型而不是已达成工业验收。

实施代码不修改旧运行目录：输出在outputs/case03d_autodetect/run_20261009_autodetect_final；src/detection/candidate_autodecision.py（规则）、candidate_contour_export.py（精确轮廓）、scripts/run_case03d_autodetect.py（管线）、scripts/render_case03d_autodetect_fullview.py（全图PNG）、scripts/build_case03d_uncertain_review_ui.py（100例离线标注界面）、tests/test_case03d_autodetect.py（回归）。后续务必基于新样品盲法标注验证真实疵病位置、轮廓、误检率和漏检率后才可声明自动检出效果。


# Case03-D：Top12自动检测图册改为方案A（四列，2026-10-09）

用户要求避免旧 atlas_detected_top12.png 仅标选中绿色连通域、使旁边已检出暗斑看起来像漏检的误解。本次已直接修改原工程而非仅提交提示词。

## 生成文件及备份
- figures/atlas_detected_top12.png：原地更换为4列，每张160×160原RAW区域，完整图像2025×1099 px。
- figures/atlas_detected_top12_legacy_selected_only.png：修改前完整旧版备份。
- atlas_detected_top12_roi_numbers.csv：每个局部ROI数字1/2/3对应真实H候选ID及可见面积、中心位置。
- atlas_detected_top12_four_view_validation.json：独立审计12卡、局部全候选数及示例第三卡验证。

## 方案A图例
1 RAW：真实原始RAW局部图。
2 ALL S/H：黄色S230强响应、青色H170扩展响应。
3 ALL AUTO IN ROI：此局部全部自动疑似疵病H连通域绿色填充，每个实际可见候选逐个编号；当前选中候选红框+红底数字，其他候选暗框/灰底数字。
4 SELECTED ONLY：当前选中H候选单独绿色填充并用红框标记。

第三列的绿色区域严格取自全图无损类别图中的自动疑似疵病H像素（class=3），并逐个从原始H掩膜恢复8连通组件；对全部局部绿色像素与编号候选像素并集做像素级等价验收，绝不按bbox重合就误标未出现的候选。

## 示例验证
第一行第三张卡片以 H_sample26_0406312 为当前选中候选；第三列实际上有3个不同自动检出H组件：
- H_sample26_0405250：窗口左边缘可见部分，局部编号1
- H_sample26_0406312：RAW上方暗点，当前编号2
- H_sample26_0408029：RAW下方暗点，局部编号3

旧第四列式单候选展示只突出上方暗点，容易误会下方漏检。新第三列完整显示三个自动检出候选，第四列仍仅突出当前选中组件。

## 工程代码修改
- 新增 src/visualization/case03d_detected_atlas.py：纯可视化渲染，四图与局部精确编号逻辑。
- 新增 scripts/regenerate_case03d_detected_atlas_four_view.py：复用已有自动分类与原H掩膜，安全地只重绘Top12图册；旧PNG必须已备份。
- 修改 scripts/run_case03d_autodetect.py 中 draw_atlas：仅detected_top12默认改为4图，以后新运行同样采用方案A；其他图册及100例离线人工页面不受影响。
- 新增 tests/test_case03d_detected_atlas_four_panel.py：合成多个相邻/裁切候选、仅选中一个候选、局部像素守恒、真实第三卡3组件、旧图完整备份以及今后生产入口检查。
- 全工程回归：87 passed in 9.37s。

此次修改仅更新图册，不更改139自动疑似、6685不确定、81219噪声倾向的分类结果，也不修改原始RAW、S/H分割、Case02、Case03B、Case03C或任何人工标签。绿色仅表示算法暂定疑似疵病，不代表确认滤光片表面物理缺陷，真实尺寸从原始轮廓JSONL及NPZ恢复。


# Case03-D Top12自动检出图册由四列简化为三列（2026-10-09）

## 用户反馈与处理

用户确认第三列ALL AUTO in ROI已经完整绘出局部ROI内所有自动疑似疵病候选，因此第四列SELECTED ONLY重复且容易浪费空间；要求保留前三列。已直接在远程工程实施，不再只提交提示词。

- **已原地更新**：figures/atlas_detected_top12.png，三列布局，1524×1099像素。
- 三列依次为：1 RAW原始灰度、2 ALL S/H（黄色S230强响应、青色H170补充）、3 ALL AUTO in ROI（局部所有自动疑似疵病候选的真实H区域绿色填充、逐个编号，红色框及红底编号突出当前候选）。
- 图中所有绿色为自动算法提出的provisional候选，不等同于物理滤光片疵病真值。
- 第三列所有候选严格沿用全分辨率自动分类图中的class=3以及Case03-B源H掩膜，按照真实8连通成分逐像素核对，不依赖bbox交集猜测。ROI编号与真实candidate_id映射在atlas_detected_top12_roi_numbers.csv。
- 第一行第三张卡片仍显示编号1=H_sample26_0405250（左缘部分可见）、2=H_sample26_0406312（当前上方暗点）、3=H_sample26_0408029（下方暗点）。下方暗点没有漏检。
- **备份保留**：原三小图“只显示选中连通域”版为figures/atlas_detected_top12_legacy_selected_only.png；上一版四列为figures/atlas_detected_top12_four_panel_backup.png。
- src/visualization/case03d_detected_atlas.py新增three_view_tile/atlas_three_view；scripts/run_case03d_autodetect.py默认生成新三列版；scripts/regenerate_case03d_detected_atlas_three_view.py可复用已有139候选及源掩膜只重绘图册。
- 审计：atlas_detected_top12_three_panel_validation.json；继续保存前一版的four_view_validation.json，作为历史记录，不表示当前图仍是四列。
- **全工程回归测试90项全部通过（6.93秒）**，已实际打开新PNG检查12个图册卡片与第一行第三列3个独立候选。
- 不修改RAW、Case02/03-B阈值、Case03-C特征、88,043个H组件、139自动疑似/6685不确定/81219噪声倾向的判别结果、历史人工标签；仅更换Top12图册展示。


## 2026-10-10：Case03-D 100例人工标注审计

读取用户Downloads目录的case03d_uncertain_review_backup.json与case03d_uncertain_review_batch01.csv，100条全部一致，80负16暗点3细线1不确定。10条备注指出RAW局部存在非当前绿色选中H连通域的疑似真实目标，5条正候选存在目标对应不一致风险，5条负候选ROI存在其它异常。见outputs/case03d_manual_review_analysis/run_20261010_092200/audit_report.md与note_neighbors_report.md，原始人工记录没有覆盖，尚不据此重新训练Case03-D分类器。


## 2026-10-10：Case03-D目标简化为疵病位置、精确轮廓和大小分级

用户决定暂不区分麻点、划痕等类型，不做多类别机器学习分类器。新建10处RAW点击标注页面，修正人工备注中目标位置与旧H候选ID不一致的问题；允许一张ROI多目标点选/框选/多边形并离线导出CSV和JSON。详细方案见outputs/case03d_manual_review_analysis/run_20261010_092200/CASE03D_LOCATION_SIZE_FIRST_PLAN.md。保留旧Case03-D全部判别及人工标注，无任何阈值更改。


## 2026-10-10 Case03-D人工真实RAW目标位置精确对应审计

- 用户位于C:\Users\lixia\Downloads的case03d_true_target_10roi_backup.json与case03d_true_target_10roi_locations.csv现已成功读取、几何逐项一致，共10个RAW ROI、11个用户中心点及11个手绘多边形（22条是配对标注，不能双重计数）。
- 11点的当前原H像素状态：自动疑似3，不确定5，H外3。11多边形均与H像素相交，按最大重合的原8连通H候选状态：自动疑似3，不确定8；强调H覆盖≠物理区域召回率。
- 已建立真实原H候选连通域掩膜与人工RAW区域的逐像素映射，不再使用原复核candidate_id代替真实目标ID。结果位于outputs/case03d_true_target_analysis/run_20261010_manual_10roi_matching，含22_annotations_exact_H_crosscheck.csv、11_clicked_points_class_status.csv、11_polygon_vs_actual_H_components.csv、11_manual_target_size_and_status_preliminary.csv、10roi_manual_polygons_vs_H_segmentation.png及完整诊断报告。
- H_sample26_0452065中用户新备注“无异常”与点/多边形同时存在，必须待确认并暂不作正样本。
- 人工多边形尺寸初评仅使用px、px²；3.2μm为探测器像元，不代表已知物面标定比例。4个ROI近边缘、可能因160px裁剪而影响尺寸判断。未设企业缺陷等级门限或分类器训练。
- 源RAW、Case03-B、Case03-D自动分类与人工导出保留，SHA256源文件保护记录一致；相关7项新增测试通过，全工程102项回归测试通过（7.81秒）。


# Case03-E阶段变更与验收记录（2026-10-10）

## 实际完成

用户要求继续下一阶段，重点解决已经定位的10处疑似异常的**局部RAW轮廓完整性、背景粘连风险与像素级尺寸初测**，暂不制作类型分类器、不上报未经标定的物面微米尺度。

1. 新增`src/detection/local_boundary_refinement.py`：从人工点击的RAW真实像素中心，在256×256 RAW邻域计算基于形态闭运算61/101px或高斯背景σ22的局部暗残差；通过背景环统计和种子强度设置宽松/保守阈值，进行8连通区域提取；输出精确局部像素掩膜、bbox、等效直径及最大凸包跨度，检测区域触边/面积过度扩展。
2. 新增`scripts/run_case03e_local_boundary_pilot.py`：10个用户保留区域×3种背景模型×2组预设阈值，60组实际运行，保存`masks/`60个无损掩膜、`figures/`10个8图对照、全部参数CSV、方法汇总及SHA256输入来源。
3. 新增`scripts/summarize_case03e_pilot_quality.py`：输出`per_target_engineering_QA.csv`及10目标总对照`figures/CASE03E_all_10_boundary_comparison.png`；采用不使用手绘多边形的固定验收风险条件：碰到256px边界或6组预测面积差比≥3。
4. 新增`tests/test_case03e_local_boundary_pilot.py`和`tests/test_case03e_pilot_quality.py`；包括synthetic RAW暗圆斑、真实坐标裁剪、源掩膜精度、无缺陷常量图、注释轮廓不参与算法输入、60组记录完备和质量风险。
5. `config/user_config.py`新增Case03-E集中参数：256px ROI、3方法、2阈值、最大单候选25%局部面积警戒、物面尺度/尺寸分级门限仍为None。 `main.py`支持`--case 3e`，现有Case02/03-B/03-C/03-D运算不改。

## 真正的阶段验收结果

- 10处人为选择并点击的目标完成60组实验。**这不是全图自主检测**；用户点击中心仍是分割种子。
- 3种方法×2阈值与手绘近似范围的平均IoU为0.537～0.578。高斯σ22+宽松阈值这组0.578仅是同样品开发观察分数，不是独立真实精度。
- **2处局部边界连接过度**（RAW26_MANUAL_003、010）：256px裁剪ROI内连到了其它大暗背景/大暗斑，面积可能严重高估；禁止直接作为最终测量轮廓。
- **2处参数明显不稳定**（RAW26_MANUAL_004、006）：6组面积变动约4.99倍、3.55倍，必须复核，不可直接赋予大小等级。
- **6处没有触边且不同方法面积相对稳定**：仍为`NEEDS_INDEPENDENT_CONTOUR_REVIEW`，只能进入下一阶段复核，不是已经完成轮廓真值确认。
- 本轮未修改原用户22条标注和已确认无异常区域，后者从10处试验中排除；未覆盖Case03-D的139/6685/81219判别结果和历史H170/230原始掩膜。
- **全工程119项pytest测试通过（51.35秒）**。工程模块/输出状态PASS，但生产级自动分割、独立轮廓准确率/全图漏检、物面标定和颜色尺寸等级尚未验收。

## 重点打开

- `figures/CASE03E_all_10_boundary_comparison.png`：10个ROI的RAW+黄色人工轮廓、旧H170/230分割、两种局部精修方案横向对照。
- `figures/RAW26_MANUAL_003_local_8panel.png`、`RAW26_MANUAL_010_local_8panel.png`：特别明显的背景粘连示例。
- `per_target_engineering_QA.csv`：10处风险列表；`all_60_pilot_experiments.csv`：60组技术参数和评价；`masks/`：60组真正可追溯的局部二值输出。
- `CASE03E_PILOT_REPORT.md`：详尽技术报告。

## 研究下一步

保持“不分类疵病类型”的方向，单独解决**长暗线与大暗背景的连接拓扑/线宽约束**，在扩大的RAW ROI下比较是否可切断背景但保留目标完整长度；同时为孤立点状异常验证轮廓边缘精修质量。通过人工独立检查和跨样品验证后再扩展到全图自动候选、输出尺寸分级颜色和数量统计。不能用本轮10处手绘参考直接证明系统真实检测能力。


# Case03-E2工程变更记录（2026-10-10）

- 需求：用户确认保留双阈值H170/230，Gaussian和形态学独立补充微小/主体暗响应，同一RAW窗口内自动发现所有独立目标，分别精修并去重输出；不做疵病类型分类器。
- 新增src/detection/case03e2_multicandidate.py：不接受点击/人工多边形参数，Gaussian22+Closing61各自本底MAD高低阈值、多marker watershed，保留H170/230历史候选，关联/桥接保护与质量状态。H-only弱微区域为待复核而非宣称已检出真实疵病。
- 新增src/detection/case03e2_window_stitch.py：原RAW全局bbox二值mask无损bitpack保存与恢复，跨窗口必须有真实像素交集才能去重，避免同一异常多次计数或邻近暗点误合并。
- 新增scripts/run_case03e2_multicandidate_fusion.py：10个人工参考坐标仅用于选择固定RAW网格评估窗口，不作为种子或融合参数；9个唯一窗口输出全部源候选审计、精确掩膜、全部融合候选JSONL、全局bbox表、候选图册及后验与人工近似轮廓比较。
- 新增scripts/accept_case03e2_multicandidate.py：14项目自验，包含源数据保护、人工种子与算法隔离、双暗点独立发现、H-only可追溯、输出精确像素及无重复、背景粘连、欠分割、跨窗和独立验证。运行脚本自动调用验收、生成PASS/FAIL/DEFERRED，不能强制全部PASS。
- 新增scripts/render_case03e2_review_contact.py：9个窗口完整总图；新加tests/test_case03e2_multicandidate.py，含14个独立合成/真实审计测试。
- 修改main.py支持python main.py --case 3e2 --run-id <run>，config/user_config.py集中设置Case03E2工程阈值与窗口规格，所有运行配置存config_snapshot.json。
- 最终目录outputs/case03e2/run_20261010_multiseed_fusion_v5。源历史Case02/03B/03C/03D/03E不覆盖、所有人工数据不改。全工程133项pytest测试通过（7.98s）；Case03E2验收14项：8 PASS / 2 FAIL / 4 DEFERRED。595?不采信旧草稿候选统计，本次最终机器候选数**591**、583个需复核、1569个H源候选追溯，979个H小分量只在H源层保留。MANUAL007/008同窗分别检出；MANUAL004、009可靠轮廓改进未通过；003/010背景粘连需复核。


# 2026-10-10 Case03-E2-H变更（用户复核图册后方向修正）

- 用户确认“Gaussian和形态学独立寻找新异常”产生大黑带伪影（E2_W001旧版Gaussian独立171? 待核，本次审计证实有**17051px**独立无H候选）、多细碎点；改为**H170/230唯一候选源**。
- 新增src/detection/case03e2_hseeded.py：全部原H连通域作为源、局部Gaussian/Closing仅在其已有H种子附近扩展<=12px，不再独立产生候选；识别局部低响应连接黑带、边界触及、跨H组件桥接、扩张面积失控则回退原H核心和记风险。所有H连通域（含1-2px）完整保留无损输出。
- 修改scripts/run_case03e2_multicandidate_fusion.py通过`hseeded=True`调用新算法、保持旧算法可复现；第五列图册只默认隐藏弱1-2px的audit_only_H_micro像素以减少视觉噪声，源审计和精确掩膜不删除。
- main.py默认`--case 3e2`运行H种子受约束方案，原`--case 3e2-legacy`仍可运行旧独立Gaussian/Closing候选；config/user_config.py新增H种子最大扩展半径等参数。
- 新增scripts/accept_case03e2_hseeded.py每次运行自动产生14项验收，新增tests/test_case03e2_hseeded.py 15项合成与实测不变性测试。
- 最终运行目录`outputs/case03e2/run_20261010_H_only_seeded_refinement_v2`；旧独立多源v5完全保留并可对照。实测**1569个原H候选全部准确保留**，其中957个低优先微点在结果第五列默认隐藏、83个暂定多源融合、529个需复核；旧版独立Gaussian/Closing异常对象16个 → 本版0个。007、008独立分割；001可补边。004与009安全轮廓仍未达标，003/010风险不作为安全面积。
- 自动验收14项**9 PASS / 2 FAIL / 3 DEFERRED**，全工程**150项pytest PASS**。仅样品26第1帧9个局部RAW窗口，不是整图全自动真实数量；数据均以像素面积输出，物面大小分级待标定/用户门限。


## 2026-10-10 Case03-E2-H5 W005十字暗线轮廓救援

- 问题：W005横向H源Hlocal_0050面积1936px²，Gaussian/Closing完整低阈值连通域9579/12809px²连接到256px裁剪边界，之前整块拒绝，导致横向划痕无法精修。
- 解决：新增case03e2_bounded_rescue.py，7px H源邻域内基于RAW真实DN局部响应进行阈值生长，候选不允许脱离原H、跨其他H种子、过大或触边；发生全局背景连接时有界救援，两种方法共识交集代替并集；被救援的轮廓均标记需人工复核（紫色）。
- 定量：W005原H1936px²、手绘覆盖68.44%、IoU0.6166；新共识3243px²、覆盖99.26%、IoU0.7418；旧不安全局部背景12809px²、IoU只有0.1903。手绘为近似范围，不代表物理真值。
- 程序：main.py --case 3e2入口不变，config新增有界半径7px与最大3倍扩面积，可在config_snapshot.json追溯；新增W005四图对比与metrics CSV；所有旧raw/H标签与旧run不可覆盖。
- 本版运行：outputs/case03e2/run_20261010_H_seeded_bounded_consensus_v5；全工程156项pytest通过；原14门禁仍9PASS/2FAIL/3DEFERRED，MANUAL004/009问题未解决。
- 必须注意：右侧十字交叉区域包含其它H分量，**不能**因单个横向H目标覆盖率提高就声称十字完整物理疵病轮廓已经被验收；后续需要独立H几何组关联与物理连续性验证。


## 2026-10-10 Case03-F RAW局部统计小噪点筛选旁路实验

- 用户同意试验通过面积+局部RAW对比度+MAD显著性区分小候选与背景噪声。新建src/detection/candidate_local_noise.py、scripts/run_case03f_localcontrast_trial.py、scripts/evaluate_case03f_manual_check.py及tests/test_case03f_localcontrast_trial.py；参数统一置于config/user_config.py。
- 完全沿用Case03-E2 H种子受约束方案v5既有9个窗口与原H连通域，**不修改、不覆盖**RAW、历史H掩膜、人工标签、Case02/03B/03C/03D/03E2输出，不对主流程执行物理过滤。每个原H候选始终归档保留，新建outputs/case03f_localcontrast/run_20261010_small_raw_contrast_v1独立实验。
- 原始12bit RAW上计算候选中位数、外围12px参考环带中位数及MAD（排除全部H及2px内环），形成相对灰度差和稳健显著性。仅面积<=5px²候选在有效参考下对比度<8%或显著性Z<3时建议隐藏；较大、邻接大H或窗口边界参考无效者保护。仅使用原始H作为判别输入，人工ROI多边形仅用于后验评价。
- 九窗口原始1569候选/11802源H像素完整保留；实验建议在可选显示中隐藏1288组件/2562 H像素，其余224 keep、57 keep_review；**以上不是经过人工确认的噪声数，更不是误检率**。
- 对10个既有人工近似多边形后验比较：9个内部原H覆盖像素不变；W002（RAW26_MANUAL_009）原48像素中有4像素被建议隐藏，覆盖保留44/48=91.67%，属于不可忽视的弱目标损失风险。W005十字划痕RAW26_MANUAL_003原1668像素100%保留。人工多边形不是物理边界真值，也不是独立测试集。
- 当前结论仅为**实验原型/待人工看图**，不能启用自动永久删点或替代原检测结果。后续特别检查W002弱目标是否应在大候选邻域关联中强制保护。Case04/05和全幅样品27-30未执行。
- 三图对照：figures/E2_W001...W009_before_after_suggestions.png；审计：candidate_trial_decisions.csv、window_trial_summary.csv、manual_polygon_retention_posthoc.csv、trial_summary.json。运行命令python scripts/run_case03f_localcontrast_trial.py --run-id <新ID>；只允许使用新的run-id，不覆盖既有实验。


## 2026-10-10 Case03-F图片输出修复

- 问题复核：原`outputs/case03f_localcontrast/run_20261010_small_raw_contrast_v1/figures`确实没有PNG；`cv2.imwrite()`在Windows中文路径下可能静默保存失败，旧脚本未检查返回值。
- 修改`scripts/run_case03f_localcontrast_trial.py`：以`cv2.imencode('.png', image)`+`Path.write_bytes()`替代`cv2.imwrite()`，并增加编码状态与文件大小校验。
- 使用新运行编号`run_20261010_small_raw_contrast_pngfix_v2`重复生成全部9张对照图，并**补充复制**到原v1的空`figures`文件夹。原始RAW、H、历史运行统计CSV和人工标注均未更改。
- 已通过目录检查：v1 `figures`含9张PNG，文件大小337234–593131 bytes；`cv2.imdecode()`9张均成功，尺寸282×768×3。


## 2026-10-10 Case03-G 十个例子 × 九窗口联合筛噪和H约束轮廓精修

- 用户明确纠正测试集为**10个例子**，不是9例：RAW26_MANUAL_001、002、003、004、006、007、008、009、010、011；其中007/008两处位于同一个256×256窗口E2_W001，所以10个例子对应9个原图窗口。005标记无异常本阶段排除，不能充当疵病真值。
- 新增src/detection/case03g_joint_gate.py、scripts/run_case03g_joint_noise_refinement.py、scripts/build_case03g_contact_sheet.py及tests/test_case03g_joint_gate.py；入口main.py --case 3g --run-id <new-id>；所有新试验参数集中于config/user_config.py。
- 仅从Case03-F原RAW筛选决策读取弱小候选状态，并依据原H中面积>=6px²结构的8px邻域及已有Case03-E2-H5 Gaussian22/Closing61精修证据自动保护弱小候选；判定**没有使用任何人工多边形/点位**。复用Case03-E2-H5已有Gaussian22/Closing61有界精修轮廓，不允许高斯/形态学独立生成新目标；暂不重新运行滤波器，也不修改先前精修算法。
- 对每个原H组件ID（Hlocal_XXXX）精确一对一映射到此前的E2_Wxxx_Oxxxx精修对象，验证原H像素归属和精修面积一致；**源RAW/H/精修mask、旧筛噪CSV及人工标签不改变**。判定仅用于新阶段的可逆输出显示；低置信度源像素和其精修结果完整保存在旧档案。
- 新建outputs/case03g_joint/run_20261010_10target_noise_refinement_v1，figures_10_targets有**10张**独立四栏图（RAW人工多边形辅助审阅/H候选/筛噪/联合精修），figures_9_windows有9张窗口图，ten_target_overview.png可集中浏览10例；所有PNG经编码、文件存在和解码检查。
- 定量：九窗口1569个源H组件、11802源H像素完全保留归档。可选显示层建议隐藏1056候选、保护复核289、直接保留224；显示保留9796原H像素。既有精修原轮廓联合17300像素，显示门控15294像素（非真实疵病面积、非性能指标）。
- 后验10例近似人工多边形：10例原H像素交集全部保留，无任何H覆盖损失；W002 RAW26_MANUAL_009从上一轮显示后48→44修正为48→48；W005 RAW26_MANUAL_003的原H交集1668像素保持1668，已存有界精修后交集2419。请注意用户画的粗略范围不等同物理边界真值，且本样本是算法开发样本，不能用来声称真实召回率/误报率。
- 审计：joint_candidate_audit.csv、nine_window_comparison.csv、ten_manual_targets_posthoc.csv、summary.json、config_snapshot.json；162既有+5新增=**167项pytest全部通过**。
- 当前为9窗口10人工目标的研发对照，**未开展整幅11276×9200扫描和外部样品盲测**，Case04/05未执行。人工验收状态PENDING USER。下一步先人工检查十个逐例四栏图，重点考核单点、W002和W005是否需要微调保护半径与安全精修策略。

## 2026-10-10 Case03-H：第007例绿噪声残留与中等面积纹理筛选试验

- 用户发现第007例四栏图红圈仍有大量绿色背景散斑。E2_W001原H候选237：旧Case03-G隐藏94，放行63个面积>=6px²候选，保护复核80个小候选；表明只过滤<=5px²不足。
- 第一轮仅以面积6~30、RAW对比度<6%、MAD Z<2.5筛选的v1，在E2_W002用户真实弱暗点（RAW26_MANUAL_009）产生严重丢失，原H人工多边形重合48px变4px。保留该失败结果作为反例，禁止将v1启用为自动输出。
- 实测W002弱暗点的三个主要H分量原RAW相对对比度3.6~4%、MAD Z约1.74~2.01，但Gaussian sigma8-sigma2的DoG原H中位DN分别约22.21、17.81、29.93。这说明单纯灰度显著性不足以区分微弱真实暗斑和背景。
- 新增src/detection/case03h_background_texture.py：只对6~30px²中等面积H作可逆低置信度标记，同时保护强BlackHat峰、细长H结构、近大H结构、DoG暗核中位>=16DN的H。DoG只提供保护，不独立生成目标。阈值仍是开发样本经验参数，无独立标定。所有参数集中user_config.py。
- 工程入口main.py --case 3h --run-id NEW_ID，脚本scripts/run_case03h_texture_trial.py读取只读Case03E2/03F/03G存档和12bit RAW，沿用既有Gaussian22/Closing61受约束轮廓，不重做精修也不生成G/M独立目标。标注仅在判定之后用于后验图册和交集，不参与门控。
- 最终可看版本 outputs/case03h_texture/run_20261010_10target_texture_dog_guard_v3：十个样例5栏PNG、九窗口5栏PNG、ten_target_overview_5panel.png，以及candidate_screen_audit.csv、ten_target_retention_review.csv、window_summary.csv、summary.json、config_snapshot.json。所有图片已实际写入且通过解码。
- 定量：九窗口1569个原H组件均归档保留；旧Case03G显示建议隐藏1056，新Case03H显示建议隐藏1210（新增154）；原H可选显示像素从9796降到8359，预计算精修可选显示像素从15294降到13252，不能解释成真实噪声误检率或物理疵病面积。
- 后验10人工示例原H多边形交集均无显示损失。W002弱暗点48/48、精修73/73；W005十字划痕1668/1668、精修2419/2419。人工手绘是粗略范围、也是开发集，不是独立盲测准确率。
- 全工程174项pytest通过。Case03H依然是试验阶段，仅保留可逆显示建议，不永久删除源H/精修结果。尚未评价27～30样品、整幅自动检测或Case04/05。

## 2026-10-10 Case03-T：26号第二帧固定/全局MAD/局部MAD双阈值对照

- 用户怀疑历史170/230 Black-Hat DN固定双阈值泛化受限，要求在26号第2帧试验。已独立读取D盘26 (2).raw，基于原Case02 black_hat_uint16椭圆3/5/9/15/31px结构元重算整幅9200×11276融合Black-Hat响应，保存到outputs/case03t_threshold_pilot/run_20261010_sample26_frame2_response_v1/fused_blackhat_26_frame2_uint16.npy；RAW不变。
- 固定170/230对照统计背景上2%截尾全图median+3.5sigma / median+5sigma，sigma=1.4826MAD且下限3DN，双阈值下限20/40DN及最小差15DN；全局阈值144.1602/193.0860DN。局部256px网格（采样步长4）独立统计并连续插值，1620格，低floor占0%，高floor占15.49%。统计参数写入config/user_config.py，不依赖26(2)人工标注。
- 试验只在第一帧历史9个256窗口位置 + 9个规则空间控制窗口提取真实第2帧H候选（8连通滞后），三个阈值均独立重算同样Case03E2_H5锚定Gaussian22/Closing61有界精修及Case03F/G/H RAW筛噪；第1帧10个坐标仅用于第2帧同位置视觉回放，不作为第2帧真值或候选种子。总计54个窗口×方法比较，完整全帧处理只到BlackHat响应阶段，尚未执行全图连通域统计。
- 结果历史9窗口固定/全局MAD/局部MAD的候选数量分别416 /4767 /6；经过同样后端后H可选显示像素为1938/12412/1015。控制9窗口候选分别122/1744/73。全局MAD阈值偏宽松导致候选数量激增；局部MAD高纹理区域阈值可达200~350DN导致候选可能漏检。没有第二帧真值，不代表真实误检/漏检率；**目前不能替换固定170/230基线**。
- 结果目录outputs/case03t_threshold_pilot/run_20261010_sample26_frame2_three_methods_v1；报告CASE03T_EXPERIMENT_REPORT.md；总览historical9_contact_sheet.png、spatial_controls9_contact_sheet.png、ten_position_replay_contact_sheet.png，18张七栏窗口图片与10张坐标回放图片，保存并解码验证。完整统计18windows_3methods_metrics.csv、local_grid_statistics.csv、summary.json、masks以及config_snapshot.json。
- 新源码src/detection/case03t_adaptive_hysteresis.py、src/detection/case03t_hseeded_variable.py、scripts/run_case03t_prepare_response.py、scripts/run_case03t_threeway_comparison.py、scripts/build_case03t_contact_sheets.py及tests/test_case03t_adaptive_hysteresis.py。
- 历史src/detection/case03e2_hseeded.py接口已恢复原状；可变阈值扩展独立存在Case03-T模块；所有旧Case03数据保持不变。待开展26(2)独立人工标注及隔离背景黑带/有界统计方案研发；调参后26(2)不能再作为独立验证数据。

## 2026-10-10 Case03-I：RAW上自动轮廓标记、面积/长度分级与颜色标注

- 用户决定**暂缓开发全局自适应辅助补漏**（固定170/230作首选，之前全局Median/MAD更多噪声、局部MAD漏检），现阶段优先完成原始RAW叠加轮廓编号和基于尺寸分级；该延期决定记录在Case03I报告，不允许擅自重启自适应开发。
- 新增src/detection/case03i_size_grade.py和scripts/run_case03i_annotation.py；面积为Case03-H后保留的约束精修二值掩膜8邻接像素数，长度为该连通块像素中心凸包的最大点间距离（下限1px），并输出等效圆直径、整图坐标中心、bbox、触窗截断标记；一个物理划痕有多个断开连通段仍分开列出。
- 仅演示性尺寸档位：绿小(A<40px²且L<15px)，黄中(A>=40或L>=15且不满足大)，红大(A>=250px²或L>=45px)，**面积或长度任一升级即使用较高尺寸档位**。颜色不表示真伪、质量风险或不合格；用户配置字段CASE03I_*，不将探测器像元3.2μm直接作为物面校正尺寸。
- 第一帧只读Case03-H v3和Case03-E2-H5原H及历史有界精修标签，标注9个256窗口；第二帧只读Case03-T独立重建的26(2)固定170/230+Case03-H筛噪结果，标注18个256窗口（9历史位置+9独立空间控窗）。不重新调整阈值、不使用人工点位检测；第一帧人工10位置只用于生成后验查看裁剪图。
- 新目录outputs/case03i_annotation/run_20261010_frame1_frame2_pixel_grade_v1：frame26_1_9roi_contact.png、frame26_2_18roi_contact.png、frame26_1_10targets_contact.png、两张frame*_ROI_locations_on_raw_overview.png、9+18张单窗口PNG、10张局部焦点PNG、region_masks/*.npz（精确分割、局部标记、等级uint8和坐标）、all_candidate_size_grades.csv、roi_grade_summary.csv、summary.json、CASE03I_REPORT.md，实际运行成功。
- 9个26(1)窗口共349个显示连通块，其中小322、中16、大11；18个26(2)窗口117块，小108、中4、大5；这些数据仅是窗口级**疑似候选**，不是整幅图物理疵病总数，也未做跨窗口去重。未扫描的全图区域不得认定阴性。
- 本阶段图注中绿色=小尺寸、黄色=中尺寸、红色=大尺寸。此前橙色可逆噪声建议隐藏的候选不显示在等级主图；旧候选仍归档。图片叠加为RAW的显示灰度映射，不修改原RAW数值，尺寸统计来自精确布尔掩膜。
- 试验配置统一在config/user_config.py，入口main.py --case 3i --run-id <独立名字>，测试tests/test_case03i_size_grade.py，新增测试约束大小/长度升级、细线长度、多个不相连目标、ROI边界、像素长度下限及空窗口。后续应经人工核对再扩展全帧tile处理与跨窗口物理合并。此阶段未完成全帧无遗漏检测或微米标定。

## 2026-10-10 Case03-J1：断裂疵病归属关联预研，W005验证

- 用户认可在不更改原始像素轮廓的情况下，对断裂划痕做物理对象级关联、统一编号与面积/长度分级，以避免同一划痕在Case03-I被拆分成多个连通域。**这不等于授权把邻近所有区域一律并为同一疵病；必须防止噪点误关联。**
- 新算法src/detection/case03j_fragment_association.py：组件轮廓最近距离、PCA/包围框主轴方向、DoG(sigma8-sigma2)原RAW断点的正向暗线支持；8连通H原组件标签只用于源ID，关联只产生对象成员关系和ID，不会膨胀、涂画或删除分割mask。参数CASE03J_*均在user_config.py；人工点位未用于关联。面积为各段原像素和；综合最大长度为成员像素凸包直线跨度，不是划痕中心线路径长度；尺寸档沿用Case03-I暂定规则。
- 第一版曾在合成双小暗斑测试中错误合并，已修正短距离例外规则（需要至少一个>=12px线状跨度），保留第一版历史输出不覆写。正式可视化试验采用outputs/case03j_fragment_association/run_20261010_W005_fragment_link_guarded_v2。
- W005原29连通区域变24疑似对象，成员原ID7;12;15;16;19;20归为1个对象E2_W005_OBJ0007，面积4866px²，直线跨度187.2111px、颜色红。窗口原像素5160关联后仍5160；其余邻近区域不会无条件合并。窗口级27窗总466个连通域→459个疑似对象，3组多段对象，7条有效链接；**无跨窗去重，无整幅图检测，不可当作实际物理疵病数**。
- 检查图figures_first9/E2_W005_original_vs_grouped.png（三栏：RAW/独立轮廓/新对象统一颜色与编号）；总输出27张PNG、27份exact_masks NPZ、object_hypotheses.csv、source_region_to_object.csv、association_link_audit.csv、window_before_after_counts.csv、summary.json与CASE03J_PILOT_REPORT.md。27张PNG成功解码、源分割像素和标签与Case03-I逐像素一致，所有193项pytest通过。
- 源码测试tests/test_case03j_fragment_association.py，QA scripts/verify_case03j_fragment_outputs.py，入口main.py --case 3j --run-id NEW_ID。旧Case03-H/I及固定170/230流程未改。应先请用户核验W005的6段物理归属，再扩展全图分块、跨窗合并与真实中心线长度评价。用户此前要求全局自适应补漏暂缓，继续保持暂缓。

## 2026-10-10 Case03-J2：用户要求十字划痕显示成实际一整块连续轮廓

- 用户上传W005的J1旧三栏截图，指出“没什么区别，十字叉丝线应该是一个整体，但当前还是分块的”。确认原J1仅做**对象归属合并**、未做衍生像素的桥接或整体contour，视觉断点保留，用户指出的问题确实存在。
- Case03-J2新模块src/detection/case03j_continuous_contour.py：根据经验证的J1配对边、长水平划痕方向、RAW的sigma8-sigma2暗线DoG证据，扩展右侧断裂片；将恰好位于已验证暗线桥带、含充分DoG暗核的小原始碎片并入整体对象；经验证的相邻端点之间生成**独立推断桥接掩膜**、并作八连通校验。原H/精修/Case03-I真实候选像素完全保持不变；新增像素仅用于衍生显示，不作为实际测量面积；没有对周边所有噪点无条件合并。
- 在W005原29块中自动关联源ID`7;12;14;15;16;17;19;20`共8块为**同一完整可视轮廓**；W005变22个对象；新增441个仅用于显示的推断桥接像素；原W005候选5160px不变；合并对象原始检测面积5068px²不含441px桥接；连续显示掩膜为1个八连通区域。
- 已计算独立对象邻接保护：全部27窗的桥接像素没有八邻域触碰其他不同对象的源mask。第一版含短桥邻接原ID14的情况，已在通用高DoG支持微碎段归属逻辑中解决，不能将该修订理解为无需人工复核。J2全27窗口原466块→457个疑似对象，所有显示衍生桥接像素合计463；仍只是27个ROI，不是全图缺陷总数。
- 新图`outputs/case03j_continuous/run_20261010_27windows_one_piece_v2/figures/26_1_E2_W005_connected_fourpanel.png`，四栏分别为RAW、分块原轮廓、连接后真实单个八连通整体轮廓、青色桥接推断像素来源；用户应主要看第三栏是否真的与想要的十字整体效果一致，并检查第四栏是否沿真实暗线。
- 新目录保存27张四栏PNG、27份NPZ（source_exact_mask/original_region_labels/grouped_original_only_ids/inferred_bridge_ids/one_piece_visual_ids）、对象级csv、连接边与推断像素审计csv、summary.json和CASE03J2_CONTINUOUS_REPORT.md。全部27张PNG解码、27份原mask逐像素比较及桥接与其他对象不邻接验证通过。测试tests/test_case03j_continuous_contour.py新增3项，**全工程196项pytest通过**。入口main.py --case 3j2 --run-id UNIQUE，关键参数config/user_config.py CASE03J2_*；不能覆盖历史。
- 下一步只有在用户认可第三/四栏图之后才将J2应用到全幅11276×9200自动检测，并针对分块边界、跨窗归并、错误连接继续独立验证。全局自适应补漏保持暂缓。

## 2026-10-12 Case03-J4：整幅26(1)RAW分块检测+对象级外接框，和J5区别

- 用户直接要求实现J4，同时问“case5是什么”。明确：**Case03-J5不是Case05，而是J4下一子阶段，负责跨图块归并、去重、最终全图DEFECT_xxxx编号和实际全图尺寸统计**；目前只实现J4，不以局部数量冒充全图物理疵病数。
- 新代码`scripts/run_case03j4_fullscan.py`，`src/visualization/case03j_object_boxes.py`，新增`tests/test_case03j4_fullscan.py`共4项测试、`scripts/verify_case03j4_outputs.py`增量独立QA，`main.py --case 3j4 --run-id NAME`入口，参数`config/user_config.py CASE03J4_CORE_SIZE_PX=256,CASE03J4_HALO_PX=64`。
- 26(1)RAW实际形状9200×11276，在磁盘复用既有Case02全图`blackhat_fused.npz`（12bit DN uint16），流式解压为只读磁盘映射NPY，保护有限RAM。Core尺寸256，外围halo64，完整覆盖45×36=1620个互不重叠核心块，保留末尾不足256条带，必要时向内加宽处理区。每tile复用**固定170/230的Case03-T process_one、Hseeded Gaussian22/Closing61、Case03-F/G/H、Case03-I等级、Case03-J1/J2断裂关联与桥接**。局部经关联对象每个有一个整体bbox，遇core边缘标ROI_CLIPPED；小点默认仅画轮廓（减少拥挤），中/大对象画框。
- 输入RAW/BlackHat与原Case03-H/J全部只读；推断桥接不计入检测面积。每块生成tile_status/*.json（提交凭证）、tile_masks/*.npz（原检测、原区域ID、组别标签、桥接、显示标签）、tile_objects/*.csv和非空图块`tiles_marked/*_fourpanel.png`。任何tile失败会停止且写failed_tile.json，不允许静默跳过。可中断后用`python scripts/run_case03j4_fullscan.py --run-id run_20261012_frame26_1_full_j4_v1 --resume`，但**不能与仍在运行的同名进程并发**。配置快照保护防不同版本混跑。
- 正式全帧扫描**已在远程电脑启动**：`outputs/case03j4_fullframe/run_20261012_frame26_1_full_j4_v1`（进程初始PowerShell PID9076），总1620核心块。因为约0.6~1.3sec/块，完整任务时间较长；只有`run_status.json stage=J4_COMPLETE,completed_tiles=1620`方可宣布整幅图全部处理完成。扫描完成才会有`frame26_1_full_preview_unmerged.png`、`j4_unmerged_tile_objects.csv`、`tile_manifest.csv`。请勿过早把进程中部分数量视为全图总数。
- 首6块的独立试跑成功；初期前139个图块经过`scripts/verify_case03j4_outputs.py`独立核验，源标签与显示关系逐像素一致，139张PNG可正常解码，无failed_tile。彼时得到5682个图块局部对象、401个边界截断，均不是最终全图疵病数量。**200项全工程pytest通过**。
- 操作/范围详见本次输出文件`CASE03J4_IMPLEMENTATION.md`。后续J5需先验证跨块避免重复统计且不误并不同疵病；之前用户要求全局MAD辅助补漏暂缓，继续保持暂缓。

## 2026-10-12 Case03-J5 已完成全图跨图块归并、编号与统计

- 用户明确要求“直接开展Case03-J5”。已实现于`src/detection/case03j5_seam_match.py`＋`scripts/run_case03j5_global_merge.py`；统一参数在config/user_config.py的CASE03J5_*，入口`python main.py --case 3j5 --run-id NEW_UNIQUE_NAME`。测试`tests/test_case03j5_seam_match.py`，QA`scripts/verify_case03j5_global_outputs.py`。
- 使用冻结、完整的Case03-J4 `outputs/case03j4_fullframe/run_20261012_frame26_1_full_j4_v1`（1620个互不重叠256核心块，26号第1帧）。从原图块真实候选标签`grouped_source_only_i32`进行跨右/下/斜角边界匹配。直接源像素八邻域接触视为高确定性；若间隔<=18px则还须两块几何、方向、RAW DoG暗线支持；多个候选间距相近且归属模糊的保守拒绝。并查集进行关联，不回写或更改H/Case03-H/J4源掩膜、不将J2推断连接像素算进原检测面积。全局中心来自源像素矩，跨块Feret来自成员凸包准确旋转卡尺、外接框为成员bbox并集极值。按y后x从小到大赋唯一`DEFECT_00001...`编号。
- 已实际完成`outputs/case03j5_global/run_20261012_frame26_1_global_j5_v1`，summary.json:stage=J5_COMPLETE。J4局部15934个对象→J5唯一全局候选15604个，覆盖1620块；6239图块邻接关系、1444候选pair；接受342条合并关系（341直接源像素相邻＋1条灰度/方向验证的断开假设，后者保留review标记），有效并查集归并330次，264个对象跨越多个图块。源检测有效面积保持`234029px²`完全不变。绿SMALL14884、黄MEDIUM593、红LARGE127。这些包含疑似噪点，**不等同于真实疵病数**，不是Precision/Recall，未有独立人工真值。
- W005十字疵病经J5有统一对象ID`DEFECT_07328`，来源T004_011及T004_012，全局外接框`(x=2987,y=1071,w=331,h=125)`px，原检测源面积7689px²，整体源像素Feret330.1227px，红色“大”。已实际查看`review_crops/DEFECT_07328_review.png`左右RAW与完整框图，对整个十字左右水平与上下臂统一矩形。J2桥接仅作显示辅助，不计面积。
- 结果目录`global_defects.csv`（全局ID、中心、面积、Feret、等级、bbox）、`global_object_membership.csv`（15934局部对象→全局ID完整追溯）、`cross_tile_matching_audit.csv`（1444条配对接受/拒绝和灰度/方向证据）、`full_frame_all_sizes_unreviewed.png`、`full_frame_medium_large_unreviewed.png`、`review_crops`（20张样例）、`summary.json`、`config_snapshot.json`及`CASE03J5_IMPLEMENTATION_REPORT.md`。
- 独立QA `J5_QA_PASS`全量逐对象验证唯一归属、每个全局bbox确由局部成员合成、面积守恒、等级重算一致、跨块接受边都有审计依据、22张PNG有效解码。**208项全工程pytest全部通过**。
- 局限：J5只跨tile对象归并，不改变当前原始算法漏检/误检；全图全局候选仍可能含较多背景噪点，真实物理疵病总数未人工确认；像素面积/跨度未进行物面标定，演示颜色不等于工业验收结论；若两段仅以有证据的gap关联，未额外绘制跨tile填充像素，只有整体bbox。
- 建议下一阶段Case03-K：人工ROI真值标注、Recall/Precision、每百万像素误检密度、轮廓完整性及错误归因；保留26(2)或其他未调参样本用于盲测。此前用户要求全局MAD辅助补漏暂缓，该决策继续有效。

## 2026-10-12：用户确认J5主图按大小分离，并开展轻量版Case03-K0

- 用户指出J5全图绿色小候选绝大多数肉眼看来是背景噪点，要求：**中、大尺寸疵病独立一张图作为工程主图，绿色小尺寸候选单独一张辅助人工参考**。同意轻量版Case03-K只在有助于算法改进时继续，不进行没有针对性的全图人工标注、不贸然修改固定170/230和Case03-H。
- 已完成`scripts/export_case03j5_split_views.py`，实际目录`outputs/case03j5_global/run_20261012_frame26_1_global_j5_v1/separate_size_views_v1`：`medium_large_main.png`（黄593＋红127＝720）、`small_reference.png`（绿14884）、`medium_large_defects.csv`、`small_defects_reference.csv`、`summary.json`。只改变显示/CSV筛选，全部15604条J5唯一ID互斥覆盖且与原J5一致。两图使用相同26(1)RAW底图、相同坐标原点、1:8预览比例；小点只画辅助绿色1px圆点，不能当做真实物理疵病。
- 新的轻量版`scripts/prepare_case03k_light_review.py`从当前J5 SMALL对象抽取96个跨全图、按检测面积分层样例（1、2-3、4-7、8+px²，各24）以及24个全图均衡的**无任何J5预测bbox落入其中**的128×128ROI（不是已确认为无疵病！）；同一帧随机种子20261012，记录全部sample ID、J5全局ID、原坐标、源像素面积与Feret等。输出目录`outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2`包含120张RAW+目标指示双栏图、5张`contact_sheets`总览、`manual_review_template.csv`空白人工标注、`unlabeled_features.csv`统计特征、`summary.json`和`CASE03K0_README.md`。
- 绿色候选的数值特征有RAW局部中位数、MAD、std、目标灰度、背景环带对比度/MAD显著性、融合BlackHat峰值、DoG暗核、距离中大候选等；**尚未标注真实/噪声**，不得计算Precision/Recall或把特征当有效筛噪规则。允许人工填写`REAL_MICRO_DEFECT`、`BACKGROUND_NOISE`或`UNCERTAIN`；空预测ROI应人工判断是否存在漏检，同时注明ROI是否充分复核，不能把算法没框的区域自动标注为阴性。
- 预留`scripts/analyze_case03k_manual_labels.py --reviewed-csv PATH`，等人工填表后只作特征的描述性组间比较，**不自动改主算法**，至少5真实+5噪声才做比较，人工不够则记录待复核。当前26号第一帧开发样本不是独立盲测，任何从它推导的规则必须在26(2)或其他未参与调参帧验证后才能宣称有效。
- QA`scripts/verify_case03k_light_review_outputs.py`已核实两级CSV互斥完整覆盖15604条、两张全图大小一致、96样本正确索引J5、24无预测ROI无J5 bbox交叠、所有120张cards和5张contact PNG真实可解码；独立输出`J5_SPLIT_K0_QA_PASS`。新增`tests/test_case03k_light_review.py`3项测试，**全工程211 passed**。原J5/H/J4和RAW一概未更改。

## 2026-10-12 Case03-K人工首轮反馈记录（新增）

- 用户在首轮`first_pass_review_30_contact.png`看图后明确说“只有53，54，77，73，74确认为微小疵病”。这五项等价于`K0_SMALL_053,054,073,074,077`，只属于首轮30个样本中的24个SMALL_CANDIDATE。按“只有”把其他**19个本轮候选**记录为用户目视判断的`BACKGROUND_NOISE`；六个`NO_J5_CANDIDATE_ROI`用户没有对是否漏检做评价，**仍为空白**，其他72个尚未看的小候选继续未标注。用户没有提供置信度，留空；人工对候选点的判断不等于该128px区域内所有疵病均已复核。
- 新的人工作业记录独立存放`outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2/first_pass_review_30_user_feedback_20261012.csv`，原`first_pass_review_30.csv`及`manual_review_template.csv`未覆盖。另有`first_pass_user_feedback_provenance.json`。执行脚本`scripts/record_case03k_first_pass_feedback.py`保证来源不变及正例正好五项，不能重复覆盖。
- `scripts/analyze_case03k_manual_labels.py`已在上述人工反馈CSV上运行：5真实、19噪声；`manual_labels_feature_comparison.csv`和`manual_labels_exploratory_report.json`生成。另由`scripts/summarize_case03k_first_pass.py`保存`first_pass_evidence_20261012.md`与`first_pass_hypothetical_rule_sensitivity.csv`。
- 按人为分层每组只复核了6个：面积1px²的6/6被判噪声；2-3px²的6/6噪声；4-7px²中2真实/4噪声；8px²以上3真实/3噪声。**是真实5/24，但不能外推为全图小候选Precision**，因为人为按面积强制平均抽样，且用户根据肉眼判断未作独立显微确认。
- 五个真实的源检测面积分别为4px²(053)、4px²(054)、8px²(073)、24px²(074)、35px²(077)。故若简单采用面积>=5px²规则将误删053和054，**不得仅以尺寸门限提高为优化**。BlackHat峰值/相对暗对比中位数不能清晰区分两类，甚至噪声中位可能高于真实；DoG的中位较大（真实23.939DN vs噪声7.383DN），但有明显交叉（真实最低7.4965DN、噪声最高16.8635DN），不可一刀切。
- Case03-H、固定170/230、Case03-J5全局原掩膜和主图／小图分离方案全部保持不变；没有部署任何新的删除规则。后续优先再标注4-7及8+的未标样例，保留少量1-3px样例，检查无预测ROI漏检，并用独立26号第二帧验证是否真有能普适工作的二次筛噪特征。目的只是决定K是否值得继续开发。

## 2026-10-12 Case03-K 74号更正（用户最新人工判断）

- 用户明确更正“74不算微小疵病了，黑斑非常明显”。已查看`cards/K0_SMALL_074.png`，RAW中有十分明显的大暗斑可见结构，而算法J5对象`DEFECT_10725`只记录源检测面积24px²、Feret 9.8489px、bbox8x10px，因此误以SMALL绿色输出。注意明显黑斑的可见周边与精确真实疵病物面面积尚需定界，不能直接当真实尺寸。**人工真实/噪声属性与几何尺寸分级必须分别管理**。
- 之前用户反馈的五例真实候选中，真“微小”实际只有53、54、73、77四例；74为`REAL_OBVIOUS_DARK_SPOT`，仍然是**真实疵病**；其余首轮19个候选仍按人工噪声，6个NO_J5_CANDIDATE_ROI仍未评价。不能再把74纳入“真实微小疵病”特征组。
- 已生成**版本化修订**`outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2/revision_074_obvious_dark_spot_20261012/`：`first_pass_review_30_labels_corrected.csv`、`corrected_feature_comparison.csv`、`revision_provenance.json`、`correction_notes.md`；脚本`scripts/revise_case03k_label_074.py`。原始首轮标签CSV、原本K0统计和RAW/H/J5检测掩膜/工程配置均不覆写。
- 真实微小4例DoG中位值约18.9927DN，而旧统计把74（DoG55.4287DN）混入后为23.939DN；人工噪声19例中位7.3834DN。**不要用旧五例DoG均值/中位来专门推断微小疵病暗核特性**，微小4例数量不足且与噪声有交叉；不可据此提高阈值。
- 74号后续单独作为`J5尺寸等级低估/真实黑斑显著但检测核心过小`的轮廓完整性分析样例。要检查真实RAW暗核与晕染边界、原H/精修轮廓覆盖关系，确定是否为轮廓低估还是“尺寸 vs 视觉显著性”不同，不可未经检查断言特定原因。不要因为用户更新分类直接重新标J5绿色/红色；J5尺寸显示仍按冻结算法统计，修订仅是人工评价元数据。

## 2026-10-12 Case03-K2：74号明显黑斑的候选轮廓低估原因已实际确证

- 用户特别强调“第二个问题（真实明显黑斑却被分割成小尺寸）很重要”，决定优先调研**轮廓完整性**，不继续盲目筛绿噪点。
- 已直接检查26(1).raw的K0_SMALL_074/J5 `DEFECT_10725`：全局中心(5699,5670)，原ROI[5635,5606,5763,5734]。完整重算固定H170/230 + 现有精修/Case03-H阶段：**H原始相应连通分量24px、后续H保留24px、J4/J5源掩膜24px**，外缘没被后续筛噪/J5丢失，而是**最初H仅发现明显黑斑核心，原有边界精修未生效**。J5源bbox仅8×10px，Feret9.85px，因此SMALL绿色是算法当前数据的形式性结果，不符肉眼明显黑斑的视觉范围。
- 全图融合BlackHat中该24px源响应170～233DN（中位188.5DN，高于高阈值230的像素仅一处）；半径6–9px中位116DN、9–12px中位88DN，过不了低阈值170；但RAW灰度在0–3px径向约901DN、9–12px约981DN、24–27px约1043DN，明显有渐变暗色外围。具体真实缺陷边缘/光学暗晕需区分，不能把所有暗晕确认为物理疵病。
- 新脚本`scripts/diagnose_case03k2_spot_074.py`，只读原RAW+J4/J5掩膜。研究性方法：Gaussian sigma20宽背景减sigma1.3局部平滑生成暗度残差，连通域必须与原24px源mask重叠、r<=34px，阈值同时不低于3倍外围MAD sigma和局部峰值的15/25/35/50%；候选范围分别638/544/325/205 px²（对应33×29、32×27、23×21、17×18px bbox），这些**只是可视边缘假设并非实测疵病尺寸**。输出`outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2/K2_obvious_spot_074_extent_diagnostic_v1/074_original_H_J5_vs_local_extent_8panels.png`、`074_exact_trial_masks.npz`、`radial_profile.csv`、`diagnostic_summary.json`、`CASE03K2_REPORT.md`。已经打开验证图像。
- 为避免只针对74过拟合，另脚本`scripts/compare_case03k2_contour_control.py`在首轮24例人工判断样本重跑同方法。35%时74源24→候选325px²；73源8→候选218px²（可能扩大过度，需人工确认真实边缘）；53、54、77原本是真实微点但新规则未得到可用连通候选，不能替换原分割；19例被目视判噪的多数候选没有扩展；结果`K2_contour_expansion_control_review_v1/contour_trial_real_vs_noise_contact.png`、`all_first24_contour_trial_audit.csv`、`group_descriptive_statistics.csv`。
- QA核实: H原分量=J5源mask=24px，四档候选面积和源含量一致，8面板PNG可解码，24例数据来源一致。全部数据/掩膜只读，**没有修改H170/230、Case03-H、J4、J5生产参数/源mask**。
- 结论：应考虑**双层轮廓**：既有固定阈值候选定位（不动）+ 对强且具空间相干暗核的真实暗斑做有背景估计/局部尺度/受限区域生长的可撤销补边，只用于轮廓候选显示；需要更多强黑斑/弱真微点/噪声对照与用户确认实际边界（暗核 vs 外围散射/晕染），并独立验证后才允许替换正式面积和尺寸分级。注意K0 user修订74为明显黑斑，而53/54/73/77仍为真微点。

## 2026-10-12 Case03-K2 74号黑斑外轮廓仍偏小，最新进一步试验
- 用户指出此前15%外轮廓仍不完整。再次确认原K2门限`max(3sigma,15%peak)`中3sigma≈27DN>15%peak≈19DN，仅下降15%百分比不能绕开噪声门限；Gaussian sigma20局部背景也会混入宽黑斑暗晕从而压低外围信号。
- 已于74号原128×128 ROI（中心5699,5670，原H/J5源24px）进行只读背景方法与阈值敏感性试验。脚本`scripts/diagnose_case03k2b_spot074_background.py`、`scripts/diagnose_case03k2c_spot074_threshold_sensitivity.py`。输出`outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2/K2b_074_outer_dark_halo_models_v1/074_boundary_model_and_noise_floor_16panel.png`与`K2c_074_lower_floor_guarded_experiment_v2/074_stricter_vs_broader_boundary_8panel.png`，另存CSV、JSON和完整`CASE03K2BC_REPORT.md`。
- 老15%K2候选638px²；背景换为外环r38~58的稳健二维一阶平面，仍15%+3sigma时1203px²。沿同一平面方法，10%+3sigma1279、10%+2sigma1501、5%+1.5sigma1659px²；但其他独立暗噪声分量由4增至30，说明越降阈值误吸收噪声风险越大。注意外环方法同时改变噪声估计，不能把638→1203仅归因于背景模型。所有都是未经人工验收的轮廓候选、并非实际测量疵病面积。
- 建议先请用户看8panel新图确定视觉目标范围：高可信核心、主体暗斑及外围渐变晕染应区分，考虑双层轮廓显示；不对全图固定170/230、H、J4/J5或用户人工标签做任何修改。低对比度柔性边界没有唯一“物理真实”轮廓，必须定义边界标准并验证其他样本。

## 2026-10-12 Case03-K2d 74号偏小原因的源头参数对照已完成
- 用户问“改黑顶帽或阈值好，还是原方案加受限轮廓修复好”，已核查前端确切配置：BlackHat椭圆核[3,5,9,15,31]px，对各尺度原DN响应逐像素max融合，H170/230。脚本`scripts/diagnose_case03k2d_blackhat_vs_threshold.py`以原74中心384×384 RAW patch重算，冻结Case02融合BlackHat的原128×128范围**逐像素完全一致**，故对照可信。
- 仅增加BH尺度、维持H170/230，锚74源mask的初始H候选面积31→24px²，41→99，61→215，81→248，101→287；黑顶帽响应在原源24px最高值从233升到305DN，证明黑顶帽最大尺度31px对较宽暗斑明显不充分。仅保持BH最大31、改低/高阈值，170/230→24px²，150/230→74，130/230→136，110/180→215，但384上下文高阈值组件数量从2升至46，提示引入大量额外候选种子风险（并非真实误检数）。两者都导致原候选缩小，单独调一项无法直接提取全部视觉外围。
- 重要建议：固定H定位通道保留；新的尺度通道只作候选实验，再基于RAW对明确宽暗斑独立做受限外轮廓精修，保留源掩膜与估计外轮廓两套结果，待人工界定边界和多样本盲测才调整正式面积/等级。弱真实微点/划痕不能一刀切降阈值。
- 结果文件`outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2/K2d_074_blackhat_scale_vs_threshold_v1/`：`074_blackhat_kernel_vs_H_threshold_comparison.png`、`factor_ablation_audit.csv`、`summary.json`、`CASE03K2D_REPORT.md`。未更改任何生产代码与配置。

## 2026-10-12 Case03-K3 独立双阶段宽暗斑轮廓试验（用户同意先按建议试）

- 用户同意优先验证黑顶帽最大核31px是否尺度偏小，再在原RAW采用有证据的受限外轮廓恢复，而非直接改全局固定170/230和所有形态。已完成可运行K3**研究试验**，正式J4/J5源掩膜/参数完全未改。
- 新算法模块`src/detection/case03k3_spot_contour_pilot.py`，新脚本`scripts/run_case03k3_scale61_seeded_pilot.py`（仅BH61对照）、`scripts/run_case03k3_dualstage_pilot.py`（BH61+RAW稳健外环平面估计/噪声阈值/与其他J5对象碰撞及形态检查）、`scripts/run_case03k3_W005_scratch_control.py`、`scripts/verify_case03k3_dualstage_outputs.py`、`tests/test_case03k3_shape_contour_pilot.py`。
- K3双阶段逻辑：保留原J5 H170/230定位锚点，增加仅61px BlackHat响应并用原H170/230锚点拓展，**严禁独立提出新目标**；只有H61候选面积>=60、相对源区域增长>=2、长宽PCA比<=2.5等明显斑点条件才允许后续RAW背景轮廓候选。RAW使用距目标中心r38-58px的稳健拟合背景平面、sigma1.3 Gaussian局部图像，阈值`max(3*MADsigma,15%峰值)`，受限r<=49，必须包含原H源点、大小安全、无竞争J5源对象交叠、无ROI/径向截断，才提供`PROVISIONAL_OUTER_SUGGESTION`。始终`suggested_display`和`original_J5_detected`两份不同mask；不能把前者代入正式测量面积、等级。
- 已在26(1)开发集人工复核的24例小候选（4真实微点:53/54/73/77，1明显黑斑74，19人工噪声）及6个预测无标记未人工确认ROI运行。BH61初始锚定响应面积：53 4→125px²、54 4→156、73 8→87、74 24→215、77 35→194，但**这些不是实际面积或经过筛噪的最终轮廓**，背景噪点个别也扩大、最高30px²；不能全局直接用61代替31。
- 按研究性保护门控，24例中**只有74号**生成RAW候选1203px²的衍生轮廓展示（旧24px全保留、无竞争J5源像素交叠），另23例显示仍用旧源mask。73有RAW候选约219px²但与其他原J5目标相交故拒绝；53/54/77等RAW边界缺乏足够证据不强行扩展。19人工判噪均未开启外轮廓；本样本含人工反馈属于**开发集而非独立验证**，不能推断泛化。
- W005十字划痕DEFECT_07328专门测试：旧J5源7689px²（不变），老BH31锚定高响应候选约4643px，+BH61后同窗H锚定高响应扩展至17375px，提示无形态区别的黑顶帽大尺度会过度扩大/错误连通。**划痕仍走J2/J5原关联线，不应用斑点RAW修复**。
- 输出`outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2/K3_dualstage_contour_pilot_v1`，重点`figures/K0_SMALL_074_fivepanel.png`（原RAW→J5原24px→+BH61 215px→RAW估计1203px→条件式显示轮廓）；`figures/K0_SMALL_073_fivepanel.png`用于审查拒绝因竞争目标，另`review_candidates_19_to_24.png`，`all_30_audit.csv`，24个独立NPZ，`summary.json`、`CASE03K3_REPORT.md`。
- 独立QA`K3_PILOT_INDEPENDENT_QA_PASS`：24个源mask逐像素保留且原图只读，23个非74显示源mask一致，74显示mask=原source并RAW proposal，29张PNG可解码。**全工程215项pytest均通过**。QA是工程一致性，不是正确物理轮廓真实性；74的1203px用户尚未判断是否完整，前期638px曾被用户判断仍不完整，务必待用户查看新图后决定进一步边界。

## 2026-10-12 Case03-K4：用户同意将74号认可的K3双阶段轮廓方案扩大验证

- 在用户表示K3对74号基本覆盖、同意扩大样本和后续验证后，**未修改J4/J5/170/230或K3冻结规则**，而是新增脚本`scripts/run_case03k4_expanded_pilot.py`和`scripts/run_case03k4_scale_sensitive_discovery.py`，审计`scripts/verify_case03k4_expanded_outputs.py`；报告`outputs/case03k_expanded_validation/run_20261012_240_green_scale_sensitivity_v1/CASE03K4_REPORT.md`。
- K4扩大普通抽样60个RAW 26(1)区域：12 J5中等级、12大等级（几何小于48px且不截断）、24未使用过的SMALL（4面积档各6）、12个J5没有候选的未人工标注ROI。K3固定核61, H170/230, RAW背景平面/受限边界门控均保持不变，**48个已有J5对象无一个被自动显示扩展，原源像素全保留**。主要拒绝原因累计：RAW外围面积小于黑顶帽扩张范围46次、H61增长不足39、RAW种子不一致34、H61响应面积偏小30、竞争J5对象接触3。绝大多数中大候选现有J5面积已经基本与提取暗核相当，没有扩张不代表方法失效，也不证明外轮廓已物理准确。
- K4S为了寻找与74号类似的“原面积很小但+61px尺度后显著扩张”的样本，在当前J5 14,884绿色候选中，排除K0初次选中的96个、K4已测试的24个，按面积和6x4空间区域、固定随机种子选240例：单像素24、2-3像素24、4-7像素72、8-39像素120。**不使用任何人工真值选样**。其中22例满足冻结K3的BH61成核面积≥60px²、增长≥2倍和近似圆斑形状要求；进一步RAW连通背景/竞争目标过滤，仅1例得到试验性`PROVISIONAL_OUTER_SUGGESTION`：`K4S_079`，原J5源面积7px²，BH61锚定127px²，RAW估计候选179px²。**该对象真实性尚未得到用户确认，不得声称已成功恢复另一个真实暗斑，也不能把179px²算正式面积**。
- K4S输出`outputs/case03k_expanded_validation/run_20261012_240_green_scale_sensitivity_v1`：重点`074_versus_K4S079_side_by_side_review.png`（上面人工认可74号，下面未评价K4S079），`review_figures/K4S_079_unlabeled_5panel.png`，`top_unlabeled_01_to_09.png`/10_to_18.png、`priority_18_manual_review_blank.csv`（18个尺度敏感候选按人工真实/轮廓/误合并评价，空白未自动标注）、`240_scale_trial_audit.csv`、`summary.json`、`CASE03K4_REPORT.md`。
- K4原始结果`outputs/case03k_expanded_validation/run_20261012_new_J5_objects_K3_frozen_v1`有60张5panel、5张contact、48个源掩膜NPZ、`all_60_audit.csv`、`manual_review_template.csv`。独立QA `K4_ALL_QA_PASS`核对60个区域的分层及J5归属、48个现有对象掩膜守恒、60张PNG和5张contact可解码；K4S 240来源不重复、22尺度预筛、1暂定候选、18优先复核图可解码。全工程pytest **215 passed**。
- 26号第二帧 RAW `26 (2).raw`（207,478,400 bytes）已存在，但至今没有第二帧独立J5及真值，也不能假设与第一帧目标一一对齐。故**这只是在原第一帧未用于调参对象上的扩大探索，尚未完成独立帧/独立样本的人工验证，不得部署J5全图正式轮廓或改产品判定**。
- 下一个用户动作：优先看`074_versus_K4S079_side_by_side_review.png`，回答K4S_079是否真实暗斑和青色179px²边界是否基本完整。再看`priority_18_manual_review_blank.csv`中其他对象，进一步决策是否有条件集成K3，或者应优化轮廓边界方法。

## 2026-10-12 K4S_079人工评价“179px轮廓覆盖约70%”之后的扩展诊断
- 用户检查K4S_079后说“覆盖了70%，相比之前有一点效果”。这是**肉眼目测覆盖**，不等于严格标定IoU/物理面积；K4S_079是否实际真疵病未单独确认为真值，仍为未正式验证候选。
- 已执行`scripts/diagnose_case03k4b_079_boundary.py`：冻住K3 RAW局部背景模型、alpha、种子及竞争对象掩膜，改变噪声约束3σ、2σ、1.5σ，对应K4S_079试验候选179、272、314px²；因3σ主导，单降alpha15→10→5%面积不变。新两档没有碰到其他J5源、亦未触径向上限，**仍不意味着外围物理正确或无背景噪声**。
- K4c完整门控复核旧已人工判断24候选：3σ、2σ、1.5σ下都只有真实大暗斑74号生成候选1203px²；19目视噪声和4弱真微点都不自动扩展。**全为参与开发的样本，不能外推泛化**；新079仍需用户评价。
- 用户优先看`outputs/case03k_expanded_validation/run_20261012_240_green_scale_sensitivity_v1/K4b_079_outer_boundary_sensitivity_v1/K4S079_compare_179_272_314_for_manual_review.png`，四栏同RAW比较；详细`CASE03K4B_DIAGNOSTIC_REPORT.md`、`sensitivity_audit.csv`、NPZ；代码`scripts/build_case03k4b_manual_comparison.py`和`scripts/analyze_case03k4c_noise_floor_control.py`。**不更改J5源掩膜/170-230/CASE03-H/尺寸等级，也不默认1.5σ进入生产**。

## 2026-10-12 Case03-K5：用户要求重点解决局部噪声自适应阈值+同一暗斑的J5多连通域一票否决

- 已在远程设备Lixx`D:\疵病检测\DefectDetectionProject`实现研究性K5，不覆盖旧Case03-H/J4/J5原掩膜、固定170/230阈值、全局ID或正式面积等级。
- 代码新模块`src/detection/case03k5_adaptive_grouping.py`（局部噪声门限k=3/2/1.5倍MADσ响应、预定轮廓稳定性和放宽安全条件、全J5来源ID像素级兄弟碎片归属、显式待复核显示状态）、脚本`scripts/run_case03k5_adaptive_group_pilot.py`、`scripts/verify_case03k5_outputs.py`、8个`tests/test_case03k5_adaptive_grouping.py`测试。`223 passed`全工程pytest通过；独立QA`K5_INDEPENDENT_QA`通过，每个原检测像素保留、全部PNG真实可读。
- K5独立结果目录`outputs/case03k_adaptive_group_trial/run_20261012_K5_adaptive_and_J5_group_review_v2`，最重要：`K5_focus_024_057_086_079_074.png`；单体`K4S_024_review_focus.png`,`K4S_057_review_focus.png`,`K4S_086_review_focus.png`,`K4S_079_review_focus.png`,`K0_SMALL_074_review_focus.png`；`review_figures/`23张六栏、`reversible_masks/`23份NPZ、`k5_23_case_adaptive_and_group_audit.csv`、`provisional_group_membership_review.json`、`deduplicated_group_review.json`、人工空表`deduplicated_group_review_blank.csv`、完整`CASE03K5_README.md`。
- 选择RAW噪声底限时，不再固定k3，只有初始RAW面积相对H61太小(<=1.8)、k2到k1.5面积增长稳定(<=1.22)、相对k3面积增长不超过2.5且满足源覆盖/裁剪条件才选择k1.5。K4S_079**179→314px²，k1.5**（此前用户认为314更完整）；开发参考074保持k3=1203px²。K4S_024 725→1301px²、057 139→231、086保持493。这些都是**未人工确认的试验性RAW视觉轮廓**，不是物理真面积。
- J5竞争对象审查改为像素级：从J4.tile labels及J5.global_object_membership准确还原每个原始J5全局ID，判定共同RAW连通候选是否几乎完整覆盖其他小碎片(>=85%各自全部源面积)、单碎片面积<=160px²、最多8个、候选非长条/未截断、源像素总面积占候选<=30%。符合者`COHERENT_GROUP_REVIEW`，**仅待人工确认同一物理黑斑**。不符合也显示黄色待复核候选和拒绝原因而非只回退红点，但绝不自动合并J5或把新面积算正式分级。
- 23个测试（先前未用于K3门限开发的22个K4S预筛候选+开发参考074）有7条“同一斑点碎片”预审提案，按完全相同J5来源ID集合去重后为**6组**。K4S_024涉及旧`DEFECT_11170`及其他4个，显示1301px²黄色轮廓；057涉及2个，显示231；086涉及5个，显示493；旧182和200两次提案为同一组三个J5成员，其两种RAW候选在全局坐标IoU=0.95133，统一去重成一条人工复核组，保留2种候选形状。这些不是新“真实疵病组”也未修改原有编号。
- **关键限制**：本轮阈值判据显然受74/079已有用户视觉反馈启发，属于开发集方法；K4S的22处未有全部人工物理轮廓，更未在26号第2帧独立验证，不能声称泛化或报告Precision/Recall。用户尚未确认新024/057/086轮廓是否过度包含背景/是否同一物理黑斑。K4S_055不是22个形态预筛通过的对象，原H61 5→6像素，不能用本版冲突归属方法直接解决。后续先人工核对`K5_focus_024_057_086_079_074.png`与6组CSV，再考虑独立帧验证和J5正式集成。

## 2026-10-12 Case03-K6：26号第二帧独立RAW全图检测与冻结K5试验已实际执行

- 用户在第一帧K5的024/057/086等多J5关联试验视觉判定“这一次都正常了”后，同意按建议在`26 (2).raw`独立验证。已连接远程`Lixx`，数据在`D:\疵病检测\疵病实测数据\260624批次表观（5片）\26 (2).raw`。与26(1)图片不假定已配准；两帧J5编号不能一一对应、第一帧人工ROI不能套用到第二帧。
- 新`scripts/build_case03k6_frame2_blackhat.py`用512px核心、halo32px重算第二帧精确五尺度3/5/9/15/31 BlackHat最大融合，输出`outputs/case03k6_frame2_fused_blackhat/run_20261012_frame26_2_frozen_kernels_v1/frame26_2_fused_blackhat_exact.npy`（207MB）。同一分块法在第一帧5个随机/边缘位置和冻结原Case02全幅BH逐像素差值**0DN**。原始RAW只读。
- 旧J4/J5脚本补充可选新RAW、新Fused NPY、新J4路径及`frame_label`，原第一帧默认保持。第二帧J4已**1620/1620**分块完成，4511个分块局部候选，来源`outputs/case03j4_fullframe/run_20261012_frame26_2_J4_independent_v1`。第二帧J5`outputs/case03j5_global/run_20261012_frame26_2_J5_independent_v1`完成**4440个全图疑似对象**（SMALL4215、MEDIUM119、LARGE106），原检测面积总**123659px²** J4→J5守恒；全图对象编号、原掩膜来源完全是第二帧，不引用第一帧。
- J5原始第二帧分级显示主/辅图：`outputs/case03j5_global/run_20261012_frame26_2_J5_independent_v1/second_frame_separate_size_views_v1/medium_large_main.png`（中大225个，工程主图）；`small_reference.png`（绿色4215，人工参考图），两份CSV同步、同RAW背景/坐标/比例、不修改正式J5。
- 新`scripts/run_case03k6_second_frame_K5.py`按固定种子20263614、空间与源面积分层，**不看第一帧任何人工标签**从第二帧J5抽264个源对象：SMALL 1px²24、2-3px²24、4-7px²72、8-39px²120、MEDIUM12、LARGE12；另外抽24个无J5任何显示bbox的128ROI用于人工潜在漏检核查（未确认为无疵病），共288。冻结K5参数（BH61、H170/230、RAW外围MADσ自适应k3/2/1.5、对象归属审计），K5仅用于研究性试验候选，不改变J5。
- 264例中严格的BH61面积/方向/扩展倍率形态预筛**13**例，7例生成非空RAW外围，**5个**可展示多对象碎片共同轮廓提案`GROUP_OUTER_PENDING_HUMAN_REVIEW`，另2个`REJECTED_HALO_DISPLAY_REVIEW_ONLY`（仍可显示审查但无法通过全部安全条件）；2例选k1.5。注意早期摘要文件`summary.json`中`frozen_K5_new_spot_shape_prechecks:27`仅计BH61面积>=60的数量，不能当完整预筛；准确完整预筛是**13**，由独立QA确认。5组只是提案且没有用户人工真实性评价，本轮0处自动生产合并。结果`outputs/case03k6_frame2_independent/run_20261012_frame26_2_frozen_K5_v1/`：重点`selected_6panel_labeled_top_7.png`、`all_288_frozen_K5_audit.csv`、`fixed_selection_and_blank_manual_review.csv`、`reversible_mask_audit_top7/`中的7个mask逐像素重算及人工复核CSV、`CASE03K6_VALIDATION_REPORT.md`。
- 两帧数据灰度对比在同一1:8像素采样下：RAW灰度中位**第一帧993DN vs 第二帧793DN**；BH反应>=230DN的比例**0.1084% vs 0.0435%**；J5总疑似对象**15604 vs 4440**。高阈值响应显著下降与固定170/230跨帧候选减少相符，**可能存在亮度或拍摄条件造成漏检的风险**，但未有人工作全图真值、不能据此称任何一帧检测准确率更高，更不能悄悄改变170/230。
- 新`scripts/verify_case03k6_independent_second_frame.py`**完整QA通过**：J4 tile覆盖1620，J5 id4440唯一、全源面积123659守恒、从第二帧J4原NPZ逐像素重建264样本的J5源对象正确、24个“无预测ROI”与任何J5显示bbox零重叠、全部人工标注字段空、29张K6来源PNG/组图实际可解码。另7例由`scripts/archive_case03k6_7_proposals.py`独立重算源mask/H31/H61/k3 RAW/K5外轮廓，与审计像素数逐一匹配、保存可逆NPZ和审计。全工程pytest**223 passed**。
- 尚未完成：第二帧独立人工真假标签/精确轮廓标注，不能报告Precision/Recall/IoU；K5只在264个新J5对象上试验，并非全图4440个K5精修；没有在第二帧生产数据上合并任何J5 ID/升级尺寸。后续首先请用户查看7例`selected_6panel_labeled_top_7.png`及`seven_new_outlines_manual_review_blank.csv`，确认是否真实疵病、黄色整体轮廓是否完整、相邻红点是否同一疵病；另复核部分24个无J5候选ROI是否真实漏检。若确认跨帧误检/漏检情况，则再考虑是否推进全图K5及主阈值自适应。

## 2026-10-12 K6_190：第二帧用户截图的“暗斑没识别”根因已经查明
- 用户显示`K6_190_6panel.png`：左侧明显纵向暗斑、J5小红核心位于右侧，BH61 406px²、RAW k3/adaptive0，final仅15px²。**注意这是以右侧SMALL`DEFECT_02917`15px²为中心的局部单对象复核图，左侧大暗斑**其实J5早已检出，ID为**`DEFECT_02914`**，GRADE LARGE，**1646px²**，源bbox global x8195-8234 y8033-8100（小02917 bbox x8250-8255 y8067-8073），二者bbox横向相距15px。用户截图造成的“漏掉左侧斑点”是ROI显示没标注其他J5来源对象，并非J5整体没检出。
- 对原第二帧`26 (2).raw`直接逐像素追查（ROI global[8189,8006,8317,8134]）：RAW残差在3MAD噪声阈值约96.05DN下，左侧约740px²与右侧J5 02917源mask交集0，故锚定RAW返回0；即使1.5MAD主左斑约1041px²也不连种子，只在右侧出13px²小组件。与原02917为不同位置、不同J5 ID，不应以降低阈值或跨背景强行合并解决。
- 新只读脚本`scripts/diagnose_case03k6_190_source_and_dark.py`，修正展示`scripts/build_case03k6_190_two_J5_review.py`，重要用户图`outputs/case03k6_frame2_independent/run_20261012_frame26_2_frozen_K5_v1/K6_190_seed_geometry_diagnostic_v1/K6_190_CORRECTED_TWO_J5_OBJECTS_4panel.png`：原RAW、绿色1646px² LARGE 02914、红色15px² SMALL 02917、两对象联合叠加，明确**J5未合并ID**。另8pane详图、诊断JSON、可复算NPZ和`CASE03K6_190_DIAGNOSIS.md`。PNG已查看，未动任何正式数据。
- **重要后续**：单对象K5六栏展示应补充同一ROI内其他已检测J5 ID的异色轮廓与大小说明，防止类似的视觉漏识别假象；右侧15px对象是否真实疵病仍需人工判断，不能先自认噪声或并入左侧。此例不需要调K5阈值。

## 2026-10-12 Case03-K7：两帧细线标注与探测器像面3.2μm尺寸导出已完成
- 用户要求“标注线条细些，之前未标注大小，先按探测器像元尺寸计算”，明确配置`config/user_config.py: PIXEL_SIZE_UM=3.2`。工程`CASE03E_OBJECT_PLANE_UM_PER_PIXEL=None`，因此仅称**探测器像面等效尺寸**，不自动作为样品物面真值。原J5有效源像素`Aμm²=Npx*10.24`；`maxFeretμm=Lpx*3.2`；bbox宽高同乘3.2，桥接推断像素不计面积。现有SMALL/MEDIUM/LARGE面积+长度分级不变。
- 新代码`scripts/run_case03k7_physical_annotations.py`与`scripts/export_case03k7_K5_review_dimensions.py`，QA`scripts/verify_case03k7_annotations.py`。最新**v2**目录`outputs/case03k7_detector_size_annotations/run_20261012_dualframe_thin_line_3p2um_v2`，不覆盖v1；项目总报告`CASE03K7_REPORT.md`。
- `frame26_1`共J5 15604,中大720、小14884；`frame26_2`共J5 4440,中大225、小4215。每帧有`medium_large_thin_1px.png`（所有中大框1显示像素、1:4相同原点）、`medium_large_with_detector_sizes_um.png`（重点数字标签，第一帧133个、第二帧129个，根据ID可查全量CSV）、`small_reference_thin_1px.png`（绿色小候选单显示像素），及`large_medium_gallery_01_to_12.png`等3张局部图册（每帧Top36原J4 source mask精确还原，经过预览缩放后1显示像素细轮廓）。`all_J5_objects_detector_sizes_um.csv`、`medium_large_sizes_um.csv`、`small_reference_sizes_um.csv`为所有原J5 ID全量等效面积/长度，单位与限制明确。
- K5试验外围**绝对不可与J5源实测面积混合**：每帧`K5_estimated_contour_sizes_FOR_REVIEW_ONLY.csv`保存K5试验估计面积（第一帧23行、第二帧7行），另目录`K5_provisional_sizes_separate`将非空K5 ROI按`RAW | FROZEN J5(red L/A) | K5 OUTER review(amber L~/A~)`三个面板展示并写辅助CSV；第一帧13幅，第二帧7幅，重点`frame26_2/K5_provisional_sizes_separate/K6_084_size_3panel.png`。
- 软件核查：独立`K7_DETECTOR_SCALE_AND_IMAGE_QA_PASS`逐条核对首帧15604和次帧4440个J5原ID/面积/等级完全一致，严格3.2换算；第一帧、第二帧各36张gallery对象均自原J4精确还原并源像素守恒，PNG实际可解码；全工程`223 passed`。**不更新原始J4/J5/H170/230/K5源、等级、真实疵病判定，也没有完成误检/漏检真值评价**。

## 2026-10-13 Case03-K8-A：用户明确波段数量可变，已真实完成两帧自动分带与独立掩膜
- 用户指出滤光片工作波段并非恒为4，可能为5，要求先做K8-A（只定位、掩膜；暂不独立黑顶帽/阈值检测）。已完成`src/detection/case03k8a_band_locator.py`、`scripts/run_case03k8a_variable_band_masks.py`、`scripts/verify_case03k8a_masks.py`、`tests/test_case03k8a_band_locator.py`。算法在每帧RAW DN行中位曲线中检测同时由两侧低DN遮光谷围住的峰值，按局部峰-谷亮差识别灰度偏低的工作波段，排除高亮的上下非工作区；每带30个X位置鲁棒拟合上下倾斜边界；上/下边界内收12px以保留待复核边缘，横向内收24px；**不固定波段数、无任何第一帧固定坐标复用到第二帧**。
- 两帧实际RAW各找到**4条**内部工作波段；峰行号26(1):2916/4684/5608/6672；26(2):2380/4152/5088/6148；按4个band真实WORK区域灰度中位DN26(1):1706/330/1029/1117，26(2):1474/300/898/976；暗透过波段2不会因全局高门限而遗漏。NON_WORK上下界26(1) y1748/7852；26(2) y1220/7324。两帧原坐标WORK mask未经配准IoU约0.1513，反映不能复用固定分区，不是算法精度。
- **仅推荐v2**：`outputs/case03k8a_auto_workband_masks/run_20261013_26twoframes_variableband_v2`，每帧`frame26_1`/`frame26_2`下优先检查`work_band_overlay_on_RAW.png`、`region_codes_preview.png`、`row_band_profile.png`；全分辨率`band_id_fullres.png`含0背景及1..N工作带ID；`region_type_fullres.png`包含0非工作、1遮光、2工作内芯、3工作带边缘待复核；`band_01_core_fullres.png`等二值mask，`band_geometry_and_DN_statistics.csv`、`audit.json`记录几何/DN和人工确认空栏。根目录`CASE03K8A_REPORT.md`、`independent_mask_QA.json`。
- 真实两帧原11276×9200 mask已完整导出PNG且逐像素解码一致。合成5波段不同灰度图单元测试自动输出5条；4波段输出4条，平移重计算独立mask。测试**K8A_INDEPENDENT_MASK_QA_PASS**；全工程**228 passed**。**人工边界还未正式确认**，程序未声称真实5波段样品已通过，5条仅合成可变数量验证。
- 此阶段严禁改170/230、BlackHat尺度、J4/J5官方疵病来源ID/面积、K5轮廓和正式物理质量结果，尚未进行K8-B的分带检测/筛噪。用户接下来先看两帧叠加图（尤其弱灰度第2带、斜边界及遮光带附近），认可后再考虑K8-B的每波段独立背景/黑顶帽对照。
- 仅供追溯：旧K8-A v1第一帧完整但在最后统计打印时因numpy.uint8 JSON键出错终止，v2在新run目录从头完整生成两帧，旧结果未覆盖。

## 2026-10-13 Case03-K8-B：K8-A用户确认“准确”后已独立运行分波段双阈值候选对照
- 用户已明确K8-A两帧动态4波段几何定位“准确”，但滤光片物理上可能4或5波段。K8-B结果**不固定4**，读取各帧K8A`band_id_fullres.png`和独立阈值统计；仅在K8-A`WORK_CORE`内提候选，不改源J5/G/H/K5/RAW。
- 新模块`src/detection/case03k8b_perband_trial.py`、脚本`scripts/diagnose_case03k8b_perband_dn.py`,`scripts/run_case03k8b_bandwise_thresholds.py`,`scripts/build_case03k8b_band2_review_gallery.py`,`scripts/verify_case03k8b_trials.py`,8项`tests/test_case03k8b_perband_trial.py`。最新**v2**目录`outputs/case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2`（旧v1文字错误A面板显示了B阈值,已独立重跑v2;不覆盖）。
- 两帧各4工作带按原RAW+32px halo重新计算全宽每带3/5/9/15/31椭圆BlackHat最大融合,与原全幅响应在WORK_CORE**逐像素0DN**，因此分带本身同核不改BH值；修改影响来自后面候选阈值。固定A为每带H170/230低、高双阈值8连通；实验B为最高RAW工作带的融合BH中位数+1.4826MAD中旧170/230对应标准化Z，向各其他工作带转移，并不使用人工标签。这是**纯H候选对照，没有完整重新运行旧G/H/J4/J5分类与拼接**，禁止用候选数量宣称已提高检测准确率。
- 试验B各波段低/高DN：首帧B1=170/230、B2=64.71/87.00、B3=128.43/173、B4=134.43/179；次帧B1=170/230、B2=64.25/86.75、B3=128.50/173.50、B4=134.50/179.50。第二帧A固定4带候选连通域分别515/0/2/11，B实验515/1483/770/1124；第二帧B2新增1483个连通候选，**1402个仅1～2像素**,81个≥3像素、10个≥10像素；巨量碎噪候选不得直接纳入正式疵病！用户尚未评价新增B2候选真伪。
- 对冻结J5全部候选仅按对象中心定位到分区: 首帧NONWORK=14829 SHIELD=88 WORK_CORE=683 EDGE=4，总15604；次帧NONWORK=4037 SHIELD=5 WORK_CORE=398 EDGE=0，总4440。这是用户此前“大部分疵病候选来自非工作区”的量化支持，但**中心判定无法解决跨工作区边界对象完整归属**，不能当正式验收。未改J5原源mask与分级。
- 第二帧`frame26_2/B_robustZ_perband_workband_overview.png`及`A_fixed_170_230_workband_overview.png`和`B_new_vs_A_fixed_overview.png`同原RAW坐标对比; `frame26_2/band_02_4panel_RAW_BH_A_B.png`看暗波段原RAW、BlackHat、固定/自适应4面板；**优先看**`frame26_2/band02_candidate_review_atlas/band2_top12_by_area_12patches_RAW_B_candidate.png`前12较大候选, 和`band2_tiny12_deterministic_12patches_RAW_B_candidate.png`12微小候选；其中有明显暗斑也有疑似背景噪声/靠遮光边界条带，局部CSV含RAW相对灰度和MAD z，但人工真伪字段未填写。
- `independent_trial_QA.json`逐像素验证两帧A/B二值PNG、阈值、区域不越界、原BH同核0DN、源J5完整、24个Band2局部候选/帧人工字段空，**K8B_INDEPENDENT_QA_PASS**；全工程**236 passed**。另提供`trial_candidate_size_and_edge_risk_audit.csv`记录1～2、≥3、≥10px候选和距K8-A内芯边界32px伪响应风险（不自动删除）。
- 每帧所有4带原分辨率Y裁剪二值候选图`band_XX_A_hysteresis_mask_cropped.png`、`band_XX_B_hysteresis_mask_cropped.png`及其全局Y裁剪坐标在`summary.json: ROI_crops`；`perband_comparison_and_thresholds.csv`保存统计, 根目录`CASE03K8B_REPORT.md`全面记录对照。
- **重要结论**：当前B分带阈值可释放固定170/230在暗工作带近乎无法检测的灰度下降响应，但会带来大量噪声；未经用户标注审查、经过可逆RAW局部对比度+面积+空间形态+边界风险筛除和独立真值验证前**不能上生产**或更新J5/K5。后续可考虑独立K8-C筛噪，但需用户审查上述新图后决定。

## 2026-10-13 Case03-K8-C：用户确认K8B新增较大候选是暗斑，已完成两帧全部工作带的可逆噪声分层和主图集成

- 原K8A已用户认可定位准确，原K8B每带分段双阈值B是H候选不是J5，用户看`frame26_2/band02_candidate_review_atlas/band2_top12_by_area_12patches_RAW_B_candidate.png`表示“属于暗斑”，随后同意K8-C。
- K8-C真正写入且执行的代码：`src/detection/case03k8c_noise_review.py`（K8CConfig、RAW局部环带背景/中位灰度差/MAD稳健z/DoG暗核P90、带边32px待复核、原固定A重叠保留、≤2px微噪仅建议隐藏、>=3不直接硬删除），`scripts/run_case03k8c_band_supplement_review.py`（既有B二值连通对象归档全部每个原label、不看任何人工标签评估、逐帧带状态分掩膜及raw画册），`scripts/build_case03k8c_J5_workplus_supplement_views.py`（原冻结J5仅WORK工作区对象/新增strong候选/联合主图/疑似待复核/1–2px微点建议隐藏5张主图），`scripts/verify_case03k8c_band_triage.py`（逐像素掩膜并集完备且互斥的QA），`tests/test_case03k8c_noise_review.py`（10例单元测试）。
- **只推荐最新v2**`outputs/case03k8c_band_supplement_review/run_20261013_f1_f2_allbands_reversible_v2`，根`CASE03K8C_REPORT.md`为完整报告。`frame26_2/03_J5_WORK_plus_K8C_provisional_supplements.png`是当前最重要的合成主图：旧J5工作区按RED/YELLOW/GREEN的原大小等级标注,新`PROMISING_DARK_REVIEW`用青色细框和B#-ID；`01_frozen_J5_WORK_only.png`旧J5工作区主图；`02_K8C_promising_supplement_ONLY.png`新增值得看暗斑；`04_uncertain_boundary_and_micro_review.png`待复核；`05_micro_1to2px_HIDE_SUGGESTION_only.png`小微点建议隐藏附件。用户还应看`frame26_2/band02/review_large12_RAW_vs_K8C_outline.png`，这12幅新版局部RAW轮廓图含全部原K8-B面积最大候选、各状态及RAW z、DoG。
- 一帧 K8B B连通候选16766，其中固定A重叠B对象3008（原A独立对象3009，B降阈后合并两A对象变成一个）、真正与A完全不交的B候选13758。K8C建议RAW支持较强的暗斑13个，≤2px微点建议主图隐藏11524个，其他新增未明确的留待复核2221个。冻结J5只有683个对象中心在K8A WORK_CORE。
- 二帧 K8B B连通候选3892，其中A已检H对象528、新B候选3364；RAW暗度+MAD+DoG支持较强13个（B2 6 / B3 2 / B4 5）、1–2px建议主图隐藏3168个、其他新增需要复核183个。冻结原J5 398个对象中心在WORK_CORE。**不同于正式J5对象统计：K8B A只是H双阈值候选比较，不能混称为J5检测。**
- 用户此前确认的**第二帧B2前12大候选**在不看人工标签计算状态后回溯分类：6`PROMISING_DARK_REVIEW`，4`BOUNDARY_REVIEW`，1`UNCERTAIN_REVIEW`，1`MICRO_REVIEW`，**0建议隐藏**。用户确认仅适用**第二帧**，不能把第一帧B2前12也标成人工真值。最新v2修正了早期v1这一范围错误。后续不应对已有12个肉眼确认暗斑的弱区直接删除，而是保留待审。
- 每帧`K8C_per_band_review_summary.csv`、`all_K8B_candidate_objects_complete_K8C_audit.csv`逐个候选位置/原B label/面积/RAW相对灰度/MAD z/DoG/距工作带边界状态及理由，三类二值原工作带Y裁剪掩膜`band##/K8C_promising_raw_supported_mask.png`、`K8C_uncertain_or_fixedH_review_mask.png`、`K8C_micro_suggest_hide_mask.png`，逐像素或等于原K8B B而互不重叠，所有原B像素保留，没有真删除。第二帧回溯人工记录`frame26_2/band02_user_reviewed_12_POSTHOC_only.csv`但候选门控全程不读标签。
- 实际检查过第二帧`03_J5_WORK_plus_K8C_provisional_supplements.png`（同原RAW坐标1:8,细框，不用跨帧图像错误配准）和`band02/review_large12_RAW_vs_K8C_outline.png`（12幅左原RAW右细黄色轮廓，前5强暗斑、后若干波段边缘及微小暗斑，保护待审）。`K8C_INDEPENDENT_QA_PASS`（每帧12原全分辨率三类掩膜合并/源数字关系、全部图实际可解码、旧J5数量不变、仅第二帧做用户参考映射）、全工程pytest**246 passed**。
- 尚未完成正式整图K8C补漏合并J5、跨波段复杂轮廓修复、已人工标定真实缺陷面积、Precision/Recall、合格率。应先让用户看第二帧J5_WORK+K8C合成主图以及B2前12暗斑是否接受“6强支持+6待复核”的保守分层；不要因为显示上3168小点隐藏建议就误报3168处真噪声。

## 2026-10-13：用户发现K8-C局部图只圈暗核、线宽及中大优先展示，新K5 RAW轮廓试验已执行
- 用户看`frame26_2/band02/review_large12_RAW_vs_K8C_outline.png`（截图），判断可检出暗斑但**黄色轮廓不覆盖完整RAW灰度下降区**，明确要求**优先展示中、大疵病，小候选单独参考**，询问是否原K5完整轮廓算法已调用。根因：此前K8-C只筛分类别和显示K8-B H低阈值源候选，**未使用K5 RAW轮廓修复**。
- 新代码`scripts/run_case03k8c_K5raw_outer_contour_pilot.py`真实**复用**`src/detection/case03k3_spot_contour_pilot.py:raw_outer_envelope`（局部RAW 128 ROI、鲁棒环带平面拟合、3/2/1.5MAD受限扩展）。区别是种子是K8-B分波段低阈值H候选**不是**原J5 H170/230+BH61，不能照搬完整K5 BH种子限制；因此叫K5RAW复用**试验**而非正式重跑K5。用mask保护跨工作边界、种子保留、增长倍率/径向界/其它B候选冲突。原J5/K5/K8B/K8C都不修改，所有mask和RAW省份字节数据不丢。
- 新结果**`outputs/case03k8c_outlines_prioritized/run_20261013_K5RAW_contour_expansion_pilot_v1`**，根`CASE03K8C_OUTER_PRIORITIZED_REPORT.md`及独立QA。每帧`frame26_X`：`01_PRIORITY_original_J5_MED_LARGE.png`原J5只工作带中大；**`02_PRIORITY_J5_MED_LARGE_plus_K5RAW_review_OUTER.png`**优先看，新旧中大+受限RAW扩大轮廓青色、1显示像素，原J5绿色小候选隐藏；`03_K5RAW_expanded_contours_only_MED_LARGE.png`仅建议扩展；`04_REVIEW_safety_rejected_raw_outer_candidates.png`橙色未通过安全门控的RAW外围不纳正式；`05_SMALL_original_J5_and_K8C_reference.png`原J5小疵病+K8C新增小候选独立。冻结原J5 WORK中大：首帧25、次帧26；小候选原J5分别658、372。
- 每个轮廓对比6栏原RAW/原B掩膜/k3/k2/k1.5/安全建议，单独可逆NPZ及CSV中包含原B和建议面积/最大Feret转换(3.2μm/px仅探测器**像面当量**)、拒绝原因、不改变原ID/Grade。先验选择两帧K8C强RAW暗区13+13，另外第二帧B2用户看到的12候选去重，因此总首帧13、次帧19个。
- **实际扩展第二帧4个/19**：B2候选705原474→安全RAW621 px²、544原359→427 px²（RAW420加原B边缘）、264原151→392 px²；B4候选183原97→281px²。第一帧13个候选**0个通过当前安全门控**，不能报全面成功。B2候选1161/1148/626 RAW各自可以提出更大面积(如626原34→RAW k3=273,k2=323,k1.5=348)，但增长超限且与其他B分段冲突，**当前未采用**；后续需要恢复历史“多个连通分量属于同一暗斑”的关联复核，防止假合并和跨工作带边界。
- 重点图片**`frame26_2/02_PRIORITY_J5_MED_LARGE_plus_K5RAW_review_OUTER.png`**已经真实打开检查并细线标注。另`frame26_2/band02/F2_B2_C00705_six_panel.png`、`F2_B2_C00264_six_panel.png`（部分外轮廓恢复明显）、`F2_B2_C00626_six_panel.png`（显示RAW有候选但安全回退到原B）已实际读图检查。
- `scripts/build_case03k8c_prioritized_K5RAW_views.py`、`scripts/verify_case03k8c_K5raw_priority.py`新建，QA逐个32个trial检测原B面积、source联合后完全不丢、受限外轮廓不越K8A CORE、所有PNG真实解码、原J5 WORK中大小统计保持25/26，**K8C_RAW_PRIORITIZED_QA_PASS**，全工程pytest**246 passed**。本次没有正式合并/重分级/替换J5、没有定量漏检率验收。

## 2026-10-14 Case03-K8D｜1148/626等暗斑“RAW外围已出，但最终安全检查回退小种子”已真实修复
- 设备Lixx重新连接成功，已不止提供修复包：实际直接写原工程的新代码`src/detection/case03k8d_group_stability.py`、`scripts/run_case03k8d_grouped_raw_contours.py`、`scripts/verify_case03k8d_real_masks.py`、`scripts/build_case03k8d_4target_regression_sheet.py`、`tests/test_case03k8d_group_stability.py`。保留旧K8C/K5/J5/B/H数据不变（新文件、新run）。
- 核心修复：不把原B种子小面积的`RAW/seed>5`直接当成硬拒绝；验证真实3MAD种子重合度/工作带边界/最大面积/形状/ROI及径向裁剪，再逐级审查3→2→1.5MAD阈值形状嵌套和面积增长稳定性；计算被RAW外围覆盖的其他B连接分量的**完整原分量面积**，>=80%包含才提示关联，不自动合并J5/B IDs。竞争/越界只能橙色**完整外围待复核**，原3MAD完全无可靠锚则保留原小种子，不放行弱阈值爆发。
- 本轮真实两帧结果唯一推荐**`outputs/case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3`**。早期v1/v2先验RAW centroid取整差异曾中断，v3严格采用原K8C记录的OpenCV质心3位小数复现相同K3 RAW三档掩膜，所有32候选的源B/3档RAW与旧K8C逐像素一致。`CASE03K8D_REAL_RAW_REGRESSION_REPORT.md`汇总全部逻辑、数据与输出。
- 用户重点第二帧B2回退例真实验收：**1148原48→新369px²**（RAW3/2/1.5=317/353/369），**1161原64→新370px²**（314/353/370），**626原34→新348px²**（273/323/348），三者都不再退回小种子；**1483原12→新12px²**，因为RAW3/2无可靠锚、1.5MAD爆发1746px²不能放行。1148和1161相互包含其他B源（另有1186），两个完整轮廓高度重合，显示级以一个**橙色关联待复核**区域展示，不重复当作两个已确认疵病；原B label1148和1161独立保留。626与B2另一个658候选拟关联，待人工确认，不正式合并。
- 用户优先看**`frame26_2/K8D_REGRESSION_4TARGET_OLD_VS_NEW.png`**，4行1148/1161/626/1483，4列RAW/原B源/旧Safety最后一栏/新K8D最后一栏，真实图片已打开检查，新最后一栏前三个明显扩大并覆盖暗斑，而1483被拦截。另`frame26_2/band02/F2_B2_C01148_K8D_six_panel.png`、`F2_B2_C00626_K8D_six_panel.png`、`frame26_2/02_J5_MED_LARGE_plus_STABLE_K8D.png`、`03_ALL_REPAIRED_FULL_OUTERS.png`及`04_AMBIGUOUS_NO_SHRINK_OUTERS.png`，中大优先主图，微小对象未挤入。`all_K8D_original_vs_outer_review.csv`、`deduplicated_review_groups_NO_official_merge.csv`以及32个可逆128px NPZ完整保留。
- 双帧候选数首帧13、第二帧19；扩大RAW建议首帧10、第二帧11；中大主图稳定建议首帧7、第二帧9；完整橙色冲突审查首帧3、第二帧1，均是候选/显示组**非真实疵病量或测量验收值**；原J5工作区中大25/26不变。
- 独立实测`K8D_REAL_PIXEL_EXACT_QA_PASS`，11项新增合成单测+**全工程257 passed（94.29s）**，原J5/G/H/K5/K8B/K8C原mask/ID未修改、像面3.2μm仍非经倍率标定的物面真实尺寸。此阶段解决的是“算法不合理回退小红种子”的代码逻辑，不代表已盲测真实轮廓误差或能把候选自动计为正式缺陷。

## 2026-10-14 Case03-K8E：双帧多连通域“统一显示、不重复算面积”的真实实现已完成
- 在用户要求“继续”后，已直接在Lixx Windows工程中新增`src/detection/case03k8e_group_hypothesis.py`、`scripts/run_case03k8e_exact_union_review.py`、`scripts/verify_case03k8e_exact_union.py`、`tests/test_case03k8e_group_hypothesis.py`。源J5/GH/K5/K8B/K8C/K8D文件均未改；新run只保存显示组、真实像素并集mask、人工审核表与PNG。
- **新结果唯一目录**`outputs/case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1`，根`CASE03_K8E_REPORT.md`完整技术方法及注意事项。两帧K8D输入13/19候选外围，实际K8E显示组13/18；次帧分组后面积总和从K8D候选外轮廓直接相加4950px²减少为逐组像素并集4581px²，**去除369px²重复覆盖**（这个是本次研究候选区域的面积去重，不是全图真实疵病面积统计）；首帧不重复13组14570px²。原J5 WORK中大仍25/26。
- 核心B2-1148和1161：同一RAW 128px范围，独立完整RAW轮廓369/370px²，交叠369px²、IoU99.73%，来源种子48/64px²；今次`K8E_F2_B2_G009`把两个提议轮廓**在原RAW像素XY坐标上真正OR并集**，**唯一面积370px²，而非739px²**。同一RAW外围完整包含第三B小种子1186（原3px²），只作为待审嵌入源。正式J5/B IDs不合并，组ID只用于审核和显示。
- B2-626与B2-658：`K8E_F2_B2_G006`，626完整RAW外围348px²，658旧B只有6px²且100%被外围包含；标`EMBEDDED_B_SOURCE_REVIEW`证据比两个独立RAW外轮廓相互重合的G009低，人工待确认，不增加额外外围面积。B2-1483继续保留12px²且不进入中大主图，避免1.5MAD大面积误扩张。
- **重点图路径**`frame26_2/02_PRIORITY_J5_MEDLARGE_plus_K8E_GROUPED_REVIEW.png`旧J5 WORK中大为原红/黄、K8E新增中大青色单源/橙色多分段关联待复核，小点独立在`06_SMALL_SOURCE_REFERENCE_UNCHANGED.png`；`frame26_2/group_detail/K8E_F2_B2_G009_RAW_sources_exact_union.png`显示1148/1161/1186来源，`.../K8E_F2_B2_G006_RAW_sources_exact_union.png`显示626/658，4栏原RAW、不同B原种子、完整RAW轮廓、统一OR外围；PNG已读图检查。每个组有`K8E_..._EXACT_GROUP_MASK.npz`原像素XY/种子来源及标签，`K8E_unique_group_union_measurements.csv`及`K8E_source_member_traceability.csv`可追溯、人工确认列空。
- 关联只在同波段候选mask重叠小轮廓≥65%且IoU≥50%时归组；仅当多源完整外围IoU≥90%定义高一致性组；其他B种子被外围覆盖≥80%才列为`embedded`，但不自动认定同一真实疵病；不允许按“面积倍数”强制删小种子，也不会将重合分组计量两次。正式物面尺寸缺少成像倍率标定，3.2μm只是探测器像面当量。
- 独立真实样本全部31组源真实并集NPZ与原K8D区域在全图XY位置重新计算OR**逐像素完全一致**，32个K8D候选没有遗漏或被重复分组，验证1148+1161=370px²、626+658的证据和1483不扩张、冻结原J5总对象首帧15604次帧4440。结论**K8E_INDEPENDENT_PIXEL_EXACT_QA_PASS**；单元测试10项与**全工程pytest 267 passed（9.11s）**。
- 限制：仅处理K8D先前选中的本次32个暗斑试验候选，没有完全整帧自动生成所有分波段候选的新J5 ID和合格率。分组`group_id`为临时审核展示编号；正式J5 IDs与面积等级未改。接下来请用户先肉眼核对第二帧G009和G006完整外围及是否确属一个暗斑，再决定是否进入正式统一疵病ID/跨波段汇总和真实物面尺寸定标工作。

## 2026-10-14｜Case03-K8F：用户明确认可K8E G009/G006实际为两处暗斑，已新增独立工作区统一候选清单（**不改原J5正式对象数据**）
- 用户看到`K8E_F2_B2_G009_RAW_sources_exact_union.png`（B2源1148/1161+内部1186）和`K8E_F2_B2_G006_RAW_sources_exact_union.png`（B2源626+内部658），回复“符合实际”。仅把**第二帧这两组**登记为`USER_CONFIRMED_DARKSPOT_AND_OUTER_GROUP_20261014`。第一帧K8E 13组、第二帧其他16组还没人工确认，不得借此自动加入真实缺陷。
- 已在Lixx执行新脚本`scripts/run_case03k8f_approved_supplements_ledger.py`与独立QA`scripts/verify_case03k8f_approved_register.py`及新单元测试`tests/test_case03k8f_confirmed_register.py`（5项）。**推荐输出v2**：`outputs/case03k8f_confirmed_group_register/run_20261014_F26_2_two_user_approved_G006_G009_v2`，含根`CASE03_K8F_REPORT.md`；v1首次保存128x128稀疏PNG触及通用>=1000byte PNG护栏而中断，v2改用cv2原字节PNG写入并逐像素回读，v1不要用。
- 第二帧冻结原J5 WORK_CORE有398个原候选（J5全图4440），新加入用户确认G006、G009两条研究补漏记录，**统一审查CSV共400条，非400个真实疵病**；第一帧683条WORK J5原候选、没有新增人工确认，统一复核CSV仍683条。旧J5源ID、每条面积/Feret/原size grade逐行与原J5 CSV比对**不改变**；新`WORK_F26_<frame>_<6位数>`只是排序审查编号，原J5 `global_defect_id`保留作溯源，不重写原J5官方ID。
- 第二帧新增2组：G006 G1/联结B626+658，原精确面积348px²、Feret像面当量75.523μm、面积像面当量3563.52μm²；G009 1148+1161+1186，原精确RAW并集面积370px²（**不是369+370=739**）、Feret 74.91μm、面积像面当量3788.80μm²；合718px²。两个组新试验级别均LARGE；**3.2um/px只是探测器像面尺度，物面倍率没标定，不能作滤光片真实物面尺寸。**
- 两组RAW外围与所有原J5全图对象的显示bounding box做保守相交核验，**0碰撞**，比仅检查WORK中心更严格；其余16组仅保留待审。新CSV`workband_unified_candidate_review_register.csv`包含全部原J5+这两组的来源、统一索引、全图XY、像素面积/长度、3.2μm像面换算、人工确认状态和未校准标志。`other_K8E_groups_pending_manual_review.csv`隔离未确认组，`all_K8E_source_B_members_with_exact_user_approval.csv`中仅这两组共5条B源为confirmed，保留原B碎片ID。
- 用户偏好中、大优先新图：`frame26_2/02_MEDLARGE_plus_two_USER_CONFIRMED_DARKSPOTS.png`原J5 WORK MED/LARGE 26候选+2确认暗斑以1px细轮廓显示，不挤绿小点；`01_J5_existing_MEDLARGE_baseline.png`原冻结主图；`03_ONLY_user_confirmed_darkspot_outlines.png`只新2组；`04_SMALL_existing_and_K8C_reference.png`微候选单图。两张新`K8E_F2_B2_G006_outer_mask_128p.png`与`...G009...`完全等于K8E源NPZ原像素并集掩膜；全图RAW像素XY在溯源NPZ与CSV。
- 已查看实际主图及补漏专图；独立`K8F_INDEPENDENT_QA_PASS`验证第一帧683/第二帧400记录、全部旧J5 id/area/grade/feret、两组源mask等于原K8E、没有旧J5 bbox碰撞、所有PNG解码、确认状态严格只2组，**全工程pytest272 passed (10.89s)**。
- 重要限制：这还不是全图生产真缺陷ID、可靠精度/召回/漏检评价或质检合格率；只是正式独立**审查索引**整合。不得覆盖原`outputs/case03j5_global/.../global_defects.csv`或把J5其它候选标为真实缺陷。后续如要正式物面大小，先获得倍率/标定标尺，还需审查余下16组。

## 2026-10-15 Case03-K8G：用户要求框扩大1.5倍、1像素细线、标注疵病大小，已在Lixx实际完成双帧显示改版
- 用户确认G006/G009对应真实暗斑并保留完整外围；K8F已有第二帧工作区398 J5疑似候选＋2人工确认暗斑=400审查记录、第一帧683旧J5疑似记录。用户指出原框小易盖住缺陷，要求原框1.5倍、细线并标面积/长度。曾因Lixx离线，用户重新连接后状态Online，已在原Windows工程实施。
- 新代码`src/detection/case03k8g_display_boxes.py`、`scripts/run_case03k8g_1p5_display_boxes.py`、`scripts/verify_case03k8g_1p5_boxes.py`、`tests/test_case03k8g_display_boxes.py`（8项）。**最终只推荐v2**：`outputs/case03k8g_display_zoom_labels/run_20261015_26_1_2_boxes_1p5x_1px_size_v2`，根`CASE03_K8G_DISPLAY_REPORT.md`和`independent_QA.json`及`full_pytest_result.log`均已生成。
- 坐标仍在原11276x9200 RAW：对于源J5中大，获取旧K8F真正绘制的`display_bbox_[xy]_global`（而不是用SourceBBox替代），对于新增确认G006/G009采用已批准K8E准确全轮廓外接显示框。对旧框RAW连续坐标以中心扩张，宽=旧宽×1.5、高=旧高×1.5，近RAW四边裁剪。只改变显示框，绝不改变source area/Feret/size grade/old J5 IDs及K8E真实轮廓源像素。图框宽**1个显示像素**，不填充或在主图叠画任何掩膜，以免视觉遮盖暗斑。
- 图中两行**中文Unicode字体**标签：疵病源编号短名＋[大/中]＋`A=xxx px²`；第二行`L=xx.x μm (像面)`，L=原J5 source maxFeret/已确认K8E精确并集mask maxFeret×探测器3.2µm/px，不是滤光片物面的实际标定尺寸。J5已有大红、中黄、新已确认暗斑G006/G009青色；绿小候选单独保留源参考图，不进入主图。使用本地Windows微软雅黑字体显示中文/μm（不分发字体）。
- 运行两帧生成`frame26_1/`和`frame26_2/`：先看**`02_MED_LARGE_boxes_1p5x_1px_with_area_length_detail_1to4.png`**（1:4高清全图，第一帧25中大、第二帧28中大）；`01_MED_LARGE_boxes_1p5x_1px_with_area_length_overview_1to8.png`（1:8原比例全图概览），第二帧`03_G006_G009_1p5box_vs_exact_mask_three_panel.png`（2行G006/009×3栏：同RAW原图、1.5倍细框、源K8E准确轮廓作为唯一面积测量来源），`04_SMALL_unchanged_reference.png`为小候选完整源参考。
- 每帧`per_object_1p5_display_geometry_and_UNCHANGED_sizes.csv`记录完整源标记ID、原显示框真实RAW坐标、新1.5显示框RAW坐标、缩放后像素坐标、原始面积/Feret/等级、文字位置及内容、`measurement_uses_enlarged_bbox=False`；`frozen_K8F_work_review_register_UNCHANGED.csv`字节SHA256与原K8F完整审查CSV一致。
- 1:8第一批v1因标签密集造成4处互撞和3～4处压其它目标，独立QA发现后扩大标注位置候选搜索、独立v2重跑。**当前v2双帧1:8/1:4 4张图共四项审核都达到 own-box碰撞0、other-box碰撞0、labels互撞0**，PNG实际已打开目检，第二帧新主图可读。源J5面积/grade/feret逐条完好。
- `scripts/verify_case03k8g_1p5_boxes.py`真实逐项执行`K8G_QA_PASS`，结合8新增合成单测，全工程**280 passed in 12.04s**（记录在`full_pytest_result.log`）。唯一工作仍是让用户审查字体/扩大倍率是否满足其视觉偏好；原检测/品质验收结果本轮根本不改变。

## 2026-10-15 用户指出第一帧Band02 K8D两处暗区在最新K8G缺失——根因复核及K8H显示层已修复
- 用户上传第一帧K8G`.../frame26_1/01_MED_LARGE_boxes_1p5x_1px_with_area_length_overview_1to8.png`截图圈出Band02中部条状RAW暗缺陷，指出此前`outputs/case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3/frame26_1/band02`曾提两个明显目标，问是否算法一致以及漏掉原因。**真正根因不是K8G新1.5倍框、也不是新版RAW阈值降低效果变差，而是后续K8F仅把已确认的第二帧K8E G006/G009作为新增写入J5统一审查表，第一帧K8F新增审核0，K8G只显示K8F中大所以没有再读取第一帧K8D/K8E未审补漏。**两个阶段候选来源本来不同，不能把K8G说成“完整K8D检测”的同算法等价结果。
- 源第一帧Band02 K8D有**6个源候选**：B614源H135px²、K8D RAW试验外围2262px²（K8D半径上限＋过细长＋面积max守护未通过）；B1273源H162px²→RAW1646px²（半径＋细长拒绝）；B1562源H456px²→RAW1781px²（半径＋细长拒绝）；三个位置相邻，对应用户圈的中部条状缺陷区域，不能无证据一口认成一个物理划痕，K8E显示G001/G002/G003。B1902源H56px²→RAW398px²（K8D稳定但未获用户人工确认），K8E G004，对应左侧点状黑斑。另两个B2871/3989原始9px小种子被严格3MAD锚保护，不属中大主图。
- **真实新增显示层补救Case03-K8H**：代码`scripts/run_case03k8h_f1_B02_review_reinstatement.py`、独立QA`scripts/verify_case03k8h_f1_B02_review_overlay.py`；输出目录`outputs/case03k8h_f1_band02_review_overlay/run_20261015_f1_b2_K8D_unreviewed_restore_v1`，根报告`CASE03_K8H_ROOT_CAUSE_REPORT.md`。
- 核心图**`01_F1_B02_review_reinstated_plus_J5_1to8.png`**（实际打开，第一帧旧K8G J5 25个中大红黄框全部保留、附两处橙色1.5倍1px细框的**复核区域**A/B），**`02_F1_B02_review_reinstated_plus_J5_1to4.png`**（同一图高清1:4，优先检查），**`03_B02_two_REVIEW_ZONES_RAW_vs_trial_contours.png`**（实际打开，上方A中部条状暗区左原RAW右原K8D三个源RAW外围不同色轮廓；下方B左侧点状暗斑左RAW右K8D 398px外围）。4张源K8E原四栏RAW参考图也复制在该目录。
- A只用一个外显示框围住B614/B1273/B1562位置供人工定位，不等于自动确认“是一条真实划痕”、没有把这些面积相加；B是B1902，RAW面积398px²仍是试验建议，不代表已确认物面面积。新的`B02_four_original_K8D_source_candidates.csv`与`B02_two_review_zone_1p5_DISPLAY_geometry.csv`分别存逐个源面积/试验外围/安全性理由，以及两组1.5倍显示框真实RAW XY位置+不同缩略尺度；人工确认全False。**不能擅自更新原J5/K8F官方质量统计、轮廓或ID**。
- QA实际运行`K8H_REAL_RAW_CORRESPONDENCE_AND_DISPLAY_ONLY_QA_PASS`：4个源H及RAW外围与旧K8D实际NPZ逐像素源数量相等，1.5倍B02复核框真坐标核验，新全图与原K8G逐像素对比——除橙色新增框、区域文字及重新写的标题外**全部原J5原显示像素都没有改**；原K8F第一帧683条候选与老J5正式索引保持不变。全工程pytest**280 passed in 10.16s**。
- 后续用户如确认第一帧B02哪两个物理暗区属实际缺陷，应单独保存第一帧人工审查状态，并重新解决A的多分段关系和越半径/长线安全边界；别误把第一帧缺陷自动批准，也别在K8F/K8G后续展示中静默丢任何“补漏待复核”数据。正确生产工程UI应清晰分离**旧J5主通道、已确认K8E补漏、未确认K8D补漏待复核**三层。

## 2026-10-15：用户授权正式进入K8I整图集成，已在Lixx实际运行两帧完整RAW的**全候选来源追踪和分层显示**，不能再仅看K8F/K8G主图
- 新K8I代码`src/detection/case03k8i_lineage_rules.py`、`scripts/run_case03k8i_full_frame_lineage.py`、`scripts/verify_case03k8i_full_frame_lineage.py`、`tests/test_case03k8i_lineage_rules.py`；新独立中大RAW补试验`scripts/run_case03k8i_priority_raw_contour_probes.py`及`scripts/verify_case03k8i_priority_raw_contour_probes.py`。旧J5/K8A~H检测源与阈值不改；读取已有26(1)/(2) 11276×9200 RAW和各阶段只读mask/CSV，波段IDs从已保存K8A/K8B metadata动态取，两帧目前各4带（代码不假设固定4）。
- **第一优先K8I目录**`outputs/case03k8i_full_frame_lineage/run_20261015_sample26_2frames_fullcandidate_lineage_v1`；根`CASE03_K8I_FULLFRAME_IMPLEMENTATION_REPORT.md`有全部步骤、数目、图片、边界。每帧`end_to_end_candidate_lineage.csv`全候选来源J5+K8B：第一帧**15604原J5全图+16766 B源=32370行**，第二帧**4440+3892=8332行**，两帧40702条源**0个缺失显示去向**。J5和B是不同分支并可重叠，记录数不能当独立实际疵病数；跨J5/B真实对象空间查重**尚未自动完成**，在CSV明确`NOT_EVALUATED_DO_NOT_ASSUME_DEDUPLICATION`。所有K8C微点即使被建议hide，也仍在`04_K8C_MICRO_SUGGEST_HIDE_NOT_DELETED_1to4.png`，独立小候选`03_ALL_SMALL_J5_AND_NOVEL_B_1to4.png`；旧J5的非工作区也不删除而在`06_J5_OUTSIDE_WORK_REVIEW_REFERENCE_1to8.png`；K8B固定H重合参考`05_K8B_FIXED_H_OVERLAP_REFERENCE_1to8.png`，所有B原始source pixels在`07_ALL_K8B_B_SOURCE_PIXELS_reference_1to8.png`，首帧B源像素39333，第二帧14753，与K8B源mask逐pixel计数一致。
- **新版全图主图**`frame26_1/01_MAIN_J5_plus_confirmed_plus_unapproved_MEDLARGE_1to4.png`、`frame26_2/01_MAIN_J5_plus_confirmed_plus_unapproved_MEDLARGE_1to4.png`（均39个中大/复核框，1.5倍单像素细框，每个A及L来自原J5源或K8E RAW试验真实掩膜/未做K8D时的B真实源，不使用扩大的框计算）。旧J5工作区中大25/26+用户确认第二帧G006/G009两组+所有待审K8E中大+新源B中大都明确显示，**第一帧Band02四原K8D问题614/1273/1562/1902由通用K8E动态清单加载进入，而不需要K8H硬编码4个B标签**。所有K8E复核组无论大小在`02_ALL_K8E_PENDING_AND_CONFLICT_GROUPS_1to4.png`（第一帧13组第二帧18组），每帧还有`08_MAIN_all_mediumlarge_overview_readable_preview.png`可远程轻量打开；第一帧主图实际打开已视觉检查。
- 分层精确统计文件`render_visibility_reconciliation.json`；第一帧B`K8C微候选建议隐藏`11524（均可见复核层），原J5 nonwork14921、小658，中大25；第二帧B micro3168、J5 nonwork4042、小372、中大26。用户确认仅第二帧G006/G009对应5个原B碎片，其他不自动确认为真实疵病。独立QA`K8I_INDEPENDENT_FULL_CANDIDATE_LINEAGE_QA_PASS`通过源CSV/mask/ID/全部原B像素和每一层PNG、两帧K8D/K8E、指定F1 B2和F2确认对象，所有UID完整无丢失。
- **原K8D没覆盖的新增中大源补试验**：第二目录`outputs/case03k8i_full_frame_lineage/run_20261015_fullframe_novel_medlarge_K8D_original_rules_probe_v1`。根据上述全量索引**自动发现仅第一帧4个**以前没做K8D的B_NOVEL_MEDLARGE，第二帧0个，用原`raw_outer_envelope`3/2/1.5MAD+相同K8D稳定门控重算：F1 B02-C3原52→仍52、B02-C9 51→51、B03-C1692 **104→325**（3/2/1.5MAD=253/299/325，STABLE_SINGLE_OUTER_REVIEW），B03-C3615 120→120；另外三个3MAD无可靠strict anchor不放行。四对象都`fully_manual_review_required=True`，不修改J5或正式尺寸。**关键六栏图**`frame26_1/band03/F1_B3_C01692_NEW_RAW_trial_6panel.png`已打开核对RAW黑斑，外轮廓比源核完整；`frame26_1/08_NEW_MEDLARGE_RAW_trial_overlay_NOT_APPROVED.png`是新四个试验橙色ROI标记，原主图不覆盖。独立QA`K8I_NOVEL_MEDLARGE_OUTER_INDEPENDENT_QA_PASS`，所有NPZ有完整原128px源seed及RAW三档。
- 新增10项Python单元测试，完整工程`.venv\Scripts\python.exe -m pytest -q --basetemp .pytest_tmp_case03k8i_all_20261015` **290 passed in 14.62s**。实际完成的是**全图源候选完整追踪/显示+此前未做过K8D的新增中大源严格保守RAW试验**；没有把全部20,658个B候选无条件执行K8D RAW，不能把完成K8I候选追踪误作全量完整RAW外围算法/生产检出率已验证。
- 后续问题必须主动告诉用户，不得暗藏：第一帧Band02的条状长轮廓仍越K8D半径/形状限制，因此橙色待审而非正式面积；B03-C1692新的325px2稳定**只是待复核**；K8A `band_count_human_approved`历史记录false与聊天审批暂未完全同步；J5/B跨分支实际pixel overlap归属/去重未完，正式工业标定/全新RAW盲测也未做。将来所有影响保留/合并/主图可见的规则变更，必须事前向用户列明影响并征得同意。

## 2026-10-17 Case03-K8I 第二阶段：整图分波段RAW证据优先轮廓+安全关联，已在Lixx实际完成、真实数据QA通过
- 依据用户指令“进行K8I第二阶段”，新增脚本`scripts/run_case03k8i_stage2_fullband_priority_contours.py`、`scripts/verify_case03k8i_stage2_fullband_priority_contours.py`、`scripts/build_case03k8i_stage2_review_pack.py`、`scripts/build_case03k8i_stage2_review_case_cards.py`、`scripts/record_case03k8i_stage2_input_manifest.py`与9项新增测试`tests/test_case03k8i_stage2_fullband.py`。保持原J5/K8B/C/D/E/F/G/H/K8I第一阶段所有数据和已确认原G006=348/G009=370px²完全冻结；原170/230、分波段阈值、K8D的RAW3/2/1.5MAD+稳态门控不变，**所有新外轮廓只进人工复核，绝不自动批准/自动合并原正式ID**。
- **K8I第二阶段唯一输出**：`outputs/case03k8i_stage2_RAW_review_and_association/run_20261017_twoframes_priority_evidence_v1`，完整`CASE03_K8I_STAGE2_IMPLEMENTATION_REPORT.md`，根`summary.json`、`independent_QA.json`、`visual_review_pack_summary.json`、`read_only_input_SHA256_manifest.json`（59个输入含两帧RAW合414956800字节及源码/旧掩膜SHA256，建立后验版本溯源）。
- 原K8I整图全量**20,658个B源**在`frame26_X/ALL_B_STAGE2_processing_disposition.csv`都有唯一互斥处理记录（首帧16766、二帧3892，丢失0）；本轮K8C`PROMISING_DARK_REVIEW/UNCERTAIN_REVIEW/BOUNDARY_REVIEW`类别中排除旧已执行RAW者，新增原RAW轮廓试验帧1**131**，帧2**5**共136，全部完成3/2/1.5MAD原K8D门控；复用旧K8D以及前一轮K8I中大试验**17+19=36**。本轮新136结果中3MAD严格锚不足保持原源122、稳定单源7、稳定关联多源4、越径向/形态完整橙色受限2、增长不显著1。**总11个稳定候选（第一帧），但未确认不能算11个独立真实疵病**。
- **透明保留的非新RAW扩张类别**：K8C`MICRO_REVIEW`帧1 2086+二帧172=2258；K8C`MICRO_HIDE_SUGGESTION`11524+3168=14692；与固定阈值H重合的源3008+528=3536；均保持原源B、K8I第一阶段微候选/小候选/固定重合独立参考图，并在第二阶段处理原因CSV中明确标记**本批未进一步扩大**。未得到用户审批时不把这16950个微种子随意扩张或自动判噪。已有正式J5和K8B的跨通道完整物理对象去重**仍未完成**，仅对新增组做了原J5显示BBox初筛（0潜在碰撞），不能据此称跨通道彻底去重。
- 新RAW136种子聚为`new_exact_group_union_review.csv`里的**134个新复核提案组**（第一帧129、第二帧5），K8E`make_groups`使用原RAW坐标实际布尔OR并集，绝不叠加像素面积计算，不混原已审批K8E组；两帧历史K8E 13+18个组只读保留，`ALL_FROZEN_AND_NEW_RAW_REVIEW_GROUPS_no_ID_merge.csv`提供共165个历史+新复核组各自来源和人工确认状态。第一帧3个新组与旧K8D轮廓相交，全部用`PENDING_OLD_OUTER_OVERLAP_REVIEW`交人工确认。原J5 displayed bbox初筛0次相交，不等于像素级跨J5-B对象去重。
- **用户最应看的两张图**：`frame26_1/05_B04_TRIPLE_RAW_sources_outer_exact_union_REVIEW.png`（原RAW，B2424/2444/2504三个各289/295/286px²外围，直接相加870，原RAW坐标精确OR并集**297px²**，重复面积去除573，非正式审批），`frame26_1/06_B02_1787_vs_OLD_B1902_overlap_REVIEW.png`（新增B1787原23px²→398外围与原K8D B1902外围398**逐像素完全一致**，交集398、并集398、IoU=1，**不得重复计量但尚未自动改官方ID**）。两张图片均通过远程读取实际目检RAW轮廓。
- 全图`frame26_X/01_STAGE2_NEW_RAW_GROUPS_REVIEW_plus_original_K8I_main.png`是已冻结K8I旧中大主图上新增1.5×1显示像素橙色复核框；`02_NEW_RAW_GROUPS_ALL_review_1to4.png`为新134组全量复核；`03_ONLY_NEW_STABLE_RAW_GROUPS_review_1to4.png`仅8个新稳定且与历史RAW不重叠组在第一帧，第二帧0（其他候选仍完整在全部新组层，未隐藏）；`04_OLD_RAW_or_J5_bbox_OVERLAP_review_1to4.png`为旧RAW相交争议独立图。全部新分组有完整原像素NPZ，全源去向CSV及碰撞JSON，显示大小不参与真实面积。
- 独立`CASE03_K8I_STAGE2_INDEPENDENT_SOURCE_AND_PIXEL_QA_PASS`确认**所有20,658源B去向唯一、136新RAW源seed和3档RAW与原K8B标签/面积逐像素一致、134个新像素并集掩膜逐组重算一致、已批准两处旧面积完全不变**；新回归9项，**全工程pytest299 passed in 11.08s**。
- 限制：这次是**全帧覆盖的K8C证据优先轮廓试验**（所有源有状态，只有合适证据类做新RAW），不是对全部20658 B连通源做高风险K8D RAW扩张；K8D细长划痕越径向cap仍属于RAW待确认；J5↔B全图正式像素去重、微源进一步RAW研究、新滤光片独立盲测、物面倍率标定仍未完成。后续任何隐去/改变候选必须事前说明、列差异并获用户同意。

## 2026-10-17｜K8I第二阶段用户明确确认第一帧Band02、Band04各一处真实暗斑、外围完整
- 用户看过第二阶段局部图`01_Band04_Review.png`和`02_Band02_Review.png`，明确回答**“是同一处暗斑，02与04都识别准确，各自只有一处暗斑轮廓也完整”**。解释为：**F26(1) Band02** 的旧B1902与新B1787属同一处用户确认暗斑、外围398px²；**F26(1) Band04** 的B2424/B2444/B2504三源分段属另一处用户确认暗斑、原RAW像素布尔OR并集297px²（绝不可当870px²），合计2处、5源编号、695px²唯一外围。严格仅确认这两个，不扩展为其余132个K8I2复核组已经确认。
- 已真实在Lixx增添代码`scripts/run_case03k8i_stage2_commit_user_confirmation.py`与`scripts/verify_case03k8i_stage2_user_confirmation.py`及4个`tests/test_case03k8i_stage2_human_approval.py`。**唯一新持久审核目录**`outputs/case03k8i_stage2_user_confirmed_reviews/run_20261017_F1_B02_B04_two_darkspots_v1`。主记录`two_user_confirmed_darkspots_no_duplicate_area.csv`，5个旧B源↔两处物理暗斑`five_B_source_components_to_two_user_confirmed_darkspots.csv`，两张`confirmed_mask_reviewonly/*.npz`来自旧源真实RAW mask并可复核XY位置，4个标注和原图拷贝PNG，`summary.json`、`independent_QA.json`和`CASE03_K8I2_B02_B04_USER_APPROVAL_REPORT.md`。
- Band02规范MASK取**旧K8E原正式复核组`K8E_F1_B2_G004`**，与新K8I2`K8I2_F1_B02_G0021`在全RAW像素XY下精确一致（旧398、新398、交398，IoU1），一个对象绝不能把两个来源398+398相加。Band04取新组`K8I2_F1_B04_G0096`真实精确并集297px²（旧RAW提案各289/295/286，直加870重复573）。图像Feret像面：Band02 93.46μm、Band04 71.911μm，单位只是**3.2μm探测器像面当量，物面仍未标定**。两组新人工批准均标`user_confirmed_one_physical_darkspot=True`和`user_confirmed_outer_complete_and_accurate=True`，但`production_quality_approval_not_asserted=True`，未重写任何旧J5原ID或源掩膜。
- 工程QA`K8I_STAGE2_USER_APPROVED_TWO_SPOTS_INDEPENDENT_QA_PASS`，旧J5所有bbox没有与这两处碰撞，旧第二帧用户已确认G006=348、G009=370px²不变；全工程**303 passed (11.94s)**。
- **待下一步集成提醒**：原`run_case03k8i_stage2_fullband_priority_contours.py`各历史CSV仍保留旧PENDING状态（保持结果可审计）；最新用户人工审批需要**下游统一审查入口明确读取新`two_user_confirmed_darkspots_no_duplicate_area.csv`**，不得再像K8F/K8G那样只靠硬编码审批白名单，造成这两处有审核却在新主图缺失。对其他未批准候选只标待审，所有图层的“看不到”必须告知用户并有理由。

## 2026-10-19｜Case03 26_1/26_2最新统一终检（用户已批准方案A）
- 用户明确要求：**只在最终主图标注算法判为疵病的真实轮廓，不显示全部微点和待复核框；26两帧大面积原源候选可以按证据纳入；4处此前人工确认暗斑不能丢，划痕/十字划痕保留J1/J2/G/H保护；旧J5和B所有源不得静默丢失。** 已真正在Lixx写入统一脚本并执行。
- 最新唯一正式终检结果目录 **`outputs/CASE03_UNIFIED_FINAL_DETECTOR_26_1_26_2_20261019_v2`**（不要误指v1早期半成品或`CASE03_FROZEN_RELEASE_20261019_v2`历史“待复核层”）：26_1 `00_FINAL_DEFECTS_ONLY_fullframe_1to4.png` **39个自动入选对象**，26_2同名图**35个**；各自`01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK_11276x9200.png`为原RAW全分辨率**真正像素二值掩膜**，最终源像素总量分别17493、17704；同目录`FINAL_DEFECTS_AND_MEASUREMENTS.csv`、`ALL_ORIGINAL_J5_AND_B_SOURCE_DISPOSITIONS_NO_DROP.csv`、`EXACT_FINAL_BINARY_MASKS/*.npz`、`FINAL_LOCAL_RAW_CONTOUR_PROOFS/*.png`（39+35张真实RAW局部三栏轮廓对照）和`summary.json`、`independent_QA.json`。两帧原J5+B **40702条**（32370/8332）审计UID唯一可回查，不做沉默删除。
- 74是**当前自动规则入选对象（非74个用户真值）**。4处人工确认掩膜**逐像素精确保留**：26_1 B02 B1787/1902一处398px²、B04 B2424/2444/2504一处297px²；26_2 B02 G006 348px²、G009 370px²；不用多个分段面积相加。原J5工作区中大25+26个原精确源掩膜均保留，26_1还有1处J5源10px以上方向性小划痕受到专门保护。
- **实现**`scripts/run_case03_unified_final_detector_26_1_2.py`复用**真实已完成J4/J5**（逐像素J4 grouped_source_only重构、H种子Gaussian/Closing + F/G/H RAW/MAD/DoG噪声保护，J1/J2划痕关联和J5 1620tile接缝合并），K8A动态WORK、K8B原A/B多尺度BH自适应候选、K8C噪声、K8D 3/2/1.5 MAD安全门控、K8E真实mask OR；自动终检筛噪原则是J5 WORK MEDLARGE原像素、已认可4暗斑、原B种子≥40px²且RAW暗度证据良好的K8E/B补充。**安全门控失败/扩张>8倍的旧K8D外围回退原B真实源种子**，11个该类轮廓面积只保守表示已检暗斑核心，其真实外围完整性未经人工证明。所有微点只按K8C建议不进主图，源mask从未删除，审计明确非人工真值。原B阶段的超密集黄色噪点图从此不当最终图展示。
- **源级真伪优先级**：此前一张绿色稳定图中用户曾称8框都非疵病；后来用户明确认可B04 G0096一处真实暗斑，所以最新具体确认覆盖老宽泛否定，**剩余7组**作为负例不进最终主图，独立`USER_NEGATIVE_GREEN_VS_FINAL_SPATIAL_CONFLICT_AUDIT.csv`证明最终mask交集为0。最终对象间没有像素重复，J5/B最后入选组没有原像素相交且无25px以内近邻B/J5；**不是盲目按BBox合并**。
- **独立真实像素QA PASS**：`scripts/verify_case03_unified_final_detector_26_1_2.py`重建并校验74个NPZ像素、Feret、对象等级、J4源对账、完整RAW二值PNG无重叠、4个旧用户确认精确源mask未改、全部40702条源唯一去向。测试`tests/test_case03_unified_final_detector_26_1_2.py`新增8项回归，全工程最终**322 passed**（如需后续重新跑）。
- **真实主入口已接到`main.py --case unified-final --sample 26`**，调用`scripts/run_case03_final_oneclick_26_1_2.py`，核验两帧原RAW SHA256、原J4每帧1620块及J5面积守恒、K8A/B/C对旧26精确像素回放一致、K8D/E及K8I源完整、审核掩膜和最终独立QA，并生成`ONE_COMMAND_26_STAGES_2FRAMES_NO_OMISSION.csv`52条原26阶段×两帧状态及`ONE_COMMAND_STAGE_EXECUTION_TRACE.json`。**一键重入复用并验签既有冻结数据，不伪称刚从空盘全新重算J4/J5**；原历史阶段代码及掩膜保留只读，3A/K5/K8H临时研究步骤明确“已归档非主判定门控”。后续换样本需先重新J4/J5/K8A/B/C/D/E，不可直接沿用26号来源及人工审核。
- **重要未完真值**：74个入选只有4个由用户明确目视确认，未确认70个仍可能有假阳性/轮廓不完整；无独立密集标注不能给精确率/召回率或“划痕无漏检”承诺。需要用户打开这两张**新`00_FINAL_DEFECTS_ONLY...`**及局部RAW证明图指出漏检/假阳性，再对其余18帧推广；不要用旧B_ALL中间候选图判本版效果。详细`README_26两帧最终疵病图与完整算法验证.md`。
# 2026-10-19 统一终检审查修复更新

最新v4仅矩形标记，面积依据分割mask（扣除孔洞/重叠），长度依据最大Feret，不按框测量。
目标旧F1_FINAL_0032/0039/0031/0029的B02源614/1028/1273/1562合为新F1_FINAL_0029，3469px²、189.97368px。
根因是细长目标RAW安全恢复失败回退种子、历史稳定提案未消费，以及仅相交关联无法连通间断种子。
修复引入多源局部背景残差支持，必须同一RAW连通分量覆盖各源；不放宽全局阈值，保留负例/工作区/扩张上限。
配置集中在config/user_config.py UNIFIED_FINAL；背景尺度16、噪声倍数3、种子距离40、覆盖0.90、增长8倍。
新增任意同格式RAW从头管线和拖放入口。当前仅26双帧完成真实全图验证，不宣称支持任意成像格式或其他样品精度。
工程测试330 passed；双帧各1620块真实重算，最终36/35对象；完整审计/实际命令/风险见UNIFIED_FINAL_ACCEPTANCE_20261019.md。
下文历史记录只读保留；本次不进入Case04/05，也不推广其余18帧。

