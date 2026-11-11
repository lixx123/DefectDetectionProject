import sys,time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from ui.main_window import MainWindow
from ui.controllers.inspection_controller import InspectionController
from infrastructure.engines import EngineRegistry
from engine_fixtures import package

def settle(app,c):
    until=time.monotonic()+10
    while time.monotonic()<until:
        app.processEvents();time.sleep(.005)
        if not c.busy:return
    raise AssertionError('worker timeout')

def test_missing_engine_disables_both_detection_actions(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(sys,'frozen',True,raising=False);monkeypatch.setattr(sys,'executable',str(tmp_path/'app.exe'))
    c=InspectionController(runtime_root=tmp_path/'runtime');w=MainWindow(c);app.processEvents();settle(app,c)
    w.raw_path=tmp_path/'test.raw';w._refresh_actions()
    assert not w.start_action.isEnabled() and not w.redetect_action.isEnabled() and not c.engine_ready
    assert '不可用' in w.engine_label.text();w.close();app.processEvents()

def test_valid_engine_ready_and_corruption_disables(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);p,_=package(tmp_path/'package');r=EngineRegistry(tmp_path/'release');r.install(p)
    monkeypatch.setattr(sys,'frozen',True,raising=False);monkeypatch.setattr(sys,'executable',str(r.release_root/'app.exe'))
    c=InspectionController(runtime_root=tmp_path/'runtime');w=MainWindow(c);app.processEvents();settle(app,c)
    w.raw_path=tmp_path/'x.raw';w._refresh_actions();assert w.start_action.isEnabled() and '已就绪' in w.engine_label.text()
    (r.root/'versions/reference_1.0.0/engine_runner.exe').write_bytes(b'wrong');c.check_engine();settle(app,c);w._refresh_actions()
    assert not c.engine_ready and not w.start_action.isEnabled();w.close();app.processEvents()
