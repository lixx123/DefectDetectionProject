"""GUI orchestration through frozen service/repository APIs, never engine internals."""
from pathlib import Path
from app.runtime_paths import application_root
from tempfile import TemporaryDirectory
from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from application.inspection_service import InspectionService
from infrastructure.repositories import JsonResultRepository
from ui.workers.inspection_worker import InspectionWorker
from ui.models.result_view_model import ResultViewModel, ViewMode
from ui.raw_image_provider import RawImageProvider
from ui.models.human_review.evidence import FormalResultAuthority,validate_raw
from ui.models.human_review.model import digest,source_payload
from dataclasses import dataclass
from uuid import uuid4
import logging
from ui.runtime_log import ApplicationLog
from ui.runtime_errors import classify_error


@dataclass
class FormalSaveOutcome:
    record: object
    vm: object
    frame: object
    raw_binding: object = None
    raw_warning: str = ""
    ledger_warning: str = ""



class InspectionController(QObject):
    busy_changed = Signal(bool)
    completed = Signal(str, object)
    error = Signal(str)
    error_detail = Signal(object)
    status_changed = Signal(str)

    def __init__(self, repository=None, *, service_factory=None, runtime_root=None, parent=None):
        super().__init__(parent)
        root = application_root()
        self.repository = repository or JsonResultRepository(root / 'output/results')
        self.runtime_root = Path(runtime_root) if runtime_root else root / 'output/runtime'
        self.service_factory = service_factory or self._make_service
        import sys
        self.packaged_engine = bool(getattr(sys, "frozen", False))
        self.engine_ready = not self.packaged_engine
        self.engine_status = "检测引擎：开发 / 回归 Adapter" if self.engine_ready else "检测引擎：正在校验…"
        self._temporary = TemporaryDirectory(prefix='defect_gui_')
        self.staging = JsonResultRepository(Path(self._temporary.name) / 'results')
        self.formal_authority=FormalResultAuthority(self.repository,staging_root=self.staging.root)
        self.thread = self.worker = None
        self.busy = False
        self.task_state="IDLE"
        self.operation="idle"
        self.operation_id=None
        self.last_failure=None
        self.application_log=ApplicationLog(self.runtime_root / "gui_errors.log")

    def _make_service(self, repository):
        from application.engine_selection import create_detector
        return InspectionService(create_detector(self.runtime_root), repository)

    def check_engine(self):
        if not self.packaged_engine:return False
        def operation():
            from infrastructure.engines import EngineRegistry, EngineError
            try:
                manifest=EngineRegistry(application_root()).resolve()
                return True, "检测引擎："+manifest.data["engine_id"]+" v"+manifest.data["engine_version"]+" · 已就绪"
            except EngineError as exc:
                self.application_log.event(logging.ERROR,"engine_check","ENGINE_UNAVAILABLE",str(exc),exc=exc)
                return False, "检测引擎不可用，请安装或恢复兼容的检测引擎包。"
        return self.submit("engine_status",operation,operation_name="engine_check")

    def submit(self, kind, operation, *, operation_name=None):
        if self.busy:
            self.application_log.event(logging.WARNING,kind,'TASK_REJECTED','已有互斥后台任务')
            return False
        self.operation=operation_name or kind
        self.operation_id=uuid4().hex
        self.task_state='RUNNING';self.last_failure=None
        self._kind=kind
        self.busy = True
        self.busy_changed.emit(True)
        labels={'open_raw':'正在读取 RAW','detect':'正在检测','history':'正在加载历史结果列表','load_history':'正在加载历史结果','save':'正在保存正式结果','view':'正在加载视图','human_raw':'正在校验 RAW','human_save':'正在保存人工复核','human_session':'正在加载人工复核会话','human_export':'正在导出人工复核记录'}
        self.status_changed.emit(labels.get(self.operation,'正在加载视图 / 后台资源')+'…')
        self.thread = QThread(self)
        self.worker = InspectionWorker(operation,self.runtime_root/'gui_errors.log',application_log=self.application_log,kind=self.operation,operation_id=self.operation_id)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.succeeded.connect(self._succeeded, Qt.ConnectionType.QueuedConnection)
        self.worker.failed.connect(self.error)
        self.worker.failed_detail.connect(self._failed_detail, Qt.ConnectionType.QueuedConnection)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._finished)
        self.thread.start()
        return True

    @Slot(object)
    def _succeeded(self, value):
        if self._kind=="engine_status":self.engine_ready,self.engine_status=value
        handled_failure=self._kind=='human_raw' and isinstance(value,tuple) and len(value)==5 and value[-1]
        self.task_state='FAILED' if handled_failure else 'SUCCEEDED'
        self.completed.emit(self._kind, value)
        if handled_failure:self.status_changed.emit('操作失败，RAW未关联；详情见运行日志')
        elif self.application_log.write_failed:self.status_changed.emit('操作已完成，但运行日志暂不可写，请检查磁盘和权限')

    @Slot(object)
    def _failed_detail(self,failure):
        self.task_state='FAILED';self.last_failure=failure
        self.error_detail.emit(failure)

    def report_exception(self,exc,*,operation=None):
        name=operation or self.operation
        failure=classify_error(exc,name)
        self.application_log.event(logging.ERROR,name,failure.code,'界面回调或前置操作失败',exc=exc,operation_id=self.operation_id)
        self._failed_detail(failure);self.error.emit(failure.user_message)
        return failure

    @Slot()
    def _finished(self):
        self.thread.deleteLater()
        self.thread = self.worker = None
        self.busy = False
        if self.task_state=='SUCCEEDED' and not self.application_log.write_failed and self._kind not in ('saved','ledger'):self.status_changed.emit('操作完成')
        self.busy_changed.emit(False)

    def open_raw(self, path):
        def operation():
            raw = RawImageProvider(path)
            try:return raw, raw.thumbnail()
            except Exception:
                raw.clear()
                raise
        return self.submit('raw', operation,operation_name='open_raw')

    def detect(self, path, raw=None):
        def operation():
            service = self.service_factory(self.staging)
            record = service.inspect_and_save(path)
            result = self.staging.load(record.result_id)
            vm = ResultViewModel(result, record.result_dir)
            return vm, vm.frame(ViewMode.FINAL, raw), False
        return self.submit('result', operation,operation_name='detect')

    def history(self):
        def operation():
            from ui.models.defect_ledger import HistoryLedgerEntry,filter_metadata
            return [HistoryLedgerEntry(s,filter_metadata(self.repository.load(s.result_id)).get('filter_id')) for s in self.repository.list_results()]
        return self.submit('history', operation)

    def sync_ledger(self):
        def operation():
            from ui.models.defect_ledger import DefectLedger
            return DefectLedger(self.repository).sync(rebuild=True)
        return self.submit('ledger',operation,operation_name='ledger')

    def load_history(self, result_id):
        def operation():
            result,binding = self.formal_authority.load(result_id)
            vm = ResultViewModel(result, binding.package_dir,formal_binding=binding)
            return vm, vm.frame(ViewMode.FINAL), True
        return self.submit('result', operation,operation_name='load_history')

    def save(self, vm, raw=None, *, filter_id=None, notes=''):
        def operation():
            from domain import InspectionResult
            from domain.serialization import from_dict
            from ui.models.defect_ledger import DefectLedger,filter_metadata,validate_filter_id
            captured=from_dict(InspectionResult,source_payload(vm.result))
            metadata=filter_metadata(captured)
            if filter_id is not None:metadata={'filter_id':validate_filter_id(filter_id),'notes':notes}
            validate_filter_id(metadata.get('filter_id'))
            captured.extensions['filter_metadata']=metadata
            before=source_payload(captured)
            record=self.repository.save(captured,vm.package_dir)
            result,binding=self.formal_authority.load(record.result_id)
            if result.result_id!=vm.result.result_id or source_payload(result)!=before:
                raise ValueError('RESULT_MISMATCH: formal reload changed result')
            formal=ResultViewModel(result,record.result_dir,formal_binding=binding)
            evidence=None;warning=''
            if raw is not None:
                try:evidence=validate_raw(raw.path,result)
                except ValueError as exc:
                    warning='当前RAW未通过正式结果身份校验，请重新关联'
                    self.application_log.event(logging.WARNING,'save',classify_error(exc,'human_raw').code,warning,exc=exc,result_id=result.result_id)
            ledger_warning=''
            try:DefectLedger(self.repository).sync()
            except Exception as exc:
                ledger_warning='正式结果已保存，但 Excel 台账更新失败。请关闭 Excel/WPS 后使用“同步/重建检测台账”。'
                self.application_log.event(logging.ERROR,'ledger','LEDGER_UPDATE_FAILED',ledger_warning,exc=exc,result_id=result.result_id)
            try:return FormalSaveOutcome(record,formal,formal.frame(ViewMode.FINAL,evidence),evidence,warning,ledger_warning)
            except Exception:
                if evidence:evidence.clear()
                raise
        return self.submit('saved',operation,operation_name='save')

    def view(self, vm, mode, raw, final_mask):
        return self.submit('frame', lambda: vm.frame(mode, raw, final_mask),operation_name='view')

    def close(self):
        if self.busy:
            return False
        self.application_log.event(logging.INFO,'close','APPLICATION_CLOSED','应用关闭，后台任务均已结束')
        self._temporary.cleanup()
        self.application_log.close()
        return True
