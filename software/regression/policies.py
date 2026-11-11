"""Fail-closed schema, policy and change-impact gates."""
from dataclasses import fields, is_dataclass, MISSING
from enum import Enum
from pathlib import Path
from typing import get_type_hints, get_args, get_origin
import ast, importlib, json, subprocess
from infrastructure.storage.package import sha256


def schema_contract():
    from domain import enums
    modules=('common','calibration','defect','review','execution','roi','algorithm','statistics','audit','task','intermediate','configuration','inspection_result')
    classes={}
    def typename(kind):
        args=get_args(kind); origin=get_origin(kind)
        if args: return (getattr(origin,'__name__',str(origin))+'['+','.join(typename(a) for a in args)+']')
        return 'None' if kind is type(None) else getattr(kind,'__name__',str(kind))
    for name in modules:
        module=importlib.import_module('domain.'+name)
        for cls in vars(module).values():
            if isinstance(cls,type) and is_dataclass(cls) and cls.__module__==module.__name__:
                hints=get_type_hints(cls)
                classes[cls.__name__]={f.name:{'required':f.default is MISSING and f.default_factory is MISSING,
                    'nullable':type(None) in get_args(hints[f.name]),'type':typename(hints[f.name])}
                    for f in fields(cls) if f.init and not f.name.startswith('_')}
    enum_values={name:[e.value for e in cls] for name,cls in vars(enums).items()
        if isinstance(cls,type) and issubclass(cls,Enum) and cls.__module__==enums.__name__}
    return {'schema_version':'1.0','classes':dict(sorted(classes.items())),'enum_wire_values':dict(sorted(enum_values.items()))}


def auto_policy_gate(root):
    from configs.loader import load_config
    from domain.configuration import AutoPolicy
    result={'status':'FAIL','roi_j4_in_auto':False,'errors':[]}
    try:
        config=load_config(Path(root)/'configs/production_v1.yaml')
        if (config.pipeline_mode.value,config.auto_policy.primary.value,config.auto_policy.fallback.value)!=('auto','roi-bh','full'):
            raise ValueError('production YAML AUTO policy changed')
        policy=AutoPolicy()
        if (policy.primary.value,policy.fallback.value)!=('roi-bh','full'): raise ValueError('default AUTO policy changed')
        tree=ast.parse((Path(root)/'core/pipeline.py').read_text(encoding='utf-8'))
        assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='modes' for t in n.targets))
        mode_list=assignment.value.body
        if not isinstance(mode_list,ast.List) or [getattr(e,'attr',None) for e in mode_list.elts]!=['ROI_BH','FULL']:
            result['roi_j4_in_auto']=True; raise ValueError('actual scheduler is no longer ROI_BH -> FULL')
        worker=ast.parse((Path(root)/'core/runtime/engine_worker.py').read_text(encoding='utf-8'))
        guards=[n for n in ast.walk(worker) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='require_computed_response']
        if len(guards)<2: raise ValueError('actual J4/K8B consumed-window sentinel guards missing')
        result.update(status='PASS',sentinel_consumed_guards=len(guards))
    except Exception as exc: result['errors'].append(str(exc))
    return result


def code_impact(changed_paths):
    safe_prefixes=('ui/','tests/','docs/','regression/','infrastructure/regression/')
    safe_files={'README.md','CHANGELOG.md','.gitignore','pytest.ini','scripts/run_regression_suite.py','scripts/update_golden_baseline.py'}
    safe_files.update({'app/runtime_paths.py', 'packaging/defect_inspection.spec',
                       'packaging/build_release.ps1', 'packaging/finalize_release.py',
                       'packaging/launch.py', 'packaging/release_qa.py',
                       'packaging/smoke_release.ps1', 'packaging/requirements-build.txt',
                       'packaging/README.md', 'README_RELEASE.md'})
    risky=[]
    for path in changed_paths:
        path=path.replace('\\','/')
        if path in safe_files or path.startswith(safe_prefixes): continue
        # Unknown paths remain conservative, including core/domain/config/application.
        risky.append(path)
    return {'real_engine_required':bool(risky),'real_engine_reasons':sorted(risky),'changed_paths':sorted(changed_paths)}


def git_context(root,baseline_commit):
    def git(*args): return subprocess.check_output(['git','-C',str(root),*args],text=True,encoding='utf-8').strip()
    paths=set(git('diff','--name-only',baseline_commit).splitlines())
    paths.update(git('ls-files','--others','--exclude-standard').splitlines()); paths.discard('')
    tracked=git('ls-files','--','*.py','configs/*.yaml','pytest.ini').splitlines()
    current=sorted(set(tracked)|{p for p in paths if p.endswith(('.py','.yaml','.ini','.json')) and not p.startswith('docs/')})
    from .comparator import digest
    fingerprint=digest({p:sha256(Path(root)/p) if (Path(root)/p).is_file() else 'DELETED' for p in current})
    return {'git_commit':git('rev-parse','HEAD'),'worktree_dirty':bool(git('status','--porcelain')),
        'baseline_commit':baseline_commit,'tested_source_fingerprint':fingerprint,**code_impact(paths)}


def protected_algorithm_gate(root):
    manifest=json.loads((Path(root)/'docs/phase_3/protected_file_manifest.json').read_text(encoding='utf-8'))
    reference=(Path(root).parent/'DefectDetectionProject').resolve()
    manifest=[entry for entry in manifest if Path(entry['path']).resolve().is_relative_to(reference)]
    if not manifest: return {'status':'FAIL','changed_files':['original algorithm manifest scope empty']}
    changed=[]
    for entry in manifest:
        path=Path(entry['path'])
        if not path.is_file() or sha256(path)!=entry['sha256']: changed.append(entry['path'])
    return {'status':'FAIL' if changed else 'PASS','protected_files_checked':len(manifest),'changed_files':changed}
