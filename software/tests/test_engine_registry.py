import pytest,json
from infrastructure.engines import EngineRegistry,EngineError
from engine_fixtures import package

def test_install_switch_rollback_and_preservation(tmp_path):
    a,_=package(tmp_path/'A');b,_=package(tmp_path/'B','2.0.0');r=EngineRegistry(tmp_path/'release')
    r.install(a);old=(r.root/'versions/reference_1.0.0/engine_runner.exe').read_bytes()
    r.install(b);assert r.resolve().data['engine_version']=='2.0.0'
    r.select('reference','1.0.0');assert r.resolve().data['engine_version']=='1.0.0'
    assert len(r.discover())==2 and (r.root/'versions/reference_1.0.0/engine_runner.exe').read_bytes()==old
    with pytest.raises(EngineError):r.install(a)

def test_failed_switch_is_atomic(tmp_path):
    a,_=package(tmp_path/'A');r=EngineRegistry(tmp_path/'release');r.install(a);old=(r.root/'current.json').read_bytes()
    with pytest.raises(EngineError):r.select('reference','9.0.0')
    assert (r.root/'current.json').read_bytes()==old and r.resolve().data['engine_version']=='1.0.0'

@pytest.mark.parametrize('value',[None,[],{},dict(engine_id='../x',engine_version='1'),dict(engine_id='reference',engine_version='0')])
def test_invalid_current_never_falls_back(tmp_path,value):
    a,_=package(tmp_path/'A');r=EngineRegistry(tmp_path/'release');r.install(a);(r.root/'current.json').write_text(json.dumps(value))
    with pytest.raises(EngineError):r.resolve()

def test_corrupt_install_leaves_current(tmp_path):
    a,_=package(tmp_path/'A');b,_=package(tmp_path/'B','2.0.0');r=EngineRegistry(tmp_path/'release');r.install(a);(b/'payload.bin').write_bytes(b'wrong')
    with pytest.raises(EngineError):r.install(b)
    assert len(r.discover())==1 and r.resolve().data['engine_version']=='1.0.0'
