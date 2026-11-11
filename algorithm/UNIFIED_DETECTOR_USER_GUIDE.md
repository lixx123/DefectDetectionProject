# 输入 RAW 自动标记疵病

入口为 `main.py`。也可把一个 RAW 文件拖到 `Run_Detection.cmd`，程序从头计算，
在 `outputs/UNIFIED_RAW_时间戳/` 新建结果。运行有错误时会明确报错，不覆盖旧结果。

## 当前支持的输入

与本工程相同采集格式：11276×9200，16bit大端容器，有效12bit，单文件207478400字节。
文件无头部。尺寸、位深、路径和算法参数位于 `config/user_config.py`。
普通8bit截图、JPG或不同格式RAW不能直接当定量输入；不自动猜字节序或物面比例。
工作区应为该滤光片的条带成像结构，波段数自动定位；其它结构尚未验证。

## 从输入图片完整运行

在工程目录的PowerShell执行：

```powershell
.\.venv\Scripts\python.exe main.py --case unified-final --fresh --input 'D:\疵病检测\疵病实测数据\260624批次表观（5片）\26 (1).raw' --run-id MY_UNIQUE_DETECTION_RUN
```

每次使用新的 `--run-id`；省略该参数会自动生成唯一时间戳。
只要提供 `--input` 就从RAW重新计算；`--fresh`可显式表达此意图。
实际执行 RAW检查→五尺度BlackHat→1620块J4（H种子、Gaussian/Closing、F/G/H、J1/J2）
→J5跨图块归并→K8A自动分带→K8B分带候选→K8C证据筛选→K8D安全RAW外围
→多源有界恢复→精确像素去重→面积/Feret→矩形标注。
全图扫描耗时取决于候选密度；可查看新目录 `J4_J5_execution.log`。
失败记录保留，不使用半成品宣称完成。

人工确认/否定记录仅在输入文件SHA256与已审查26帧完全一致时应用，
换文件名不影响内容鉴别；其他输入不会套用26号人工标签。
当前已验证范围是26_1和26_2。其余18张RAW未在本次自动推广。

## 快速复核既有26双帧

```powershell
.\.venv\Scripts\python.exe main.py --case unified-final --sample 26 --run-id MY_UNIQUE_FINAL_REVIEW
```

此模式复用经SHA256记录的既有J4/J5/K8上游掩膜，重新执行最终选择和原RAW恢复。
它也生成新目录，但不声称重新计算了上游。真实执行模式在 `execution_trace.json` 中。

## 结果怎么看

- `00_FINAL_DEFECTS_ONLY_fullframe_1to4.png`：仅矩形框、疵病ID、A、L。
- `FINAL_DEFECTS_AND_MEASUREMENTS.csv`：逐对象真实掩膜像素面积、最长Feret、来源。
- `EXACT_FINAL_BINARY_MASKS/`：无损mask与原图坐标，是尺寸计算的依据。
- `01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK*.png`：原分辨率二值分割。
- `ALL_SOURCE_DISPOSITIONS.csv` 或 `ALL_ORIGINAL_J5_AND_B_SOURCE_DISPOSITIONS_NO_DROP.csv`：全部原候选审计。
- `RAW_recovery_gate_audit.csv`：每次恢复成功/拒绝原因，阈值、覆盖与面积。
- `acceptance.json`：工程检查结果；物理效果仍待人工验收。

A为mask中前景像素数，包含轮廓内实际分割区域，扣除孔洞和重复像素；不是框的宽×高。
L为前景像素中心凸包的最大Feret跨度；不是弯曲中心线路径长度。
显示框可为mask bbox的1.5倍，只方便定位，不参与A/L计算。
未取得物面标定前，使用px/px²，不把探测器3.2μm直接当成样品物面尺寸。

当前规则输出的是自动判定候选。四处既有暗斑的人工确认独立保存，
不能由“程序测试通过”推导所有候选均为真疵病或无漏检。
