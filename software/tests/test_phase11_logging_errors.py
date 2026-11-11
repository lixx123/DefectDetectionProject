"""Phase11 adaptation tests, including real controller failure propagation."""
import logging
from pathlib import Path
import pytest
from PySide6.QtTest import QSignalSpy
from test_phase6_ui import qapp,window,wait
from ui.runtime_errors import classify_error
from ui.runtime_log import ApplicationLog
from ui.models.human_review import ReviewConflict
from infrastructure.repositories.errors import PackageIntegrityError

@pytest.mark.parametrize('operation,exc,code',[
 ('open_raw',FileNotFoundError('private'),'RAW_READ_FAILED'),
 ('open_raw',ValueError('RAW 大小不正确'),'RAW_SIZE_MISMATCH'),
 ('human_raw',ReviewConflict('RAW_UNSUPPORTED_FORMAT'),'RAW_UNSUPPORTED_FORMAT'),
 ('human_raw',ReviewConflict('RAW_MISMATCH'),'RAW_MISMATCH'),
 ('human_raw',ReviewConflict('RAW_UNAVAILABLE'),'RAW_UNAVAILABLE'),
 ('detect',ValueError('CONFIG_ERROR'),'CONFIG_ERROR'),
 ('detect',ValueError('ROI_DETECTION_FAILED'),'ROI_DETECTION_FAILED'),
 ('detect',RuntimeError('known technical failure'),'DETECTION_FAILED'),
 ('load_history',FileNotFoundError(),'RESULT_LOAD_FAILED'),
 ('load_history',PackageIntegrityError('secret'),'RESULT_INTEGRITY_FAILED'),
 ('save',OSError('secret'),'RESULT_SAVE_FAILED'),
 ('view',OSError('secret'),'VIEW_RESOURCE_FAILED'),
 ('human_session',OSError('secret'),'REVIEW_SESSION_FAILED'),
 ('human_save',OSError('secret'),'REVIEW_SUBMIT_FAILED'),
 ('human_save',ReviewConflict('revision conflict'),'REVIEW_CONFLICT'),
 ('human_save',ReviewConflict('POLICY_MISMATCH'),'POLICY_MISMATCH'),
 ('human_session',ReviewConflict('TEMPORARY_RESULT'),'TEMPORARY_RESULT'),
 ('human_export',OSError('secret'),'EXPORT_FAILED'),
 ('fixture',ValueError('输入值不在允许范围'),'INPUT_VALIDATION_FAILED'),
 ('fixture',Exception('SECRET_STACK_DETAIL'),'UNEXPECTED_ERROR'),
 ('open_raw',FileNotFoundError('missing/POLICY_MISMATCH.raw'),'RAW_READ_FAILED'),
 ('fixture',RuntimeError('technical detail mentioning RAW_MISMATCH'),'UNEXPECTED_ERROR'),
 ('fixture',RuntimeError('SECRET_STACK_DETAIL'),'UNEXPECTED_ERROR')])
def test_error_mapping(operation,exc,code):
    failure=classify_error(exc,operation)
    assert failure.code==code and code in failure.user_message
    assert 'Traceback' not in failure.user_message and 'SECRET' not in failure.user_message
    assert '日志' in failure.user_message and failure.retryable in (True,False)

def test_log_utf8_rotation_levels_and_directory(tmp_path):
    path=tmp_path/'new/log/gui_errors.log';log=ApplicationLog(path,max_bytes=450,backup_count=2)
    for i in range(18):log.event(logging.INFO,'history','STARTED','正在读取中文历史结果',operation_id=str(i))
    log.event(logging.WARNING,'view','VIEW_RESOURCE_FAILED','资源不可用')
    log.event(logging.ERROR,'save','RESULT_SAVE_FAILED','保存失败');log.close()
    files=list(path.parent.glob('gui_errors.log*'));assert 1<=len(files)<=3
    content=''.join(p.read_text(encoding='utf-8') for p in files)
    assert all(s in content for s in ['WARNING','ERROR','operation=','timestamp=','保存失败'])

def test_logging_failure_does_not_suppress_worker_error(window,qapp,monkeypatch):
    c=window.controller
    monkeypatch.setattr(c.application_log.handler,'emit',lambda record:(_ for _ in ()).throw(OSError('disk unavailable')))
    spy=QSignalSpy(c.error)
    c.submit('fixture',lambda:(_ for _ in ()).throw(RuntimeError('private detail')))
    wait(qapp,lambda:not c.busy)
    assert spy.count()==1 and c.task_state=='FAILED' and c.thread is c.worker is None
    assert '日志' in window.resource_status.text() and 'private detail' not in window.resource_status.text()
    assert c.application_log.write_failed

def test_unknown_traceback_and_success_logs(window,qapp):
    c=window.controller
    c.submit('fixture',lambda:'done');wait(qapp,lambda:not c.busy)
    def boom():raise RuntimeError('TECHNICAL_TRACE_ONLY')
    c.submit('fixture',boom);wait(qapp,lambda:not c.busy)
    content=(c.runtime_root/'gui_errors.log').read_text(encoding='utf-8')
    assert all(s in content for s in ['STARTED','SUCCEEDED','UNEXPECTED_ERROR','Traceback','TECHNICAL_TRACE_ONLY'])
    assert 'TECHNICAL_TRACE_ONLY' not in window.resource_status.text()
