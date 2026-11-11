# Phase 6 最终显示细节设计

仅修改 ui/image_viewer.py、ui/main_window.py、ui/models/result_view_model.py；保持 MainWindow 现有布局、表格字段、颜色等级和稳定服务结构。

## 真实 RAW 局部

ORIGINAL 和 FINAL 均启用 detail_enabled，实际渲染还必须 raw_provider 存在、zoom≥0.7。使用既有只读 RawImageProvider.crop；按可见 scene 区域裁剪，在原始像素坐标定位。4,000,000 像素上限，超出保留 thumbnail。缩放、平移、1:1、定位和Fit 使用 30–40ms QTimer 防抖；鼠标移动只读一个 DN，不刷新 crop。旧 detail_item 先移除，换视图立即清除，不累计永久图元。

图层：thumbnail -10，RAW detail -9，final mask -8，普通框 +10，选中框 +15，编号/Band 标签 +20。mask 为独立图元，开关后 RAW 局部仍可出现。BAND/ROI 不启用 RAW detail，保留原视图逻辑。历史无 RAW 的 FINAL 继续中性底图+mask+框，DN —；不伪造灰度。

## 显示框

UI Overlay 明确分为 measurement_bbox 和 display_bbox。bbox 兼容只读属性仍表示 measurement_bbox，不能悄悄改变原语义。display_bbox 以原 measurement bbox 中心展开 1.5×，宽高分别至少6原始像素，再裁剪到[0,width]×[0,height]；边缘裁剪后允许小于6。6像素是图像坐标单位，不是屏幕像素。显示、编号和点击区域使用显示框；centerOn 请求原 measurement bbox 中心，避免clamp改变定位。表格和详情始终读取原 Defect.geometry，不写回任何 display 字段。

## 名称和冻结边界

窗口：滤光片表面疵病自动检测与分析软件 V1.0；QApplication 名称：滤光片表面疵病自动检测与分析软件。在 UI 初始化同步 QApplication，保持 app/main.py 字节不变，避免保守 app 路径规则要求真实重跑。没有修改门禁规则。

原 schema/Defect/InspectionResult/ROI/Band/Repository/AUTO/算法/Golden 一律保持。既有 mask 显示采样策略保持；本轮恢复的是高倍率真实 RAW 背景，不重算 mask。人工可独立关闭 mask 查看原始灰度；07截图用于这种复核。
