# J4 性能与工作条带审计（2026-11-07）

## 1. 审计对象与版本

基准为昨天完整成功的发布版27-1运行：`\\?\C:\Users\lixia\Documents\Codex\2026-10-20\an\outputs\RAW_Performance_20261106_27_1_retry1\runtime\ENGINE_293d02cded8c401cbdf3957e9d7cc224\inspection\2026-11-06T135941.341190_0800_27-1_000_8373aa76\engine\roi-bh`。外层Engine receipt=PASS，软件提交`c303e7eb4f24d2ff7713d73095f502f57b9a18f1`，RAW SHA256=`3927dbb72b966f60346d53a1c67d1e90e4652a52693439e69ecce1275cc08ec3`，冻结算法SHA256=`b59eddcddc7739b94b5a58dff93fc3c2235aa63dbda049cd07ae16d5696706a5`。请求AUTO，实际ROI-BH，未回退。原生J4=76.271s，BH=4.318s，J5=3.827s，K8输出=5.717s，算法主体=92.980s，最终38对象/19879px²。outputs内历史、失败、完整运行和外部最新成功基准分别列在baseline_run_inventory.csv，不以失败运行计时。

当前算法目录没有Git仓库，不能虚构HEAD。原始Python文件逐文件哈希另存。当前四个文件与冻结源的差异只涉及注释/docstring；去除注释/docstring后的AST完全相同，详见baseline_source_match.json。所有原始生产文件保持本轮开始时的字节，新增独立diagnostics模块。未重建Engine、未改GUI、参数、阈值或源mask。

## 2. 实际生产链

GUI实际从DetectionEngineClient进入冻结engine_runner.exe，经过Detector的AUTO调度和独立reference-attempt/bridge，再进入run_two_level_unified.run_raw。bridge还先做一次分带/调度有效性检查。main.py只有明确选择`--roi-mode`时才走此Two-Level入口；不能把不带该参数的历史终检重入路径说成新算J4。

Two-Level：K8A→ROI-BH→J4→J5→K8与最终输出。J4.run_tile→Case03T.process_one→**case03t_hseeded_variable.detect_window_H_seeded**，不是文档列举的旧case03e2_hseeded入口。源码和两种H-seeded模块都已读取，具体证据为production_code_readings.txt。

## 3. K8A工作条带

重算4条工作带，band_id差异0、region_type差异0、geometry一致。每条上下边界是随x变化的直线，并非单一固定行。参数和每条边界见recomputed_band_geometry.json。WORK_CORE=26,666,500px；EDGE=1,202,134px；NONWORK=75,870,566px。NONWORK审计口径明确包含原始code0外部区域和code1遮光区，分别为27,333,024/48,537,542px，未把遮光像素漏掉。

拟合条带边界如下（0基坐标，CORE在上下边界内收12px；离散像素以region_type为准）：

| band | top_x0 | top_x11275 | bottom_x0 | bottom_x11275 | core_x_min | core_x_max_exclusive | review_margin |
|---|---|---|---|---|---|---|---|
| 1 | 3314.611000 | 3294.434275 | 3929.521000 | 3914.514990 | 24 | 11252 | 12 |
| 2 | 5122.578000 | 5118.161244 | 5648.175000 | 5646.962261 | 24 | 11252 | 12 |
| 3 | 5987.561000 | 5989.695019 | 6600.724000 | 6608.647845 | 24 | 11252 | 12 |
| 4 | 6938.197000 | 6949.378530 | 7641.898000 | 7657.780867 | 24 | 11252 | 12 |


## 4. 四种范围和全部Tile调度

A为K8A的WORK_CORE；B为边缘复核区；C为检测矩形上下扩展（最大支持93px+review12px），只表示计算上下文；D为原始256px网格的完整core和64px halo，窄余块还会向内扩到最小192px工作宽度。C/D不能称为有效工作区。

1620个原始Tile全部核验：720 scheduled、900 skipped；每个scheduled core均与C相交，每个skipped core与所有C均不相交。scheduled中148个core完全没有WORK_CORE，236个WORK_CORE占比低于10%，237个低于25%。

## 5. 实际计算像素量

全幅103,739,200px，WORK_CORE占25.71%；WORK+EDGE=27,868,634px；C矩形并集=37,808,428px；scheduled core并集=46,186,496px（全幅44.52%）。

所有J4窗口访问总和104,275,968px，含Halo重复访问，相当于全幅1.0052倍、WORK_CORE的3.9104倍、scheduled core并集的2.2577倍。原1620Tile全算窗口访问为232,176,960px，当前减少55.09%。不能把“900个Tile跳过”理解成每个剩余像素只访问一次，也不能因当前窗口访问接近一次全幅就说ROI完全没节省——原全网格本身也有Halo重复。

## 6. J4整体与Tile耗时

基准J4=76.271s；新cProfile重放=64.583s。两者不可混作同一次计时；探针/cProfile增加Python开销，机器负载和缓存也不同，所有语义百分比使用profile wall分母，不把时间硬缩放到76秒。baseline Tile统计见j4_tile_time_summary.json。

| group | count | sum | mean | median | P90 | J4_wall_fraction |
|---|---|---|---|---|---|---|
| H=0 | 538 | 51.152000 | 0.095078 | 0.094000 | 0.108000 | 0.670657 |
| H=1..5 | 88 | 8.917000 | 0.101330 | 0.101000 | 0.114600 | 0.116911 |
| H=6..20 | 87 | 12.020000 | 0.138161 | 0.136000 | 0.161000 | 0.157595 |
| H>20 | 7 | 1.253000 | 0.179000 | 0.175000 | 0.195600 | 0.016428 |
| objects=0 | 614 | 58.736000 | 0.095661 | 0.095000 | 0.108000 | 0.770092 |
| objects>0 | 106 | 14.606000 | 0.137792 | 0.134500 | 0.163500 | 0.191500 |


## 7. 函数级Top20

以下inclusive累计时间有父子重叠，不能直接相加。真实cProfile文件和Top100/callers文本已保存。具体OpenCV/NumPy操作可在self-time表中查看；语义表采用嵌套exclusive计时避免重复累计。

### cumulative Top20
| function | calls | self_seconds | cumulative_seconds |
|---|---|---|---|
| run_case03j4_fullscan.py:309 run | 1 | 0.017092 | 64.559070 |
| profiler.py:12 call | 58098 | 0.492200 | 57.475156 |
| profiler.py:42 tile | 720 | 0.136018 | 57.387886 |
| run_case03j4_fullscan.py:137 run_tile | 720 | 0.069685 | 57.251046 |
| run_case03t_threeway_comparison.py:116 process_one | 720 | 0.388672 | 49.443206 |
| case03t_hseeded_variable.py:169 detect_window_H_seeded | 720 | 1.070458 | 44.291049 |
| local_boundary_refinement.py:58 compute_local_residual | 1440 | 0.304822 | 37.450906 |
| ~:0 <GaussianBlur> | 6480 | 26.398059 | 26.398059 |
| ~:0 <morphologyEx> | 720 | 13.014902 | 13.014902 |
| run_case03j4_fullscan.py:255 finalize | 1 | 0.014079 | 6.565588 |
| ~:0 <built-in method _io.open> | 2412 | 5.881887 | 5.888990 |
| __init__.py:763 open | 1474 | 0.002406 | 4.584564 |
| __init__.py:780 read_text | 721 | 0.004946 | 4.477679 |
| _npyio_impl.py:681 savez_compressed | 720 | 0.005801 | 3.633665 |
| _npyio_impl.py:756 _savez | 720 | 0.042711 | 3.627093 |
| _format_impl.py:702 write_array | 4320 | 0.062456 | 2.524196 |
| __init__.py:1326 write | 8640 | 0.039322 | 2.265442 |
| fromnumeric.py:2031 nonzero | 10119 | 0.007441 | 2.180112 |
| fromnumeric.py:48 _wrapfunc | 10777 | 0.010960 | 2.178947 |
| ~:0 <method 'nonzero' of 'numpy.ndarray' objects> | 10119 | 2.159535 | 2.159535 |


### self-time Top20
| function | calls | self_seconds | cumulative_seconds |
|---|---|---|---|
| ~:0 <GaussianBlur> | 6480 | 26.398059 | 26.398059 |
| ~:0 <morphologyEx> | 720 | 13.014902 | 13.014902 |
| ~:0 <built-in method _io.open> | 2412 | 5.881887 | 5.888990 |
| ~:0 <method 'nonzero' of 'numpy.ndarray' objects> | 10119 | 2.159535 | 2.159535 |
| ~:0 <method 'compress' of 'zlib.Compress' objects> | 8640 | 2.112883 | 2.112883 |
| ~:0 <connectedComponentsWithStats> | 3868 | 1.481121 | 1.481121 |
| ~:0 <method 'reduce' of 'numpy.ufunc' objects> | 98769 | 1.292635 | 1.292635 |
| case03t_hseeded_variable.py:169 detect_window_H_seeded | 720 | 1.070458 | 44.291049 |
| ~:0 <method 'astype' of 'numpy.ndarray' objects> | 23314 | 0.977359 | 0.977359 |
| ~:0 <dilate> | 2347 | 0.536117 | 0.536117 |
| profiler.py:12 call | 58098 | 0.492200 | 57.475156 |
| two_level_roi.py:18 require_computed_response | 720 | 0.412991 | 0.431640 |
| ~:0 <method 'partition' of 'numpy.ndarray' objects> | 11126 | 0.407330 | 0.407330 |
| run_case03t_threeway_comparison.py:116 process_one | 720 | 0.388672 | 49.443206 |
| ~:0 <method 'seek' of '_io.BufferedRandom' objects> | 14400 | 0.329457 | 0.329457 |
| local_boundary_refinement.py:58 compute_local_residual | 1440 | 0.304822 | 37.450906 |
| case03t_adaptive_hysteresis.py:119 hysteresis_window | 720 | 0.272853 | 0.714481 |
| ~:0 <built-in method numpy.asarray> | 41322 | 0.219613 | 0.219613 |
| ~:0 <built-in method nt.replace> | 751 | 0.184893 | 0.187087 |
| case03j_object_boxes.py:27 measure_visual_bbox | 720 | 0.169963 | 0.177681 |


## 8. 空Tile证据

无H候选538个Tile，基准耗时51.152s，占J4 67.07%，均值95.08ms；H=1~5均值约101.33ms，二者接近。源码明确：process_one不在n=1时提前返回；detect_window_H_seeded在逐候选循环之前无条件计算两种残差与各自阈值/CC；DoG两次GaussianBlur也位于候选循环外。探针证据：{"Gaussian22": {"zero_H_tiles": 538, "zero_H_tiles_with_calls": 538, "calls_on_zero_H_tiles": 538}, "Closing61": {"zero_H_tiles": 538, "zero_H_tiles_with_calls": 538, "calls_on_zero_H_tiles": 538}, "DoG_H": {"zero_H_tiles": 538, "zero_H_tiles_with_calls": 538, "calls_on_zero_H_tiles": 1614}}。因此空Tile确实仍执行Gaussian22/Closing61/DoG。

## 9. 语义阶段计算与I/O

| stage | seconds | J4_fraction | calls | mean_ms |
|---|---|---|---|---|
| Gaussian22 | 23.919287 | 0.370366 | 720 | 33.221232 |
| Closing61 | 13.549851 | 0.209806 | 720 | 18.819238 |
| Other_run_and_wrapper_overhead | 7.158660 | 0.110844 | 1 | 7158.660205 |
| H_seeded_other | 3.819502 | 0.059141 | 3620 | 1.055111 |
| NPZ_write | 3.644019 | 0.056424 | 720 | 5.061138 |
| DoG_H | 1.712889 | 0.026522 | 2160 | 0.793004 |
| bbox_Feret | 1.326759 | 0.020543 | 5091 | 0.260609 |
| Process_other | 1.261616 | 0.019535 | 720 | 1.752244 |
| H170_230_CC | 1.212826 | 0.018779 | 2342 | 0.517859 |
| J1 | 1.072978 | 0.016614 | 720 | 1.490248 |
| J2 | 1.006122 | 0.015579 | 720 | 1.397391 |
| gaussian22_threshold_CC | 0.876746 | 0.013576 | 1440 | 0.608851 |
| G | 0.855928 | 0.013253 | 1440 | 0.594394 |
| closing61_threshold_CC | 0.798780 | 0.012368 | 1440 | 0.554709 |
| CSV_JSON_write | 0.729905 | 0.011302 | 859 | 0.849715 |
| Tile_RAW_response_read | 0.638658 | 0.009889 | 2880 | 0.221756 |
| extract_regions | 0.336511 | 0.005211 | 720 | 0.467377 |
| F | 0.301655 | 0.004671 | 2900 | 0.104019 |
| full_preview | 0.251417 | 0.003893 | 1 | 251.417500 |
| H_seeded_bounded_fallback | 0.108803 | 0.001685 | 86 | 1.265153 |


exclusive总和=64.582913s，profile wall=64.582913s，差额=0.000000000s。Other为未包装的调度、数组操作、切片/复制及探针开销，不能宣称已经逐行穷尽；DoG/H覆盖两次Gaussian和extend_gate，其余减法/特征汇总进入Process_other。A中显式asarray读取和sentinel检查单列，core copy等数组C操作同时可见于cProfile。Gaussian/Closing阈值估计及CC单列。NPZ、CSV/JSON和full-preview都与计算分开。

以下补充cProfile直接调用边的准备/复制及open明细；与上表有包含关系，不能再次加入exclusive总和。切片视图构造及core坐标运算计入run_tile自身，不虚构独立高精度时间；RAW/response各一次窗口asarray，另有rect输出asarray。

| caller | operation | calls | self_seconds | cumulative_seconds |
|---|---|---|---|---|
| run_tile | halo_rect | 720 | 0.001837 | 0.002682 |
| __init__.py:763 open | <built-in method _io.open> | 1474 | 4.575774 | 4.581849 |
| memmap.py:215 __new__ | <built-in method _io.open> | 2 | 0.000154 | 0.000154 |
| _format_impl.py:892 open_memmap | <built-in method _io.open> | 1 | 0.000156 | 0.000156 |
| _npyio_impl.py:311 load | <built-in method _io.open> | 1 | 0.007010 | 0.007010 |
| __init__.py:1423 __init__ | <built-in method _io.open> | 720 | 0.215988 | 0.215988 |
| common.py:701 get_handle | <built-in method _io.open> | 214 | 1.082805 | 1.083833 |
| <frozen importlib._bootstrap_external>:947 get_data | <built-in method _io.open_code> | 2 | 0.001550 | 0.001550 |
| run_tile | <method 'copy' of 'numpy.ndarray' objects> | 1440 | 0.027345 | 0.027345 |


## 10. J4源像素与工作区

| region | pixels | fraction |
|---|---|---|
| WORK_CORE | 18328 | 0.981472 |
| WORK_EDGE | 346 | 0.018528 |
| NONWORK | 0 | 0.000000 |


共490个原J4分组对象：完全CORE 488、跨CORE/EDGE 1、含NONWORK 0、中心在CORE但mask越出 1、中心不在CORE 1。中心口径为精确source像素质心取整，不冒称bbox中心；逐对象表保存实际中心。source_detected与grouped_source_only所有像素守恒，桥接像素未计入源面积。

J4计算窗口围绕工作带与输出mask严格限制工作带**不是同一回事**。J4没有按CORE把输出逐像素裁零；本27-1样本NONWORK源像素实测0，不代表任意新RAW都保证为0。

## 11. 最终mask审计

38个最终对象总面积19879px²；严格CORE之外345px，涉及1个对象；WORK+EDGE之外0px，含NONWORK对象0。F1_FINAL_0007面积1342px²，其中997 CORE、345 EDGE。最终逐mask并集与保存全幅最终binary逐像素差异0。

fresh_j5用round(center_x/y)查band_id保留对象，然后保留原完整source mask，并非裁剪到CORE；后续K8分支有自己的来源/安全门控，不能把整个最终流程一概说成只做中心测试。就本张图而言工程WORK+EDGE口径满足，严格CORE口径不满足。不能在性能审计中偷偷裁mask或改测量。

## 12. 明确回答Q1–Q7

Q1：以下Top3是新profile的**具体函数self-time**，不含父子重复累计，不是把旧76秒拆成伪精确数字。GaussianBlur合计涵盖Gaussian22及DoG等调用；其中Gaussian22语义阶段为23.919秒，Closing61语义阶段为13.551秒，以第9节精确表为准。第三名是文件打开，说明文件I/O亦有实际贡献，不能只讨论计算：

第1：<GaussianBlur>，26.398s，占新profile J4 40.87%。

第2：<morphologyEx>，13.015s，占新profile J4 20.15%。

第3：<built-in method _io.open>，5.882s，占新profile J4 9.11%。

Q2：是。538个零H Tile中昂贵操作的实际调用数及代码位置见第8节。

Q3：Tile减少900/1620=55.56%；core并集从103739200降至46186496，减少55.48%；窗口访问从232176960降至104275968，减少55.09%。

Q4：**否**。完整grid core、EDGE、扩展上下文和64px halo都参与计算，WORK_CORE仅占全幅25.71%，不等于计算范围。

Q5：本张图J4 NONWORK源像素=0、含NONWORK对象=0、比例0%；EDGE346px/1.85%。代码没有CORE硬裁，故“此图没有”不能外推为“算法禁止产生”。

Q6：本张图无WORK+EDGE之外的最终疵病像素；严格CORE之外345px/1个对象，属于EDGE。不能声称全mask都在CORE。

Q7：主要为昂贵残差计算、空Tile固定开销及halo重复计算的组合。Gaussian22和Closing61互斥语义时间合计约37.47秒，占profile约58.02%；NPZ写入约3.64秒，CSV/JSON约0.73秒，另有文件打开约5.88秒self-time（与I/O语义计时存在包含关系，不可直接相加），说明I/O是次要但不可忽略的贡献。Python调度不能与Other余项等同，不能把7.16秒余项都归咎于Python。不能只因有720个NPZ就假定压缩是主要瓶颈。

## 13. 后续建议（均未实施）

1. 先验证零H Tile提前退出/将Gaussian22与Closing61延后到确认H种子之后；538个空Tile总耗时约51.15秒只是理论上界，扣除仍需执行的H判定、状态/NPZ输出，不能直接承诺节省51秒。空H时完整输出模式和审计文件契约仍需保持。
2. 再考虑DoG按实际需要计算，以及在不改变边界支持和窗口阈值统计的条件下降低Halo重复。窗口访问约WORK_CORE的3.91倍是冗余依据，但不能直接缩Halo，否则局部背景和边界可能改变。
3. 不含CORE的148个Tile不能直接删除：其halo/core可能为边界对象或后续关联保留上下文，需先做跨tile等价证明。
4. 只有NPZ实测占比显著时才考虑压缩等级/布局，不改变源mask与可恢复审计；只有内存预算允许时才评估有限并行。此前低空闲内存已实际导致Engine启动失败，不建议无预算盲目并行。

## 14. 等价、图与阶段边界

{
  "scope": "J4-only replay: no J5/final recomputation",
  "algorithm_parameters_changed": false,
  "J4_source_masks_pixel_equal": true,
  "J4_all_npz_arrays_pixel_equal": true,
  "J4_tiles": 720,
  "J4_baseline_tiles": 720,
  "J4_source_pixel_count": 18674,
  "J4_object_count_equal": true,
  "J4_object_count": 490,
  "mismatches": [],
  "final_masks_pixel_equal": "NOT_RECOMPUTED_READ_ONLY_BASELINE",
  "final_object_count_equal": "NOT_RECOMPUTED_READ_ONLY_BASELINE"
}

本轮只重放J4；全部720个NPZ内每个数组逐元素一致，J4对象数/源像素数一致。J5和最终掩膜只读审计，未重算；因此等价JSON对final recomputation明确标NOT_RECOMPUTED，而不是伪造一次最终复跑。生产源和RAW前后哈希校验通过。10张图来自真实RAW、region、plan、Tile状态和精确mask，PNG解码通过，无流程图代替数据。

诊断过程中预检先因四处注释字节差异停止，查清并记录AST一致后继续；计划JSON元组/列表规范化比较修正仅在新增诊断工具内，未修补生产数据。预检日志保留。没有算法优化、阈值调整、候选删减、真实标签或人工质量签收。


## 15. 交付复核

10张实际结果图已逐图视觉检查（汇总接触表），RAW/CORE、调度热图及最终EDGE放大图一致。`index.html`为可打开图册。最终独立复核：720条Tile耗时、1620条调度记录、720个重放NPZ、223个生产源文件无修改；K8A逐像素差异0、J4全部数组差异0。未重新运行最终检测链，未作算法优化。详见final_verification.json。
