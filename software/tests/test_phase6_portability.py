"""Portability and opt-in data acceptance contracts, without external RAW."""
from pathlib import Path
import hashlib
import ast
import pytest
from regression.machine_paths import scan_machine_paths
from regression.reproduce_display_observation import build_parser, stream_sha256


def test_permanent_source_has_no_machine_paths():
    report=scan_machine_paths(Path(__file__).resolve().parents[1])
    assert report['status']=='PASS'
    assert report['production_code_hits']==report['permanent_test_hits']==[]


@pytest.mark.parametrize('scope',['ui','tests','regression','scripts','application'])
@pytest.mark.parametrize('form',['forward','backslash','escaped'])
def test_scanner_catches_literal_and_decoded_paths(tmp_path,scope,form):
    path='/'.join(('D:', '疵病检测','example.raw'))
    if form=='backslash': path=path.replace('/','\\')
    text='value = '+(ascii(path) if form=='escaped' else repr(path))+'\n'
    destination=tmp_path/scope/'example.py'; destination.parent.mkdir()
    destination.write_text(text,encoding='utf-8')
    report=scan_machine_paths(tmp_path)
    key='permanent_test_hits' if scope=='tests' else 'production_code_hits'
    assert report['status']=='FAIL' and report[key]==[dict(path=f'{scope}/example.py',line=1)]


def test_scanner_excludes_historical_docs_and_detects_user_path(tmp_path):
    (tmp_path/'docs').mkdir()
    value='/'.join(('C:', 'Users','example','input.raw'))
    (tmp_path/'docs/old.py').write_text('value='+repr(value),encoding='utf-8')
    assert scan_machine_paths(tmp_path)['status']=='PASS'
    (tmp_path/'ui').mkdir()
    (tmp_path/'ui/bad.py').write_text('value='+repr(value),encoding='utf-8')
    assert scan_machine_paths(tmp_path)['status']=='FAIL'


def test_real_display_requires_explicit_cli_path(tmp_path):
    with pytest.raises(SystemExit) as exc: build_parser().parse_args([])
    assert exc.value.code==2
    path=tmp_path/'explicit.raw'
    args=build_parser().parse_args(['--raw-path',str(path)])
    assert args.raw_path==path


def test_raw_sha_uses_bounded_streaming(tmp_path,monkeypatch):
    path=tmp_path/'synthetic.raw'; data=b'pixels'*400000; path.write_bytes(data)
    original=Path.open; requests=[]
    class Reader:
        def __init__(self,stream): self.stream=stream
        def __enter__(self): return self
        def __exit__(self,*args): self.stream.close()
        def read(self,size):
            assert size==1024*1024
            requests.append(size)
            return self.stream.read(size)
    monkeypatch.setattr(Path,'open',lambda p,*a,**k: Reader(original(p,*a,**k)))
    monkeypatch.setattr(Path,'read_bytes',lambda *_:pytest.fail('whole-file RAW read forbidden'))
    assert stream_sha256(path)==hashlib.sha256(data).hexdigest() and len(requests)>=3


def test_real_script_has_no_discovery_or_whole_raw_reads():
    root=Path(__file__).resolve().parents[1]
    tree=ast.parse((root/'regression/reproduce_display_observation.py').read_text(encoding='utf-8'))
    forbidden={'read_bytes','glob','rglob','walk','scandir'}
    assert not [n for n in ast.walk(tree) if isinstance(n,ast.Call)
                and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden]
