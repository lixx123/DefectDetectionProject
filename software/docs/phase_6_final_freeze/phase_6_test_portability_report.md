# 自动回归与真实数据验收解耦

tests/test_phase6_revision.py 不再引用真实大RAW，也不读取工程机器数据目录。Golden使用1000×800、big-endian uint16梯度fixture，DN=(3*x+5*y)%4096，检查多个局部像素及鼠标DN，覆盖ORIGINAL/FINAL、mask开关、z-order和模型零修改。

普通全部测试、FAST、GOLDEN及RELEASE以不含真实RAW参数的命令执行。验证用sitecustomize Python审计钩子向子进程继承，对任何测试输出目录之外的.raw打开操作抛PermissionError。各进程报告在raw_access_guard，汇总ordinary_gate_raw_independence.json；所有门禁PASS且外部访问尝试0。该hook仅用于本轮证明，不修改生产代码或门禁规则。

新增regression.machine_paths扫描五个指定源码目录，覆盖文本及AST字符串解码；测试验证正斜杠、反斜杠、转义Unicode/路径及用户目录路径均可检出。扫描器的驱动器/目录检测token分开存放，不持有任何可用的本机文件路径。历史文档和数据不扫描，源代码中没有例外豁免名单。

## 显式真实RAW验收

在工程根目录执行：

```powershell
python -m regression.reproduce_display_observation --raw-path "<真实26_1_RAW完整路径>" --output-dir "<新的专项证据目录>"
```

--raw-path必填，没有环境变量或源码路径fallback，不扫描磁盘。--repository与--result-id可显式选择冻结正式包；默认库位置相对工程根目录，非机器数据路径。缺路径时argparse exit2，不运行Qt、不查找RAW。输出目录需为新目录，避免覆盖历史证据。

stream_sha256每次读取1MiB，不使用path.read_bytes。显示前核对result.input_info.sha256，显示后复核RAW哈希及完整结果摘要；禁止Detector.inspect及引擎子进程。真实RAW路径只在CLI/运行时使用，不写InspectionResult、schema或Golden manifest。real_raw_display包含PASS、expected/raw SHA、CLI来源、DN、zoom、图元数、z序与两张截图。
