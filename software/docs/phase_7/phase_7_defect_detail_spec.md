# 详情页规格

五组字段：身份、几何形态、灰度光度、空间归属、检测审计摘要。数据来自Defect及本次Calibration；不重算面积、Feret、灰度、Band或ROI。None/UNKNOWN显示—，严重度独立于尺寸等级。Feret与面积有定义Tooltip。历史物理量读取存储值；invalid Calibration隐藏μm/μm²及物理坐标；非计量标定明确提示。

局部图取measurement bbox外40px并裁剪图像边界，最大400万像素。RAW可用直接复用RawImageProvider.crop读取真实像素；否则只读包内original_preview。均缺失显示局部原图不可用，以中性底图承载可用mask/框，不生成假灰度、不给preview冒充DN。

三模式：原始灰度、灰度+bbox、灰度+final mask+bbox。优先读取已验SHA的当前Defect NPZ mask，按既有measurement bbox放置；若无可用NPZ则读取结果final_mask PNG局部。只将已有前景可视化，不从mask重测geometry。路径限定包内且校验SHA。

局部scene坐标相对crop原点，状态栏转换回原始像素坐标；DN直接索引原RAW。局部显示Overlay使用相对坐标投影，右侧bbox/center永远为原始全局测量。mask独立图层、框独立图元，无数据写回。

身份/几何/光度/位置用分组Form展示；merge history使用固定高度只读文本区，防止长JSON撑乱布局。快速换对象先隐藏旧字段控件再deleteLater，避免事件循环处理删除前叠影。
