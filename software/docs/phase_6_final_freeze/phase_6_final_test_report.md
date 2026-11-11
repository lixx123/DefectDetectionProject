# Phase 6 最终自动测试

全部388 PASS；FAST359 PASS；GOLDEN27 PASS；RELEASE PASS；smoke与pip check PASS。无失败、错误、skip。原始命令、JUnit、日志在当前目录与gates/。

从367/339/26调整为388/359/27：一项依赖外部RAW的Golden移到专项工具，原位置加入两项梯度synthetic Golden（净+1），另加20项扫描、CLI和流式SHA检查。旧其余测试和断言未改，六组检测语义Golden与两个正式Repository包仍覆盖。没有以减少覆盖或跳过测试绕过失败。

普通门禁未提供真实数据路径，并受外部RAW禁读审计保护；专项真实RAW在它们完成后显式运行、SHA匹配、算法执行0。GUI与冻结层零diff。人工验收仍待用户确认，Phase7未开始。
