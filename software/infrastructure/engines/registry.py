"""Local immutable versions; atomic selection, install without overwrite."""
from pathlib import Path
import json,os,shutil,tempfile
from uuid import uuid4
from app.runtime_paths import native_path
from .manifest import EngineManifest,EngineError,identifier,inside

class EngineRegistry:
    def __init__(self,release_root):self.release_root=Path(release_root).resolve();self.root=self.release_root/'engines'

    def resolve(self):
        if self.root.is_symlink() or (hasattr(self.root,'is_junction') and self.root.is_junction()):raise EngineError('ENGINE_ROOT_LINK_FORBIDDEN')
        try:data=json.loads(inside(self.root,'current.json').read_text(encoding='utf-8'))
        except (OSError,ValueError) as e:raise EngineError('ENGINE_CURRENT_INVALID') from e
        try:
            key=identifier(data['engine_id'])+'_'+identifier(data['engine_version'])
            manifest=EngineManifest.load(inside(self.root,'versions/'+key))
            if (manifest.data['engine_id'],manifest.data['engine_version'])!=(data['engine_id'],data['engine_version']):raise EngineError('ENGINE_CURRENT_ID_MISMATCH')
            return manifest
        except (TypeError,KeyError) as e:raise EngineError('ENGINE_CURRENT_INVALID') from e

    def discover(self):
        versions=self.root/'versions'
        return [EngineManifest.load(p) for p in sorted(versions.iterdir()) if p.is_dir() and not p.name.startswith('.')] if versions.exists() else []

    def select(self,engine_id,engine_version):
        key=identifier(engine_id)+'_'+identifier(engine_version)
        target=EngineManifest.load(inside(self.root,'versions/'+key))
        if (target.data['engine_id'],target.data['engine_version'])!=(engine_id,engine_version):raise EngineError('ENGINE_CURRENT_ID_MISMATCH')
        self.root.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.current_',suffix='.json',dir=self.root)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(dict(engine_id=engine_id,engine_version=engine_version),f);f.flush();os.fsync(f.fileno())
            os.replace(name,self.root/'current.json')
        finally:
            if Path(name).exists():Path(name).unlink()
        return target

    def install(self,source,*,activate=True):
        candidate=EngineManifest.load(source);key=candidate.data['engine_id']+'_'+candidate.data['engine_version']
        versions=self.root/'versions';versions.mkdir(parents=True,exist_ok=True)
        dest=inside(self.root,'versions/'+key)
        if dest.exists():raise EngineError('ENGINE_VERSION_ALREADY_EXISTS')
        staging=versions/('.install_'+uuid4().hex)
        try:
            shutil.copytree(candidate.root,native_path(staging,force=True));copied=EngineManifest.load(staging)
            if copied.data!=candidate.data:raise EngineError('ENGINE_INSTALL_SOURCE_CHANGED')
            os.rename(staging,dest)
        finally:
            if staging.exists():shutil.rmtree(staging)
        return self.select(candidate.data['engine_id'],candidate.data['engine_version']) if activate else EngineManifest.load(dest)
