"""FAST/GOLDEN/REAL/RELEASE, with explicit data requirements and audit reports."""
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
import argparse, json, os, subprocess, sys, xml.etree.ElementTree as ET
import tempfile
from regression.golden import load_manifest
from regression.policies import schema_contract, auto_policy_gate, protected_algorithm_gate, git_context
from regression.release_gate import release_decision
from infrastructure.storage.package import sha256


def dump(path,value):
    with Path(path).open('x',encoding='utf-8') as stream: json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def run_pytest(root,output,profile):
    selection='not golden and not real_engine and not reference_probe' if profile=='fast' else 'golden and not real_engine and not reference_probe'
    junit=output/(profile+'_junit.xml'); log=output/(profile+'.log')
    # Short independent temp names keep existing Windows fixtures within MAX_PATH.
    # Reserve a unique owned parent atomically; pytest only manages its child.
    owned=Path(tempfile.mkdtemp(prefix='.pt_',dir=Path(root)/'output'))
    base=owned/'t'
    command=[sys.executable,'-m','pytest','-q','--strict-markers','--tb=short','-m',selection,'--basetemp',str(base),'--junitxml',str(junit)]
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',DEFECT_REGRESSION_REPORT_DIR=str(output))
    with log.open('x',encoding='utf-8') as stream:
        completed=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT)
    counts=dict(tests=0,failures=0,errors=0,skipped=0)
    if junit.exists():
        for suite in ET.parse(junit).getroot().iter('testsuite'):
            for field in counts: counts[field]+=int(suite.attrib.get(field,0))
    status='PASS' if completed.returncode==0 and counts['tests']>0 and not any(counts[k] for k in ('failures','errors','skipped')) else 'FAIL'
    record=dict(status=status,exit_code=completed.returncode,command=command,counts=counts,log=str(log),owned_temp_dir=str(owned),temp_policy='OS_RESERVED_UNIQUE_PARENT_RETAINED_FOR_DIAGNOSTICS')
    if profile=='golden':
        path=output/'golden_report.json'
        if not path.exists(): record.update(status='FAIL',error='golden semantic report missing')
        else:
            record['semantic_report']=json.loads(path.read_text(encoding='utf-8'))
            if record['semantic_report']['status'] not in ('PASS','PASS_WITH_WARNINGS'): record['status']='FAIL'
    return record


def run_real(root,output,raw_root=None,reference_root=None,*,detector_factory=None):
    from domain.configuration import InspectionConfig
    from domain.serialization import from_dict
    from regression.comparator import semantic_snapshot, compare_snapshots
    manifest=load_manifest(root)
    result={'status':'NOT_RUN','real_engine_executed':False,'algorithm_executions':0,'cases':[],'errors':[],
        'simulation':detector_factory is not None}
    if raw_root is None: result['errors'].append('REAL requires --raw-root; no engine launched'); return result
    paths={}
    for sample in manifest['samples']:
        path=Path(raw_root)/sample['raw_file_name']
        if not path.is_file(): result['errors'].append('RAW missing: '+sample['raw_file_name'])
        elif sha256(path)!=sample['raw_sha256']: result['errors'].append('RAW SHA256 mismatch: '+sample['raw_file_name'])
        else: paths[sample['sample_id']]=path
    if result['errors']: return result
    if detector_factory is None:
        from core.detector import Detector
        detector_factory=Detector
    detector=detector_factory(reference_root=reference_root,output_root=output/'real_runs')
    for sample in manifest['samples']:
        for mode,key in [('full','expected_full'),('roi-bh','expected_roi_bh'),('auto','expected_auto')]:
            case={'sample_id':sample['sample_id'],'mode':mode,'status':'FAIL'}
            try:
                config=from_dict(InspectionConfig,sample[key]['config_snapshot'])
                current=detector.inspect(paths[sample['sample_id']],config)
                if not result['simulation']:
                    result['real_engine_executed']=True
                    result['algorithm_executions']+=len(current.execution_info.attempts)
                current.validate_final(); current.save_json(detector.last_run_dir/'result.json')
                compared=compare_snapshots(sample[key]['snapshot'],semantic_snapshot(current,detector.last_run_dir))
                case.update(status=compared.status,comparison=compared.to_dict(),run_directory=str(detector.last_run_dir))
            except Exception as exc:
                case['error']=f'{type(exc).__name__}: {exc}'
            result['cases'].append(case)
    result['status']='FAIL' if any(c['status']=='FAIL' for c in result['cases']) else 'PASS_WITH_WARNINGS' if any(c['status']=='PASS_WITH_WARNINGS' for c in result['cases']) else 'PASS'
    return result


def run_profile(root,output,profile,*,raw_root=None,reference_root=None,base_commit=None,
                require_real=False,execute_real=False,test_runner=run_pytest,packaged_engine_evidence=None):
    root,output=Path(root),Path(output)
    if profile in ('fast','golden'):
        result=test_runner(root,output,profile)
        dump(output/(profile+'_profile_report.json'),result); return result
    if profile=='real':
        result=run_real(root,output,raw_root,reference_root)
        dump(output/'real_engine_report.json',result); return result
    if profile!='release': raise ValueError('unknown regression profile')
    manifest=load_manifest(root)
    context=git_context(root,base_commit or manifest['baseline_commit'])
    context['real_engine_required']=context['real_engine_required'] or require_real
    fast=test_runner(root,output,'fast'); golden=test_runner(root,output,'golden')
    schema_status='PASS' if schema_contract()==json.loads((root/'tests/golden/schema_contract.json').read_text(encoding='utf-8')) else 'FAIL'
    policy=auto_policy_gate(root); protection=protected_algorithm_gate(root)
    real=run_real(root,output,raw_root,reference_root) if execute_real else dict(status='NOT_RUN',real_engine_executed=False,algorithm_executions=0)
    if packaged_engine_evidence is not None:
        from regression.engine_evidence import accept_evidence
        real=accept_evidence(root,packaged_engine_evidence,context['git_commit'])
    semantic=golden.get('semantic_report',{})
    repo=semantic.get('repository_status','FAIL')
    checked={(c.get('sample_id'),c.get('mode')) for c in semantic.get('cases',[])}
    expected={(f'26_{frame}',mode) for frame in (1,2) for mode in ('full','roi-bh','auto')}
    if checked!=expected or len(semantic.get('repository_cases',[]))!=2:
        golden['status']='FAIL'
        golden['coverage_error']='all six sample/mode cases and two repository packages required'
    final=release_decision(fast_status=fast['status'],golden_status=golden['status'],repository_status=repo,
        schema_status=schema_status,auto_status=policy['status'],protection_status=protection['status'],
        real_required=context['real_engine_required'],real_executed=real['real_engine_executed'],real_status=real['status'])
    # Explicit real execution must also pass, even if impact analysis did not require it.
    if execute_real and real['status'] not in ('PASS','PASS_WITH_WARNINGS'): final='FAIL' if real['status']=='FAIL' else 'NOT_COMPLETE'
    report=dict(context,schema_version='1.0',golden_set_version='1.0',package_format_version='1.0',
        software_tests=fast,golden=golden,repository_status=repo,schema_status=schema_status,
        AUTO_policy=policy,algorithm_protection=protection,real_engine=real,
        real_engine_executed=real['real_engine_executed'],algorithm_executions=real['algorithm_executions'],
        golden_samples_checked=sorted({c['sample_id'] for c in semantic.get('cases',[])}),
        critical_differences=[{'sample_id':c['sample_id'],'mode':c['mode'],'details':c.get('comparison',{}).get('critical_differences',[]),'errors':c.get('errors',[])}
            for c in semantic.get('cases',[]) if c['status']=='FAIL'],warnings=semantic.get('warnings',[]),
        blind_validation_available=False,phase6_started=False,final_status=final,status=final)
    dump(output/'release_gate_report.json',report)
    with (output/'release_gate_report.md').open('x',encoding='utf-8') as stream:
        stream.write('# Release gate\n\n'+f'Final status: {final}\n\nTested HEAD: {context["git_commit"]}\n\nWorktree dirty: {context["worktree_dirty"]}; validated source fingerprint: {context["tested_source_fingerprint"]}\n\n')
        stream.write(f'FAST {fast["status"]}; GOLDEN {golden["status"]}; Repository {repo}; schema {schema_status}; AUTO {policy["status"]}; original algorithm protection {protection["status"]}.\n\n')
        stream.write(f'REAL_ENGINE_REQUIRED={context["real_engine_required"]}; REAL_ENGINE_EXECUTED={real["real_engine_executed"]}; status={real["status"]}.\n\n')
        stream.write('Golden Regression Set is not Blind Validation Set. Blind data NOT_AVAILABLE. Phase 6 not started.\n')
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=('fast','golden','real','release'),required=True)
    parser.add_argument('--raw-root'); parser.add_argument('--reference-root'); parser.add_argument('--output-dir')
    parser.add_argument('--packaged-engine-evidence',help='Recompute actual frozen EXE semantic evidence instead of rerunning developer adapter')
    parser.add_argument('--base-commit'); parser.add_argument('--require-real',action='store_true')
    parser.add_argument('--execute-real',action='store_true',help='explicitly run real algorithms as part of release')
    args=parser.parse_args(argv)
    if args.execute_real and args.profile!='release': parser.error('--execute-real only applies to release; use --profile real explicitly')
    root=Path(__file__).resolve().parents[1]
    output=Path(args.output_dir) if args.output_dir else root/'output/regression'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+args.profile+'_'+uuid4().hex[:8])
    output.mkdir(parents=True,exist_ok=False)
    try:
        result=run_profile(root,output,args.profile,raw_root=args.raw_root,reference_root=args.reference_root,
            base_commit=args.base_commit,require_real=args.require_real,execute_real=args.execute_real,packaged_engine_evidence=args.packaged_engine_evidence)
    except Exception as exc:
        result={'status':'FAIL','error':f'{type(exc).__name__}: {exc}','algorithm_executions':0}
        dump(output/'profile_error.json',result)
    print(json.dumps({'profile':args.profile,'status':result['status'],'output_dir':str(output)},ensure_ascii=False))
    return 0 if result['status'] in ('PASS','PASS_WITH_WARNINGS') else 1


if __name__=='__main__': raise SystemExit(main())
