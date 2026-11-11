# DefectDetectionProject 核心检测链审计记录
## 26_1：ROI Black-Hat → H170/230 → H种子精修 → F/G/H → J4 → J1/J2 → J5

审查对象：
- 当前源码
- `outputs/K8A_TWO_LEVEL_FINALGUARD_26_1_ROI_BH_20261020_v2`
- 代表J4 tile：`T011_007`
- J1/J2示例：`T010_018_C0004`
- J5跨tile示例：`DEFECT_00649`

---

## 1. 注释修正

仅修正文档/注释，没有修改检测数值逻辑：

1. `src/detection/case03k8a_band_locator.py`
   - 删除“K8A independent only / no influence on BlackHat”旧描述。
   - 改为：K8A不改变Black-Hat数值和检测核，但在当前roi-bh中负责调度Black-Hat/J4计算区域；几何不可信必须full-frame fallback。

2. `scripts/run_case03j4_fullscan.py`
   - 删除“precomputed full-frame BlackHat”旧描述。
   - 改为：输入可以是full或ROI response；所有被消费的core+halo必须与全幅Black-Hat逐像素等价，并拒绝65535 sentinel。

3. `src/detection/case03t_hseeded_variable.py`
   - 说明该算法虽源于selected-window pilot，但当前已被J4复用到每个scheduled core+halo。

4. `scripts/run_case03t_threeway_comparison.py::process_one`
   - 将“recomputed on frame2”改为“recomputed on current core+halo RAW window”。

---

## 2. Black-Hat真实定义

`src/detection/blackhat.py`

每一尺度：

```text
BH_k = MorphologicalClosing_k(RAW) - RAW
```

输入必须为二维uint16原始DN，不允许8 bit显示图。

尺度：

```text
3 / 5 / 9 / 15 / 31 px
ellipse structuring element
```

多尺度最终response逐像素取最大。

ROI-BH只减少计算区域，不改变任何被消费像素的数学定义。

---

## 3. H170/230真实定义

`hysteresis_window()`

```text
support = BH >= 170
seed    = BH >= 230
```

在support上做8连通域，只保留至少含一个230高阈值seed像素的低阈值连通域。

没有面积阈值抑制。

因此：
- 170控制弱响应延展；
- 230提供强种子证据；
- H是后续主通道唯一独立候选源。

---

## 4. Gaussian22 / Closing61不是独立候选源

生产J4调用：

`detect_window_H_seeded()`

局部RAW先做3×3 median，然后：

### Gaussian22

```text
background = GaussianBlur(denoised RAW, sigma=22)
residual = max(background - denoised RAW, 0)
residual再GaussianBlur(sigma=0.85)
```

### Closing61

```text
background = MorphologicalClosing(denoised RAW, ellipse 61)
residual = max(background - denoised RAW, 0)
residual再GaussianBlur(sigma=0.85)
```

局部response阈值来自98%截尾后的median/MAD：

```text
high = max(65, median + 4.0*sigma)
low  = max(24, median + 1.8*sigma)
```

但Gaussian22/Closing61不能独立创建目标。

它们必须：
- 锚定在已有H连通域；
- H面积至少3 px才尝试精修；
- H锚点局部response至少比low高10 DN；
- 不允许连接到另一个有意义的H seed；
- 正常扩展限制在H周围12 px；
- 面积增长、窗口占比、边缘触碰均受限；
- unsafe情况下可尝试7 px bounded rescue，最大3倍面积。

原始H像素不得被精修删除。

---

## 5. 真实案例：T011_007 / F1_FINAL_0003

J4 core：

```text
T011_007
core = [1792,2816,2048,3072)
halo work = [1728,2752,2112,3136)
```

最终对象：

```text
F1_FINAL_0003
historical J5 = DEFECT_10333
current J5 = DEFECT_00265
J4 object = T011_007_C0001
area = 7657 px²
Feret = 106.5692 px
```

该tile全halo：

```text
H components = 84
BH>=230 seed pixels = 2425
H-seeded refined objects = 4
H-only objects = 80
```

core内：

```text
H pixels = 3346
H-seeded refined pixels before F/G/H gate = 7715
F/G/H hidden H pixels = 46
J4 final source pixels = 7663
```

J4最终7663 px由：
- 主对象7657 px；
- 6个独立1 px小对象；
组成。

因此不能把“tile总mask面积7663”误写成单个大疵病面积。

---

## 6. 主对象H精修的真实数值

主H：

```text
Hlocal_0020
H area = 3292 px
BH peak = 453 DN
S230 seed pixels = 2341
```

### Gaussian22

当前halo统计：

```text
background median = 3.679 DN
MAD sigma = 5.157 DN
low = 24 DN
high = 65 DN
```

该H锚点：

```text
H anchor local response peak = 329.34 DN
source low-component area = 5470 px
candidate area after bounded H neighborhood = 5471 px
added non-H pixels = 2179
status = accepted_H_seeded_extension
```

### Closing61

当前halo统计：

```text
background median = 47.263 DN
MAD sigma = 13.635 DN
low = 71.807 DN
high = 101.804 DN
```

该H锚点：

```text
H anchor response peak = 590.20 DN
source low-component area = 7871 px
candidate area after bounded H neighborhood = 7663 px
added non-H pixels = 4371
status = accepted_H_seeded_extension
```

最终该H对象：

```text
sources = H170_230 + gaussian22 + closing61
status = provisional_fused
flags = []
```

这说明在这个代表对象上：
- H170/230负责“发现”；
- Gaussian22/Closing61负责“补完整轮廓”；
- 并非Gaussian/Closing独立发现目标。

---

## 7. F/G/H真实门控语义

### F

面积≤5 px的小H候选做RAW局部统计：

```text
ring outer = 12 px
inner guard = 2 px
min background samples = 20
relative contrast threshold = 0.08
Z threshold = 3.0
sigma floor = 3 DN
```

大于5 px直接keep。

靠近≥30 px²大H结构3 px内的小候选被保护。

### G

若F认为弱小候选可隐藏，但满足：
- 已有Gaussian22/Closing61 H-seeded精修；
- 或靠近≥6 px H结构8 px内；

则升级为protected_review。

### H

只重新检查6~30 px、且G仍为keep的对象。

只有当：

```text
relative contrast < 0.06
AND
Z < 2.5
```

且没有以下保护证据时才hide：

```text
BH peak >=320 DN
DoG median >=16 DN
line length >=12 px and aspect >=3.5
near >=40 px² H within 5 px
```

---

## 8. T011_007门控状态

全halo 84个H候选：

```text
F:
 keep = 15
 suggest_hide = 68
 keep_review = 1

G:
 keep = 15
 hide_suggestion = 67
 protected_review = 2

H final:
 keep = 13
 hide_suggestion = 68
 protected_review = 3
```

触及256×256 core的35个H候选：

```text
H final:
 hide_suggestion = 27
 keep = 7
 protected_review = 1
```

被hide的H像素在core内合计只有46 px，说明这一tile的大量噪声来自极小点状H候选。

---

## 9. 重要审计发现：F/G/H“可逆”只在函数内成立

`build_joint_maps()`确实返回：

```text
h_original
h_kept_display
h_hidden_suggestion
fused_original
fused_joint_display
```

所以函数内部原H没有被原地删除。

但是J4正式输出NPZ当前只保存：

```text
source_detected_uint8
source_region_label_i32
grouped_source_only_i32
inferred_bridge_i32
continuous_display_i32
core_xyxy
```

其中 `source_detected_uint8` 就是门控后的 `fused_joint_display`。

因此：
- hide_suggestion不会进入J4/J5；
- 原始H和hidden mask没有持久化到当前J4产物；
- 对新RAW无法仅靠当前J4目录完整重建被隐藏H候选。

这不是当前26_1最终mask回归错误，而是当前版本明确接受的数据留存边界。

经项目决策，现阶段不增加H级candidate ledger，不持久化完整 `h_original`、`h_hidden_suggestion`、`fused_original`，也不逐点保存被抑制候选的坐标、轮廓和局部图像。原因是当前被抑制候选中包含大量极小点状响应，逐点留存会增加文件量和软件维护成本；目前尚无明确真实漏检案例证明该成本有必要。

需要如实保留以下限制：
- `hide_suggestion` 候选不会进入J4/J5正式对象链；
- 当前J4正式输出不能单独恢复这些候选的精确历史几何；
- `hide_suggestion` 是算法抑制状态，不等同于人工确认的背景噪声标签。

若后续发现真实疵病疑似被F/G/H误抑制，应保留对应原始RAW，并使用当时的Engine代码版本和参数配置重新运行，在问题区域临时导出H候选、F/G/H状态及原因。再根据实际证据决定是否调整规则，或增加长期候选审计输出。若原始RAW、代码版本或参数配置缺失，则不能保证完整重建历史候选。

因此，该事项记录为**后续改进项（按真实漏检案例触发）**，当前不作为V1.0冻结阻塞项；检测算法和软件界面均无需因本事项修改。

---

## 10. J1：tile内碎片关联

J1只分组，不填充gap。

关联不能只靠距离，要求：
- max gap = 18 px；
- piece area >=8 px；
- secondary length >=5 px；
- 需要较大core或短连接结构；
- piece DoG median >=12 DN；
- 方向容差38°；
- gap DoG median >=16 DN；
- positive fraction >=0.70。

J1输出的object map非零支持必须与原labels完全一致。

因此J1：
- 可改变对象ID归属；
- 不可增加测量像素。

---

## 11. J2：连续显示bridge

J2允许在已经有可靠划痕关联证据时生成显示bridge。

重要规则：

```text
bridge_half_width = 3 px
bridge_min_dog = 12 DN
```

bridge只能写入原source labels==0的位置，不能覆盖另一个source object。

J2输出明确分开：

```text
objmap = original source ownership
bridgeids = inferred bridge
combined = display only
```

测量：

```text
original_area_px2
original_max_feret_px
```

不包含bridge。

---

## 12. 真实J1/J2案例：T010_018_C0004

```text
source region members = 4;5
member_count = 2
source area = 103 px²
source max Feret = 20.2485 px
inferred bridge = 22 px
grade = MEDIUM
```

整个tile：

```text
source_detected pixels = 131
grouped source pixels = 131
inferred bridge pixels = 22
continuous display pixels = 153
```

因此：

> 22个J2 bridge像素只让显示更连续，不进入103 px²的测量面积。

对应图：
`REPORT_ASSETS_26_1/J1_J2_J5/05_J1_J2_T010_018.png`

---

## 13. J5：跨tile全局对象化

J5读取J4的 `grouped_source_only_i32`，不重新运行H、F/G/H、Gaussian/Closing。

### 直接连续

若跨seam最近source像素：

```text
gap <= sqrt(2)
```

即8邻域真实连续，直接接受。

不需要方向和DoG二次证明。

### 分离间隙

若gap>sqrt(2)，才需要：

```text
gap <=18 px
piece area >=5 px
至少一段 Feret >=12 px
aspect >=1.5
方向容差30°
gap DoG median >=16 DN
positive fraction >=0.70
```

若同一节点有两个距离相差<2 px的竞争gap候选，则全部否决为ambiguous。

---

## 14. 真实J5跨tile案例：DEFECT_00649

当前J5：

```text
DEFECT_00649
historical identity = DEFECT_10717
```

由：

```text
T020_018_C0001 = 123 px²
T021_018_C0001 = 624 px²
```

组成。

seam证据：

```text
p0 = (4663,5375)
p1 = (4663,5376)
gap = 1.0 px
direct_connected = true
reason = exact_8_neighbor_source_continuity
```

因此：

```text
global area = 123 + 624 = 747 px²
```

没有任何J5推断面积。

对应图：
`REPORT_ASSETS_26_1/J1_J2_J5/06_J5_DEFECT_00649_DIRECT_SEAM.png`

---

## 15. 26_1 J5总体数据

```text
J4 local objects = 698
J5 global objects = 687
source area before = 20963 px²
source area after = 20963 px²
objects spanning multiple tiles = 8

accepted seam links = 11
direct source continuity = 11
separated gap hypotheses = 0
```

因此26_1最新roi-bh运行中：
- J5确实进行了跨tile对象合并；
- 但全部11条接受边都是原source像素直接8邻域连续；
- 没有任何J5“隔空推断gap link”参与26_1结果。

---

## 16. 本阶段审查结论

当前核心检测数学链是自洽的：

```text
Black-Hat
→ H170/230发现
→ H-seeded Gaussian22/Closing61补轮廓
→ F/G/H抑制弱点噪声
→ J4 source mask
→ J1只分组
→ J2只生成不可测量bridge
→ J5跨tile只合并对象身份
```

面积守恒逻辑明确：
- J1不增加source pixels；
- J2 bridge不计面积；
- J5合并前后source area严格相等。

当前核心检测链的主要数值逻辑已完成本轮审查。F/G/H被hide的H候选没有在J4正式输出中逐点持久化，这是已识别并经项目确认接受的工程取舍，不是当前版本的检测算法整改项。若后续出现真实漏检案例，再按原始RAW、对应Engine版本和参数配置开展局部调试，必要时增加候选账本或临时Mask导出。

---

## 17. 版本/哈希注意

本轮只修改了源码注释和报告，没有修改检测数值逻辑。但源码文件SHA256已改变，因此此前 `FINALGUARD_..._v2` 的“source SHA at start == 当前源码”严格条件不再成立。

在最终V1.0冻结前，应在所有文档/注释整改完成后，用最终源码重新跑26_1/26_2 roi-bh并独立QA一次，刷新最终源码哈希证据；不建议每修一句注释就重复跑全流程。
