# 滤光片疵病生产自动检测算法程序报告

**版本日期：** 2026-11-06  
**工程：** `D:\疵病检测\DefectDetectionProject`  
**报告范围：** 只描述“输入一张新的RAW图像后，当前代码实际自动执行并影响最终疵病结果”的生产检测链。  
**默认运行模式：** `roi-bh`  
**示例数据：** 26_1，仅用于展示自动算法各阶段输出；报告中的最终示例关闭了历史人工批准/负例注入。

> 本报告只描述新RAW的生产自动检测算法。历史开发过程、人工复核/确认链、独立验证与后续研究实验均不进入本文正文。

---

## 1. 程序入口与报告所对应的真实调用链

当前生产自动检测入口为：

```powershell
python main.py --case unified-final --input "<new_raw_file>" --roi-mode roi-bh --run-id "<run_id>"
```

`main.py`在`--roi-mode roi-bh`时调用：

```text
main.py
└─ scripts/run_two_level_unified.py::run_raw()
```

对于一张**新的、未绑定历史人工记录的RAW**，实际自动算法顺序为：

```text
RAW输入与格式检查
        ↓
K8A：有效工作带自动定位
        ↓
Two-Level ROI：根据工作带建立安全检测区域
        ↓
ROI五尺度Black-Hat计算
        ↓
J4：256×256 core + 64 px halo局部检测
        ↓
J5：跨Tile全局对象合并
        ↓
fresh_j5：筛选J5中大对象和方向性小划痕
        ↓
K8B：分工作带补充候选生成
        ↓
K8C：RAW局部证据分类
        ↓
K8D：3/2/1.5 MAD RAW外围稳定性选择
        ↓
J5候选 + B支路候选汇合
        ↓
Unified RAW Recovery：同带候选的受限RAW恢复
        ↓
Consolidate：全局像素级去重/合并
        ↓
精确Mask、面积、最大Feret、尺寸分级
        ↓
1.5倍显示框 + 尺寸文字
        ↓
最终输出
```

这就是本报告唯一的主线。后续各节严格按上述顺序展开。

---

## 2. 输入RAW与运行前硬检查

**执行位置：** `scripts/run_two_level_unified.py::run_raw()`

### 2.1 RAW格式

当前工程配置：

| 参数 | 当前值 |
|---|---:|
| 图像宽度 | 11276 px |
| 图像高度 | 9200 px |
| 存储容器 | 16 bit unsigned |
| 字节序 | big-endian |
| 有效位数 | 12 bit |
| 探测器像元 | 3.2 μm/px |

程序首先检查文件是否存在，并要求：

```text
文件字节数 = 11276 × 9200 × 2
```

随后按512行分块检查RAW最大值，若存在：

```text
DN > 2^12 - 1 = 4095
```

则立即终止，避免用错误位深继续计算。

### 2.2 输入不可修改

RAW以只读`np.memmap`打开。程序记录输入SHA256，并在结束前再次核对，确保检测过程没有修改原始数据。

### 2.3 运行快照

每次运行都会保存：
- `input.json`：输入路径、SHA256、形状、数据类型；
- `source_SHA256_at_start.json`：本次运行开始时的源码SHA256；
- `config_snapshot.json`：本次自动算法使用的参数快照。

这些文件用于工程追溯，但不参与疵病判定。

---


![图2-1 原始RAW输入](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/01_RAW_input_26_1.png)
**图2-1说明：** 26_1原始RAW全幅显示。仅做百分位灰度拉伸以便观察，不改变输入数据，也不参与算法判定。

26_1纯自动示例中，J5主支路选出26个对象，B补充支路输出12个对象，汇合后为38个候选；后续RAW Recovery将其中4个同组B源对象替换为1个恢复对象，候选数因此减少为35。

本次26_1纯自动示例的Consolidate输入为35个对象，输出仍为35个对象，关联边为0条。这表示本次运行中没有需要通过跨对象像素重叠进一步合并的对象，并不表示Consolidate模块未执行。
## 3. K8A：有效工作区域自动定位

**执行位置：** `src/detection/case03k8a_band_locator.py`  
**调用函数：** `locate_transmission_bands()`

K8A是自动检测链的第一项图像算法。其任务不是找疵病，而是回答：

> **这张RAW中哪些区域才是需要进行疵病检测的有效透射工作带？**

### 3.1 纵向稳健灰度轮廓

程序在图像中央76%宽度范围内稀疏采样：
- 纵向步长：4 px；
- 横向步长：12 px。

对每个采样行计算中位DN，经过一维高斯平滑，得到纵向灰度轮廓。

### 3.2 工作带判定

一个工作带必须同时满足：
- 存在明显亮平台；
- 上下两侧都有暗遮光谷；
- 峰值显著性不低于75 DN；
- 工作带宽度在170–1300 px；
- 工作带与暗遮光区对比度不低于90 DN；
- 相邻峰之间具有足够遮光分离。

因此顶部、底部的外部亮平台不会因为“亮”而被直接认作工作区。

### 3.3 工作带上下边缘

程序在约30个横向位置重新估计局部上下边缘，再进行稳健直线拟合。边缘拟合质量会检查：
- 有效边缘样本数；
- 中位残差；
- P90残差；
- 全宽倾斜量。

如果工作带数量、边缘质量或几何关系异常，后面的Two-Level计划不会把“未知区域”当作无疵病区域，而是进入全幅fallback。

### 3.4 输出

K8A输出：
- 工作带几何参数；
- `band_id_fullres.png`；
- `region_type_fullres.png`；
- `band_geometry.json`。

**图3-1说明：** 彩色边界为K8A在实际RAW上自动定位的工作带。后续高开销算法仅在这些工作带的安全扩展区域内运行；非工作区不会进入最终疵病报告。

---


![图3-1 K8A有效工作带定位](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/02_K8A_workband_localization.png)
**图3-1说明：** 彩色边界为K8A在原始RAW上定位的4条有效透射工作带。后续检测仅在这些工作带对应的有效区域内进行。
## 4. Two-Level ROI：从工作带生成安全检测区域

**执行位置：** `src/detection/two_level_roi.py::build_plan()`

K8A得到工作带后，程序不会直接用严格WORK_CORE裁切图像，而是先根据所有后续算法的空间支持范围计算安全扩展量。

### 4.1 最大算法依赖半径

当前代码综合考虑：
- Black-Hat最大结构元；
- Gaussian22；
- Closing61；
- F阶段RAW环带；
- G结构保护；
- H阶段DoG；
- J1/J2断裂关联；
- J4 halo；
- K8D 128×128 RAW窗口；
- 最终RAW Recovery背景环带。

当前最大依赖半径为：

```text
algorithm_halo_px = 93 px
```

再加：

```text
review_margin_px = 12 px
```

形成保守检测几何。

### 4.2 保留原始J4网格

J4的core固定为256×256 px。Two-Level ROI不是重新定义一套Tile，而是从原始全幅网格中选择与安全检测矩形相交的Tile。

因此：
- Tile坐标系不变；
- J4算法不因ROI优化而改变；
- 只是跳过与工作带无关的Tile。

以26_1当前运行结果为例：

| 项目 | 数值 |
|---|---:|
| 全幅J4 Tile数 | 1620 |
| 实际计划Tile数 | 765 |
| 跳过Tile数 | 855 |
| ROI模式 | K8A_WORK_ROI |

### 4.3 fallback原则

以下任一情况出现时，不允许把未识别区域解释为“无疵病”：
- 未找到工作带；
- 工作带数量异常；
- 边缘拟合不可信；
- 工作带几何异常；
- 工作区面积比例异常；
- 工作带互相重叠。

此时检测计划切换到全幅fallback。

---


![图4-1 Two-Level ROI与J4 Tile计划](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/03_TwoLevel_ROI_tile_schedule.png)
**图4-1说明：** 绿色矩形为安全扩展后的检测区域，细网格为原始256×256 J4 core网格。实际调度765个Tile，未调度855个Tile；ROI只减少计算范围，不改变原始Tile坐标。
## 5. ROI五尺度Black-Hat暗缺陷增强

**执行位置：** `src/detection/two_level_roi.py::compute_fused()`

疵病在明场透射图中主要表现为灰度下降，因此主增强响应采用黑顶帽：

```text
BlackHat = Closing(I) - I
```

### 5.1 多尺度响应

当前结构元直径：

```text
3, 5, 9, 15, 31 px
```

统一使用椭圆结构元。五个尺度分别计算Black-Hat后逐像素取最大值：

```text
R(x,y) = max(R3, R5, R9, R15, R31)
```

这样既保留小暗点，也覆盖更宽的暗斑和细长结构。

### 5.2 ROI计算不允许零填充

ROI模式只减少计算范围，不改变局部卷积输入。每个512 px计算块都会从真实RAW读取额外32 px上下文，避免ROI边缘因零填充产生虚假黑顶帽响应。

### 5.3 65535未计算哨兵

`fused_blackhat.npy`初始化为65535。由于原始有效数据只有12 bit，65535不可能成为合法Black-Hat值。

因此：
- 已计算区域写入真实Black-Hat响应；
- 未计算区域保持65535；
- 任何J4或K8B如果误读取65535，`require_computed_response()`立即抛错。

这是一道运行时硬门禁，防止未来ROI参数修改后把“未计算区域”误当作背景。

**图5-1说明：** 图片进行了显示拉伸，仅用于观察暗响应空间分布；定量检测始终使用原始uint16 Black-Hat DN值。

---


![图5-1 五尺度融合Black-Hat响应](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/04_ROI_multiscale_BlackHat_response.png)
**图5-1说明：** 显示实际计算得到的3、5、9、15、31 px五尺度Black-Hat逐像素最大融合响应。灰黑区域为未计算哨兵区域，定量处理仍使用原始uint16响应。
## 6. J4：工作区Tile内部疵病检测

**执行位置：** `scripts/run_case03j4_fullscan.py`

J4负责把高分辨RAW和Black-Hat响应转化为局部疵病对象。每个计划Tile独立处理。

### 6.1 Tile几何

| 参数 | 数值 |
|---|---:|
| core | 256×256 px |
| halo | 64 px |
| 实际局部工作窗口 | core + 周围真实RAW上下文 |

算法在core+halo窗口中运行，但只将core区域结果归属于当前Tile，因此不同Tile的源像素不会重复计面积。

### 6.2 J4调用的核心检测顺序

`run_tile()`中调用：

```text
process_one(local_RAW,
            fused_BlackHat,
            low=170,
            high=230,
            ...)
```

实际内部顺序是：

```text
Black-Hat固定双阈值H170/230
        ↓
H种子约束的Gaussian / Closing轮廓补充
        ↓
F：RAW局部背景/灰度证据
        ↓
G：邻近结构保护
        ↓
H：DoG暗核与候选筛选
        ↓
得到局部源Mask
        ↓
J1：Tile内部碎片关联
        ↓
J2：连续划痕/线状结构重构
```

其中170/230的作用是：
- 230 DN：强响应种子；
- 170 DN：与强种子连通的弱响应支持区域。

Gaussian/Closing不是独立造新候选，而是在已有H种子约束下补充边界。

### 6.3 J1/J2只改变对象关联，不虚增测量面积

J1/J2允许把方向一致、空间连续的碎片关联成一个显示对象；但代码明确保存：
- 原始源像素Mask；
- inferred bridge像素；
- 对象成员关系。

推断桥接像素不计入疵病面积。

### 6.4 J4输出

J4保存：
- 每个Tile的源标签Mask；
- Tile对象CSV；
- Tile状态；
- 全局未合并预览。

26_1当前ROI运行：
- 765个Tile全部执行；
- 产生698个J4局部对象。

**图6-1说明：** 这是J4局部对象的全局预览，此时还没有完成跨Tile对象合并。



---


![图6-1 J4全幅Tile局部源Mask](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/05_J4_fullframe_source_mask.png)
**图6-1说明：** 绿色为J4各Tile输出的精确源像素，红框标出J4中大/中对象的局部BBox；此时尚未进行跨Tile全局合并。

![图6-2 J4代表Tile内部处理结果](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/06_J4_tile_internal_stages_T011_007.png)
**图6-2说明：** 选取实际执行的T011_007 Tile，依次展示RAW core、融合Black-Hat、J4源Mask、J1分组源Mask、J2推断桥接和J2连续显示Mask。推断桥接像素不计入源面积。
## 7. J5：跨Tile全局对象合并

**执行位置：** `scripts/run_case03j5_global_merge.py`

J4只知道每个Tile内部的对象。J5负责把跨Tile边界的同一物理结构重新关联成全局候选对象。

### 7.1 J5输入原则

J5不重新执行：
- Black-Hat；
- H170/230；
- Gaussian/Closing；
- F/G/H；
- J1/J2。

它只读取J4已经确定的源Mask和对象成员关系。

### 7.2 跨Tile直接连接

相邻Tile的对象如果在全局坐标中具有8邻域直接连接，则优先建立确定性连接。

这是最强的跨Tile关系，因为不需要推测中间缺失像素。

### 7.3 间隔关联假设

对于没有直接接触、但可能属于同一条线状疵病的碎片，J5会综合：
- 候选之间的几何间隔；
- 方向一致性；
- 线状结构特征；
- RAW/DoG桥接证据；
- 是否存在竞争连接。

只有满足条件的间隔关联才会合并，并保留审计记录。推断的桥接区域仍不计入测量面积。

### 7.4 全局Union-Find合并

所有被接受的跨Tile边通过Union-Find形成全局对象。全局对象面积定义为：

```text
global source area
= 所有成员J4源像素面积之和
```

如果对象跨多个Tile，最大Feret长度使用所有成员源像素的凸包重新计算。

### 7.5 26_1当前ROI运行结果

| 项目 | 数值 |
|---|---:|
| J4局部对象 | 698 |
| J5全局候选对象 | 687 |
| 源面积合并前 | 20,963 px² |
| 源面积合并后 | 20,963 px² |
| 跨Tile对象 | 8 |
| 接受的跨Tile连接 | 11 |
| 其中直接源像素连接 | 11 |
| 间隔推断连接 | 0 |

面积在J5前后保持不变，说明跨Tile合并没有创造新的测量像素。

**图7-1说明：** J5已经完成跨Tile全局合并，但此时这些仍是算法候选对象，不等价于人工确认真值。

---


![图7-1 J5跨Tile全局对象合并](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/07_J5_global_objects_cross_tile_merge.png)
**图7-1说明：** 青色为J5全局候选源像素，红色为跨Tile对象。当前运行将698个J4局部对象归并为687个J5全局对象，其中8个对象跨Tile，接受11条直接源像素连接。
## 8. fresh_j5：从J5全局对象形成主检测支路

**执行位置：** `scripts/run_unified_raw_input.py::fresh_j5()`

J5会输出所有全局候选，但最终主检测支路并不是把全部J5对象直接写入最终结果。

程序先根据K8A的工作带ID，为每个J5对象确定：
- 是否位于有效工作区；
- 所属工作带；
- 原J5尺寸等级；
- 面积、Feret和BBox。

随后调用生产选择逻辑。

### 8.1 中大对象

J5中位于有效工作区且尺寸等级为：
- MEDIUM；
- LARGE；

的对象进入主检测候选集合。

### 8.2 方向性小划痕保护

部分小面积划痕可能因为面积不大而被分为SMALL。为了避免细长划痕仅因面积小而被丢弃，程序额外保留：

```text
最大Feret ≥ 10 px
且
BBox长宽比 ≥ 1.6
```

的方向性SMALL对象。

因此J5支路的策略不是简单的“只保留中大面积对象”，而是：

```text
中大对象
+
具有明确方向性的较长小划痕
```

### 8.3 精确源Mask重建

被选中的J5对象不会使用显示框当作Mask。程序根据J5成员表回到J4源标签Mask，将该全局对象的所有J4源像素重新OR到一起。

最终得到的J5候选Mask仍然是像素级源Mask。

---


![图8-1 fresh_j5主检测支路筛选结果](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/08_fresh_j5_selected_main_branch.png)
**图8-1说明：** 该图仅显示fresh_j5实际选入主支路的精确源Mask：MEDIUM/LARGE对象以及满足方向性条件的较长SMALL划痕。当前26_1纯自动重放选入26个对象。
## 9. K8B：分工作带补充候选生成

**执行位置：** `scripts/run_unified_raw_input.py::fresh_b()`  
**算法文件：** `src/detection/case03k8b_perband_trial.py`

J5主支路主要继承固定170/230检测结果。K8B的作用是处理不同工作带亮度差异，补充固定阈值可能遗漏的暗弱候选。

### 9.1 每个工作带独立统计

在每条K8A工作带的WORK_CORE内，对融合Black-Hat响应稀疏采样，计算：
- 中位数；
- MAD稳健尺度；
- 工作带RAW中位DN。

选择RAW中位DN最高的工作带作为参考带。

### 9.2 A固定分支

A分支继续使用：

```text
low = 170 DN
high = 230 DN
```

用于标识与主固定阈值体系已经重叠的候选。

### 9.3 B分工作带阈值

B分支把参考工作带的170/230转换成稳健Z分数，再转移到其他工作带，得到每个工作带自己的low/high阈值。

随后执行滞后分割：
1. 所有`response >= low`像素形成低阈值连通域；
2. `response >= high`提供强种子；
3. 只有含高阈值种子的低阈值连通域被保留。

K8B输出完整的`B_SOURCE_ALL.png`，每一个B连通域都有唯一源ID。

### 9.4 K8B不会直接判定最终疵病

K8B只负责补充候选。所有候选会继续进入K8C证据分类，并且原始B源Mask始终保留在来源记录中。

**图9-1说明：** 为了能够在全幅预览中看清，图中只绘制面积不小于40 px²的K8B源候选BBox；完整B源Mask仍保存在各工作带`B_SOURCE_ALL.png`中。该图只是候选空间分布，不是最终疵病结果。

---


![图9-1 K8B分工作带候选源Mask](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/09_K8B_perband_B_source_candidates.png)
**图9-1说明：** 黄色为分工作带B支路新增候选，青色为与固定A分支存在像素重叠的候选。图中覆盖全部16,766个K8B连通域，按工作带分别统计。
## 10. K8C：利用RAW局部证据对K8B候选分流

**算法文件：** `src/detection/case03k8c_noise_review.py`

K8C不重新生成候选，而是对K8B每个连通域补充RAW证据，并决定哪些候选有资格继续进入K8D。

### 10.1 与固定A分支的关系

如果B候选与A固定170/230候选有像素重叠，则分类为：

```text
EXISTING_FIXED_H
```

表示它不是K8B独立新增的候选。

### 10.2 微小候选

面积1–2 px²：

```text
MICRO_HIDE_SUGGESTION
```

注意这里是“建议降低显示优先级”，不是删除源候选。原始像素仍然保存。

面积3–7 px²：

```text
MICRO_REVIEW
```

同样不会自动判为噪声。

### 10.3 局部RAW背景环带

对于需要评价的候选，围绕候选真实形状构造局部背景环带：
- 内半径：6 px；
- 外半径：24 px；
- 最少有效背景像素：70；
- 排除其他B候选；
- 排除非工作区。

计算候选RAW中位数与背景RAW中位数之差。

### 10.4 MAD显著性和DoG暗核

K8C同时计算：
- RAW相对暗度；
- 局部背景MAD显著性；
- DoG暗核P90；
- 到工作带边缘的距离。

当前PROMISING条件主要为：
- 面积≥8 px²；
- RAW相对暗度≥7%；
- MAD显著性Z≥2；
- DoG暗核P90≥3 DN；
- 不处于边缘复核区。

满足时分类：

```text
PROMISING_DARK_REVIEW
```

证据不足但不能否定时：

```text
UNCERTAIN_REVIEW
```

### 10.5 真正进入K8D的条件

当前生产代码进一步要求：

```text
candidate_area >= 40 px²
且
classification ∈ {PROMISING_DARK_REVIEW,
                  UNCERTAIN_REVIEW}
```

才会进入K8D RAW外围处理。

其余候选不进入最终B补充对象，但源记录仍保留在`ALL_SOURCE_DISPOSITIONS.csv`。

---


![图10-1 K8C局部RAW证据分类结果](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/10_K8C_RAW_evidence_classification.png)
**图10-1说明：** 对K8B全部候选进行RAW局部对比度、MAD显著性、DoG暗核及边缘距离评价后的空间分类图。颜色对应PROMISING、UNCERTAIN、BOUNDARY、MICRO、EXISTING_FIXED_H等分类；顶部给出各类数量。
## 11. K8D：RAW外围稳定性恢复

**执行位置：** `fresh_b()`  
**算法文件：** `src/detection/case03k8d_group_stability.py`

通过K8C和面积门限的B候选，在候选中心附近提取128×128 RAW局部窗口。

### 11.1 三档RAW外围

调用`raw_outer_envelope()`，依次计算：
- 3 MAD；
- 2 MAD；
- 1.5 MAD；

三档RAW暗响应外围。

其目的不是无条件把候选扩大，而是寻找从严格到宽松逐步变化、且保持几何稳定的暗区域边界。

### 11.2 3 MAD严格源锚

首先要求3 MAD外围对原B seed有至少60%覆盖。

若3 MAD没有可靠源锚，则：

```text
SOURCE_ONLY_UNRELIABLE_3MAD
```

最终仍使用原始B seed，不允许1.5 MAD的大面积响应直接覆盖它。

### 11.3 逐级放宽的稳定性条件

3→2 MAD和2→1.5 MAD分别检查：
- 面积增长；
- 边界嵌套损失；
- 最大外围面积2000 px²；
- 形状长短轴比；
- seed支持率；
- 是否越出WORK_CORE；
- 是否触及128×128窗口；
- 是否触及RAW搜索半径上限。

当前面积增长上限：
- 3→2 MAD：1.35；
- 2→1.5 MAD：1.25。

### 11.4 K8D稳定状态

可能得到：
- `STABLE_SINGLE_OUTER_REVIEW`；
- `STABLE_GROUP_OUTER_REVIEW`；
- `AMBIGUOUS_FULL_OUTER_REVIEW`；
- `CENSORED_FULL_OUTER_REVIEW`；
- SOURCE_ONLY类状态。

在当前生产自动链中，只有：

```text
reason.startswith("STABLE_")
且
outer_area <= 8 × source_area
```

时，K8D外围才真正替代原始B seed。

否则仍使用原B源Mask。

**图11-1说明：** 黄色像素为原B seed，青色边界为K8D计算的RAW外围。是否最终采用该外围还要继续经过稳定状态和8倍增长门限。

---


![图11-1 K8D三档RAW外围稳定性示例](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/11_K8D_RAW_outer_stability_examples.png)
**图11-1说明：** 上半部分为稳定外围示例，下半部分为被截断/不稳定的外围示例。分别显示原始seed、3 MAD、2 MAD、1.5 MAD及K8D选择的外围。CENSORED示例的外围仅供判读，生产代码不会将其替代原始seed。
## 12. J5主支路与B补充支路汇合

完成`fresh_j5()`和`fresh_b()`后，自动检测获得两类候选：

```text
J5支路：
固定阈值 → J4 → J5 → 中大/方向性划痕

B支路：
K8B → K8C → K8D → 暗弱补充候选
```

两条支路在这里汇合。

对于一张新的RAW：
- 不加载任何历史人工复核结果；
- 不加载人工批准Mask；
- 不根据人工坐标创建新种子。

后续处理只依据当前RAW自动产生的J5/B候选。

---


![图12-1 J5与B两条自动支路汇合](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/12_J5_B_branch_fusion.png)
**图12-1说明：** 左为fresh_j5选出的26个J5主支路对象，中为K8B–K8D产生的12个补充对象，右为两支路汇合后的38个候选对象。三幅图采用相同RAW坐标和显示尺度。
## 13. Unified RAW Recovery：受限的二次RAW恢复

**算法文件：** `src/detection/unified_raw_recovery.py`

K8D是单个B候选局部128×128范围内的外围恢复。Unified RAW Recovery进一步检查多个邻近B候选是否能被同一个RAW暗连通区域统一解释。

### 13.1 哪些对象参与

只处理：
- B支路对象；
- 同一工作带；
- 未人工批准对象。

对于新RAW，所有对象本身均来自自动算法。

### 13.2 同带邻近候选分组

如果两个B对象：
- 属于同一工作带；
- BBox间距≤36 px；

则先放入同一个RAW恢复试验组。

这一步只是建立试验组，不直接把对象合并。

### 13.3 局部背景估计

围绕源候选联合Mask建立背景环带：
- 内距离：44 px；
- 外距离：68 px；
- 至少500个同工作带背景像素。

单源/普通候选使用稳健背景平面；多源细长结构使用较大尺度Gaussian背景，以降低单平面模型对长结构的不适配。

### 13.4 RAW残差阈值

计算：

```text
residual = background - GaussianBlur(RAW, sigma=1.3)
```

背景环带中得到稳健中心和MAD尺度，最终阈值：

```text
threshold =
max(background_center + 3 × sigma,
    0.15 × source_peak)
```

### 13.5 共享RAW连通域

候选RAW暗响应必须满足：
- 同一个RAW连通分量覆盖组内每个source；
- 每个source覆盖比例≥90%；
- 不越出当前工作带core；
- 不达到距离source 40 px的扩张上限；
- 不触及局部ROI边界；
- 最短轴≤48 px；
- 最终面积≤10000 px²；
- 最终面积≤8×源联合面积；
- 不与其他已存在对象发生冲突。

全部通过后，才用受限RAW恢复结果替换原候选组。

### 13.6 26_1纯自动示例

关闭历史人工注入的文档演示结果中：
- 进行了9个RAW Recovery组试验；
- 其中1个通过全部门限；
- 其余分别因增长过大、没有共享连通RAW分量或达到距离上限而拒绝。

拒绝不会删除源候选，而是继续保留进入恢复前的Mask。



---


![图13-1 Unified RAW Recovery接受案例](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/13_Unified_RAW_Recovery_before_after.png)
**图13-1说明：** 对同一工作带内4个相邻B源候选进行受限RAW恢复。源Mask联合面积为827 px²，满足共享RAW连通域、seed覆盖率、工作区和扩张限制后，恢复面积为3469 px²，新增支持像素为2642 px²。
## 14. Consolidate：全局像素级去重与同对象合并

**执行位置：** `scripts/run_case03_unified_final_detector_26_1_2.py::consolidate()`

J5支路和B补充支路可能对同一个暗结构产生重叠Mask，因此最终输出前还需要一次全局像素级整理。

### 14.1 只依据真实像素交叠，不依据BBox接近

程序只在：
- 同一工作带；
- 两个对象精确Mask存在像素交集；

时建立关系。

如果：

```text
overlap_px >= 3
且
overlap_px / min(area_A, area_B) >= 0.25
```

则认为两个候选很可能描述同一个疵病，执行并集。

如果有像素交叠但不足上述条件，则记录为：

```text
PIXEL_PARTIAL_CONFLICT_NOT_AUTO_MERGED
```

不会仅凭BBox距离自动合并。

### 14.2 同对象精确OR

被判定为同对象的候选使用布尔OR：

```text
final_mask = mask_A OR mask_B OR ...
```

来源UID取所有成员来源的并集，因此不会因为对象合并而丢失源候选追溯。

### 14.3 弱冲突的确定性像素归属

对于未达到自动合并条件、但仍有少量像素重叠的对象，程序按候选优先级顺序确定像素所有权：

```text
先处理高优先级/大Mask对象
↓
后处理对象删除已被前面对象占用的重叠像素
↓
保证最终对象Mask两两不重叠
```

因此最终面积不会重复计数。

---


![图14-1 Consolidate前后像素级去重](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/14_Consolidate_pixel_dedup.png)
**图14-1说明：** 左为RAW Recovery后的35个对象，右为Consolidate后的35个最终对象。本次纯自动示例没有检测到跨对象像素重叠边（0条关联边），因此对象数量保持不变；图中仍展示了合并前后Mask的实际空间分布。
## 15. 精确Mask、尺寸计算和尺寸分级

**执行位置：** `scripts/run_unified_raw_input.py::export()`

Consolidate完成后，每个最终对象重新从其精确二值Mask计算几何量。

### 15.1 面积

```text
Area = 最终Mask中True像素数量
```

显示框大小不参与面积计算。

### 15.2 最大Feret长度

程序获取最终Mask中的像素中心坐标，调用：

```text
max_feret_centers_px()
```

计算像素中心集合的最大欧氏距离，作为最大Feret长度。

### 15.3 尺寸等级

程序使用统一的`SizeGradeConfig`，根据：
- 精确面积；
- 最大Feret长度；

重新确定SMALL / MEDIUM / LARGE。

最终等级不是继承某个上游候选的旧标签，而是基于最终Mask重新计算。

### 15.4 物理尺寸语义

当前`PIXEL_SIZE_UM=3.2`是探测器像元尺寸。滤光片直接贴近探测器时可作为当前检测条件下的像面当量参考，但工程中没有独立物面倍率标定。

因此本报告仍以：
- px；
- px²；

作为算法的基本测量单位。

---


![图15-1 最终精确Mask面积与最大Feret测量](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/15_Final_mask_measurement_example.png)
**图15-1说明：** 以最大面积对象为例，左为RAW局部图，中为参与测量的精确二值Mask，右为Mask叠加图。该对象面积7657 px²，最大Feret长度106.57 px，分级为LARGE；蓝线表示最大Feret端点连线。
## 16. 最终显示：1.5倍矩形框，不绘制疵病Mask轮廓

**执行位置：** `src/visualization/unified_final_boxes.py::render()`

最终用户图与算法测量Mask严格分离。

### 16.1 背景图

原RAW按4倍步长缩小显示，并使用面积平均进行降采样，避免简单抽点导致小暗点受采样相位影响。

显示灰度采用1%–99.5%百分位拉伸，仅影响可视化，不进入疵病判定。

### 16.2 显示框

每个最终对象的精确BBox扩大：

```text
display_box_scale = 1.5
```

扩大的矩形框只用于观察，不改变：
- 精确Mask；
- 面积；
- Feret；
- 尺寸等级。

### 16.3 标注文字

每个框标注：

```text
Final ID
A = 面积 px²
L = 最大Feret px
```

标签布局函数会避让检测框和已经放置的标签。

### 16.4 不绘制Mask轮廓

当前正式用户图：

```text
mask_contour_drawn = False
```

只画矩形框和文字，不对疵病区域进行颜色填充，也不画最终Mask轮廓。

---


![图16-1 最终自动检测矩形框标注](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/16_Final_1p5_display_boxes.png)
**图16-1说明：** 这是生产自动链的最终用户显示图。矩形框按精确BBox扩大1.5倍，仅用于定位和浏览；面积、Feret及尺寸等级均由未扩大的精确Mask计算。

![图16-2 最终全幅精确二值Mask](PRODUCTION_AUTO_REPORT_20261106/assets_stagewise/17_Final_exact_binary_mask.png)
**图16-2说明：** 白色像素为最终用于面积和最大Feret计算的全分辨率Mask。该Mask与图16-1的1.5倍显示框相互独立。
## 17. 纯自动链结果示例：26_1关闭历史人工注入

为了保证示例只体现生产自动算法，本报告单独生成了一份不加载任何历史人工记录的结果：

```text
PRODUCTION_AUTO_REPORT_26_1_NO_HISTORY_20261106
```

该示例：
- 复用当前源码已经成功运行得到的K8A、ROI Black-Hat、J4、J5自动结果；
- 重新执行`fresh_j5`、K8B、K8C、K8D、Unified RAW Recovery、Consolidate和Export；
- **不加载历史人工批准Mask；**
- **不加载历史人工负例；**
- `human_confirmed_darkspot`全部为False。

这不是新的人工验收结果，而是为了说明“如果把同一RAW当成新图像，纯自动链会输出什么”。

### 17.1 中间候选统计

| 项目 | 26_1纯自动示例 |
|---|---:|
| J5源记录 | 687 |
| K8B源记录 | 16,766 |
| 自动来源记录总数 | 17,453 |
| K8D RAW试验 | 12 |
| Unified RAW Recovery试验 | 9 |
| RAW Recovery通过 | 1 |

K8C分类：

| 分类 | 数量 |
|---|---:|
| MICRO_HIDE_SUGGESTION | 11,524 |
| EXISTING_FIXED_H | 3,008 |
| MICRO_REVIEW | 2,086 |
| UNCERTAIN_REVIEW | 115 |
| BOUNDARY_REVIEW | 20 |
| PROMISING_DARK_REVIEW | 13 |

这些数字是源候选数量，不等于真实疵病数量。

### 17.2 最终自动结果

| 指标 | 数值 |
|---|---:|
| 最终对象数 | **35** |
| 最终精确Mask总面积 | **20,059 px²** |
| LARGE | 18 |
| MEDIUM | 16 |
| SMALL | 1 |
| 最小最大Feret | 10.44 px |
| 最大最大Feret | 189.97 px |
| 历史人工批准对象 | **0** |

**图17-1说明：** 该图仅使用自动算法候选，不包含任何历史人工批准结果。框扩大1.5倍用于显示，尺寸来自精确Mask。

**图17-2说明：** 白色像素为最终用于面积和Feret计算的精确疵病Mask。它与图17-1的扩大显示框是两个不同概念。

---

## 18. 生产自动检测的主要输出文件

每次`roi-bh`运行都会在独立输出目录中保存结果。

### 18.1 工作区与增强层

| 文件 | 内容 |
|---|---|
| `band_geometry.json` | K8A工作带几何 |
| `band_id_fullres.png` | 每像素工作带ID |
| `region_type_fullres.png` | WORK/EDGE/NONWORK区域类型 |
| `detection_plan.json` | Two-Level ROI与Tile计划 |
| `fused_blackhat.npy` | uint16多尺度Black-Hat融合响应 |

### 18.2 J4/J5

| 目录/文件 | 内容 |
|---|---|
| `upstream_J4/fresh/tile_masks/` | J4各Tile精确源标签Mask |
| `upstream_J4/fresh/j4_unmerged_tile_objects.csv` | J4局部对象 |
| `upstream_J5/fresh/global_defects.csv` | J5全局候选 |
| `upstream_J5/fresh/global_object_membership.csv` | J5与J4成员关系 |

### 18.3 K8B/K8C/K8D

| 目录/文件 | 内容 |
|---|---|
| `upstream_K8BCD/bandXX/B_SOURCE_ALL.png` | 每个工作带完整B源Mask |
| `upstream_K8BCD/thresholds.json` | 各带K8B阈值 |
| `upstream_K8BCD/RAW_trials.csv` | K8D RAW外围试验状态 |
| `upstream_K8BCD/*_RAW_trials.npz` | seed、3/2/1.5 MAD和选定外围 |

### 18.4 最终结果

| 文件 | 内容 |
|---|---|
| `FINAL_DEFECTS_AND_MEASUREMENTS.csv` | 每个最终对象的面积、Feret、BBox、等级、来源 |
| `EXACT_FINAL_BINARY_MASKS/*.npz` | 每个最终对象的精确二值Mask |
| `01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK.png` | 全幅最终二值Mask |
| `00_FINAL_DEFECTS_ONLY_fullframe_1to4.png` | 用户最终矩形框图 |
| `ALL_SOURCE_DISPOSITIONS.csv` | J5/B所有源候选的最终去向 |
| `RAW_recovery_gate_audit.csv` | Unified RAW Recovery每次试验的接受/拒绝原因 |
| `association_edges.csv` | J5/B候选全局像素关联关系 |
| `render_layout_audit.csv` | 显示框和文字布局记录 |

---

## 19. 当前生产自动算法的边界

本节只说明代码当前客观边界，不引入测试或人工审查内容。

### 19.1 只报告有效工作区

K8A有效工作区之外的缺陷不进入生产疵病报告。这符合当前业务要求：

> **只检测滤光片有效工作区域，工作区之外的疵病不报告。**

### 19.2 K8B补充支路仍有面积门限

当前只有K8C为PROMISING/UNCERTAIN且源面积≥40 px²的B候选进入K8D。

因此自动算法对很弱、很小但最终可能形成较大暗斑的种子仍存在保守门控。这是当前生产代码的真实行为，应在后续算法修订时单独处理，不能在文档中隐藏。

### 19.3 K8D稳定外围还有8倍增长限制

即使K8D内部得到STABLE外围，当前`fresh_b()`仍要求：

```text
outer_area <= 8 × source_area
```

否则回退到原B seed。

### 19.4 自动检测结果不是人工真值

生产算法输出的是自动检测结果。没有独立完整真值标注时：
- 最终对象数不是“真实缺陷总数”；
- 不能由该运行直接计算Precision/Recall；
- 尺寸单位首先应理解为探测器像素测量结果。

这些限制不改变算法流程本身，但决定了结果解释边界。

---

# 20. 结论

当前DefectDetectionProject面向新RAW的生产自动疵病检测主链可以归纳为：

```text
K8A工作带定位
→ 安全ROI计划
→ 五尺度Black-Hat
→ J4局部检测
→ J5跨Tile合并
→ J5主候选筛选
→ K8B分带补充
→ K8C RAW证据分流
→ K8D受限外围恢复
→ J5/B候选汇合
→ Unified RAW Recovery
→ 像素级Consolidate
→ 精确Mask测量
→ 1.5倍矩形框最终输出
```

该链条具备三个核心工程原则：

1. **只在有效工作区报告疵病，但ROI边界保留足够真实RAW上下文，不以零填充替代。**
2. **候选生成、轮廓恢复和对象合并均以精确源Mask为基础，显示框不参与面积测量。**
3. **任何被排除或未进入最终对象的源候选仍保留来源记录，不允许静默丢失。**

本报告至此结束。后续如果修改生产算法，应按本报告的实际调用顺序更新对应章节，不再把历史试验、人工确认和独立测试内容插入主流程正文。
