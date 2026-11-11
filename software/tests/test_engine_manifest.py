import pytest
from infrastructure.engines.manifest import EngineManifest,EngineError,inside
from engine_fixtures import package,save

def test_valid(tmp_path):
    p,m=package(tmp_path/'package');assert EngineManifest.load(p).identity['engine_version']=='1.0.0'

@pytest.mark.parametrize('field,value',[('protocol_version','2.0'),('output_schema_version','2.0'),('runner','else.exe'),('algorithm_source_sha256','broken'),('engine_bundle_sha256','a'*64),('engine_id','../escape'),('engine_version','../bad'),('supported_input',{})])
def test_incompatible_rejected(tmp_path,field,value):
    p,m=package(tmp_path/'package');m[field]=value;save(p,m)
    with pytest.raises(EngineError):EngineManifest.load(p)

@pytest.mark.parametrize('file',['engine_runner.exe','payload.bin'])
@pytest.mark.parametrize('mode',['missing','corrupt'])
def test_file_tampering(tmp_path,file,mode):
    p,m=package(tmp_path/'package')
    if mode=='missing':(p/file).unlink()
    else:(p/file).write_bytes(b'CHANGED')
    with pytest.raises(EngineError):EngineManifest.load(p)

@pytest.mark.parametrize('name',['../escape','a/../../escape','C:/escape','/absolute','a\\escape','a//b','./a'])
def test_unsafe_paths(tmp_path,name):
    with pytest.raises(EngineError):inside(tmp_path,name)

def test_unmanifested_rejected(tmp_path):
    p,m=package(tmp_path/'package');(p/'surprise.bin').write_bytes(b'x')
    with pytest.raises(EngineError):EngineManifest.load(p)
