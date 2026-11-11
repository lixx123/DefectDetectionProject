# 筛选 / 排序 / 选择

DefectFilterModel继续包装原DefectTableModel，不复制领域Defect。SizeGrade、Band、Type三个轻量筛选可组合，清除恢复全部；未分类使用UNKNOWN内部键，显示为未分类。过滤只改变可见行与bbox，最终mask仍表示冻结全量结果，不对mask做业务修改。

ID字符串、面积/Feret数值、尺寸SMALL→MEDIUM→LARGE→UNKNOWN、数字Band自然数顺序可排序。统一selection.defect_id通过proxy映射source ID，不能依赖源行号或顺序ID代表物理位置。详情上一条/下一条严格按proxy当前可见排序移动，边界禁用；隐藏当前对象时清理或采用Qt当前有效可见行，不保留不可见对象详情。

Tab切换不改变全局对象。上一条/下一条在局部资源工作线程忙时禁用，完成恢复；主检测表格仍可快速选择，新请求按代次丢弃旧返回。统计页标题明确全量、不受筛选影响。

无结果空状态、单对象禁用两端、0对象暂无疵病。没有审核提交、删除、修改等级或算法判断入口。
