# Phase 7 UI 设计

主窗口增加检测、疵病详情、统计分析三个QTabWidget页。检测页沿用Phase6现有Viewer、表格、工具栏、后台服务和正式保存路径，不重写主Viewer。新增ui/models/defect_detail_view_model.py、statistics_view_model.py、defect_filter_model.py、selection_controller.py与两个widgets页。

SelectionController.defect_id是唯一共享选择；表格/框点击、详情翻页均通过该状态同步。详情字段立即更新，图像仅在详情页活动时异步读取；结果/Defect/mode/代次形成请求键，过期响应丢弃，后续仅处理最新请求。复用冻结InspectionController.submit与QThread生命周期，忙时不允许关闭或切换RAW来源。

统计聚合仅最终Defect，不读取candidate表；详情仅当前最终Defect的candidate IDs/merge history摘要，不建完整Audit页面。没有审核写回、正式报告导出、数据库、打包或Phase8实现。

沿用原配色、表格风格与只读交互。两张原生Qt自绘柱状图，无QtCharts/Web新依赖。切任务清理选择、过滤、详情图元、字段、统计和待处理图像请求。
