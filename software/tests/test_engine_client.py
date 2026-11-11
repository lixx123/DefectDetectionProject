import pytest,sys,json
from pathlib import Path
from infrastructure.engines import EngineRegistry,DetectionEngineClient,EngineError
from domain.configuration import InspectionConfig
from engine_fixtures import package

def test_frozen_factory_has_no_developer_fallback(tmp_path,monkeypatch):
    from application.engine_selection import create_detector
    monkeypatch.setattr(sys,'frozen',True,raising=False);monkeypatch.setattr(sys,'executable',str(tmp_path/'app.exe'))
    c=create_detector(tmp_path/'runtime');assert isinstance(c,DetectionEngineClient)
    with pytest.raises(EngineError):c.inspect(tmp_path/'x.raw',InspectionConfig())

def test_invalid_package_cannot_launch(tmp_path,monkeypatch):
    import infrastructure.engines.client as m
    monkeypatch.setattr(m.subprocess,'Popen',lambda *a,**k:pytest.fail('invalid engine launched'))
    with pytest.raises(EngineError):DetectionEngineClient(tmp_path,tmp_path/'runtime').inspect(tmp_path/'raw',InspectionConfig())

def test_failed_child_records_exit_and_sanitizes_environment(tmp_path,monkeypatch):
    import infrastructure.engines.client as m
    p,_=package(tmp_path/'package');r=EngineRegistry(tmp_path/'release');r.install(p);raw=tmp_path/'test.raw';raw.write_bytes(b'xx')
    monkeypatch.setenv('PYTHONPATH','BAD_DEVELOPMENT_PATH');monkeypatch.setenv('VIRTUAL_ENV','BAD_VENV')
    class Child:
        pid=123;returncode=42
        def poll(self):return 42
    def popen(command,**kw):
        assert Path(command[0]).samefile(r.root/'versions/reference_1.0.0/engine_runner.exe')
        assert 'PYTHONPATH' not in kw['env'] and 'VIRTUAL_ENV' not in kw['env']
        return Child()
    monkeypatch.setattr(m.subprocess,'Popen',popen)
    with pytest.raises(EngineError,match='PROCESS_FAILED'):DetectionEngineClient(r.release_root,tmp_path/'runtime').inspect(raw,InspectionConfig())
    records=list((tmp_path/'runtime').glob('*/process_receipt.json'));assert len(records)==1 and json.loads(records[0].read_text(encoding='utf-8'))['exit_code']==42
