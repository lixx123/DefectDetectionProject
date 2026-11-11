# 当前结果统计口径

StatisticsViewModel无Qt Widget输出，返回dict/list。顶卡优先使用InspectionResult.statistics的total_defects与总面积，同时检查最终Defect数量、完整面积和、类型/尺寸/严重度/Band/ROI分组是否一致。发现不一致明确红字提示，不修复、不覆盖原值。未提供分组时提示由最终对象只读汇总；缺少任何分组面积时总和为None，不以0补齐。

分组仅最终Defect：尺寸SMALL/MEDIUM/LARGE（存在UNKNOWN也保留）、动态Band种子来自roi_info.band_list并保留未归属对象、类型None归未分类、ROI动态。数量/占比/面积/最大面积/最大Feret用原值聚合，最后格式化。Band中零对象Band保留，全部分组数和等于最终对象数；百分比分母同一最终集合，非零总数时和100%。

面积占比=存储总疵病面积/结果中VALID WORK区域pixel_count；不可确定或无有效正分母显示—，不使用整图面积替代。物理总面积优先存储字段，Calibration无效一律—，不读当前YAML重算历史。

两张图为尺寸等级数量、Band数量；表格同时提供数量、百分比、像素及物理面积、最大面积、最大Feret。卡片显示总数、像素/物理总面积、WORK占比、最大像素面积、最大Feret px。无结果提示暂无；0对象总数0、图表空、无除零，未知最大值—。

统计永远全量InspectionResult，不随检测页筛选改变，不混入REVIEW/FILTERED/historical candidates。无跨结果统计、没有Excel/PDF正式导出。
