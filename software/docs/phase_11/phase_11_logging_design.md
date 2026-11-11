# Phase11 日志设计

沿用默认 output/runtime/gui_errors.log，其他显式runtime_root下采用同一相对文件名。统一 ApplicationLog 适配器以Python logging/RotatingFileHandler写UTF-8；每文件1MiB，3份备份。单handler锁保证UI/worker多线程写入不交错；不使用第三方日志框架或print。

INFO：STARTED/SUCCEEDED/APPLICATION_CLOSED；WARNING：TASK_REJECTED、缺失资源降级、保存后RAW重新验证未通过；ERROR：分类异常及完整exc_info traceback。每条记录timestamp/level/operation/event/message，主任务携operation_id；RAW校验失败另记result_id。默认无DEBUG。稳定错误码和中文提示分离；UI只显示发生情况、影响和下一步，不直接暴露未知异常技术文本。

目录自动创建。创建/写入失败被明确标记write_failed，诊断退回stderr；正常任务仍完成，失败任务仍发error和finished，GUI提示日志不可写。日志不进入InspectionResult或审核JSON/CSV。算法audit_log、运行log、human review三条追溯链独立。

临时目录和合成RAW可出现在隔离QA原日志；发布回执副本使用可移植路径占位符，并保存原始/发布文件SHA256。冻结正式包CSV中的历史mask/成员表位置保持字节不变，不把历史算法追溯重写为运行日志。
