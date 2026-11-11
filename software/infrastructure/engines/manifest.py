"""Strict local package integrity and compatibility; no algorithm imports."""
from pathlib import Path,PurePosixPath,PureWindowsPath
import hashlib,json,re
from app.runtime_paths import native_path

PROFILE=dict(format='RAW',width=11276,height=9200,container_bits=16,effective_bits=12,byte_order='big')

class EngineError(RuntimeError):pass

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')

def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',value) or '..' in value or value.endswith('.'):raise EngineError('ENGINE_INVALID_ID')
    return value

def inside(root,name):
    from infrastructure.storage.paths import relative_path
    try:relative_path(name)
    except Exception as exc:raise EngineError("ENGINE_UNSAFE_PATH") from exc
    if not isinstance(name,str) or not name or chr(92) in name or PureWindowsPath(name).drive or PurePosixPath(name).is_absolute() or any(p in ('','.','..') for p in name.split('/')):raise EngineError('ENGINE_UNSAFE_PATH')
    root=native_path(root,force=True).resolve();p=root.joinpath(*name.split('/'))
    if not p.resolve().is_relative_to(root):raise EngineError('ENGINE_PATH_ESCAPE')
    if any(q.is_symlink() or (hasattr(q,'is_junction') and q.is_junction()) for q in [p,*p.parents] if q!=root.parent and q.is_relative_to(root)):raise EngineError('ENGINE_LINK_FORBIDDEN')
    return p

class EngineManifest:
    def __init__(self,root,data):self.root=native_path(root,force=True).resolve();self.data=data

    @classmethod
    def load(cls,root,*,verify=True):
        root=native_path(root,force=True)
        try:data=json.loads(inside(root,'engine_manifest.json').read_text(encoding='utf-8'))
        except (OSError,ValueError) as e:raise EngineError('ENGINE_MANIFEST_INVALID') from e
        try:
            identifier(data['engine_id']);identifier(data['engine_version'])
            if data['protocol_version']!='1.0':raise EngineError('ENGINE_PROTOCOL_INCOMPATIBLE')
            if data['output_schema_version']!='1.0':raise EngineError('ENGINE_SCHEMA_INCOMPATIBLE')
            if data['supported_input']!=PROFILE:raise EngineError('ENGINE_INPUT_INCOMPATIBLE')
            for key in ['algorithm_source_sha256','engine_bundle_sha256','runner_sha256']:
                if not re.fullmatch('[0-9a-f]{64}',data[key]):raise EngineError('ENGINE_HASH_INVALID')
            if data['runner']!='engine_runner.exe' or not data['config_version']:raise EngineError('ENGINE_RUNNER_INVALID')
            files=data['files']
            if not isinstance(files,dict) or not files or data['runner'] not in files:raise EngineError('ENGINE_FILE_MANIFEST_INVALID')
            if hashlib.sha256(canonical(files)).hexdigest()!=data['engine_bundle_sha256']:raise EngineError('ENGINE_BUNDLE_HASH_MISMATCH')
            for n,h in files.items():
                if n=='engine_manifest.json' or not re.fullmatch('[0-9a-f]{64}',h):raise EngineError('ENGINE_FILE_MANIFEST_INVALID')
                if not inside(root,n).is_file():raise EngineError('ENGINE_FILE_MISSING: '+n)
            if files[data['runner']]!=data['runner_sha256']:raise EngineError('ENGINE_RUNNER_HASH_MISMATCH')
            value=cls(root,data)
            if verify:value.verify()
            return value
        except (KeyError,TypeError,ValueError) as e:raise EngineError('ENGINE_MANIFEST_INVALID') from e

    def verify(self):
        for n,h in self.data['files'].items():
            if sha(inside(self.root,n))!=h:raise EngineError('ENGINE_FILE_HASH_MISMATCH: '+n)
        actual={p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file() and p!=self.root/'engine_manifest.json'}
        if actual!=set(self.data['files']):raise EngineError('ENGINE_UNMANIFESTED_FILES')
        return self

    @property
    def runner(self):return inside(self.root,self.data['runner'])

    @property
    def identity(self):return {k:self.data[k] for k in ['engine_id','engine_version','protocol_version','algorithm_source_sha256','engine_bundle_sha256']}
