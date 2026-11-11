# 大规模审计性能

Synthetic 50,000候选包含12345 FILTERED，其余REVIEW，3个source；固定初始几何引用，创建fixture不计入索引成本。使用tracemalloc记录索引、filter、search、sort、page及selection耗时和峰值内存增量；这是本机参考，不是算法精度或硬件通用承诺。
AuditViewModel O(N)索引/计数，query O(N+M logM)，额外空间为tuple/整数/键索引。局部图不参与build/query/sort/page。分页只暴露最多page_size行，50k记录没有50k Qt对象。
后台worker + GUI定时器心跳验证响应；图片方法被断言禁止，窗口Widget数量无增加。0/1/499/500/501/50000分页边界及12345筛选后的25页(500/页)覆盖。
tracemalloc使时间高于未跟踪运行；无极限速度承诺。最终提交后会重新记录性能证据。

