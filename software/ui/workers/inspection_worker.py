"""Existing QThread worker with classified user errors and full diagnostics."""
import logging
from PySide6.QtCore import QObject,Signal,Slot
from ui.runtime_log import ApplicationLog
from ui.runtime_errors import classify_error

class InspectionWorker(QObject):
    succeeded=Signal(object)
    failed=Signal(str)
    failed_detail=Signal(object)
    finished=Signal()
    def __init__(self,operation,log_path,*,application_log=None,kind='operation',operation_id=None):
        super().__init__();self.operation=operation;self.log_path=log_path
        self.application_log=application_log or ApplicationLog(log_path)
        self.kind,self.operation_id=kind,operation_id
    @Slot()
    def run(self):
        log=self.application_log
        try:
            log.event(logging.INFO,self.kind,'STARTED','后台操作开始',operation_id=self.operation_id)
            value=self.operation()
            # Some frozen display APIs intentionally degrade missing resources.
            # Preserve their messages and make the degraded state diagnosable.
            def warn(item):
                message=getattr(item,'message','') or ''
                if '不可用' in message:log.event(logging.WARNING,self.kind,'VIEW_RESOURCE_FAILED',message,operation_id=self.operation_id)
                frame=getattr(item,'frame',None)
                if frame is not None and frame is not item:warn(frame)
            if isinstance(value,tuple):
                for item in value:warn(item)
            else:warn(value)
            handled_failure=self.kind=='human_raw' and isinstance(value,tuple) and len(value)==5 and value[-1]
            if handled_failure:self.failed_detail.emit(classify_error(ValueError(value[-1]),self.kind))
            else:log.event(logging.INFO,self.kind,'SUCCEEDED','后台操作完成',operation_id=self.operation_id)
            self.succeeded.emit(value)
        except Exception as exc:
            failure=classify_error(exc,self.kind)
            log.event(logging.ERROR,self.kind,failure.code,'后台操作失败',exc=exc,operation_id=self.operation_id)
            self.failed_detail.emit(failure)
            suffix=' 日志文件暂不可写，请检查磁盘和权限。' if log.write_failed else ''
            self.failed.emit(failure.user_message+suffix)
        finally:
            self.operation=None
            self.finished.emit()
