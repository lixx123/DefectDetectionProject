"""Explicit audited metadata initialization/update; never changes physical evidence."""
from pathlib import Path
import argparse, json, os, subprocess
from datetime import datetime, timezone
from domain import InspectionResult
from domain.configuration import InspectionConfig
from domain.enums import PipelineMode
from domain.serialization import to_dict
from infrastructure.storage.package import artifact_references, sha256
from regression.comparator import semantic_snapshot, compare_snapshots
from regression.policies import schema_contract


def build_candidate(root,commit):
    root=Path(root)
    revision=json.loads((root/'docs/phase_3_revision/phase_3_revision_comparison.json').read_text(encoding='utf-8'))['cases']
    phase4=json.loads((root/'docs/phase_4/phase_4_acceptance.json').read_text(encoding='utf-8'))
    samples=[]
    for frame in (1,2):
        sample={'sample_id':f'26_{frame}','golden_id':f'GOLDEN_26_{frame}','schema_version':'1.0',
            'approved_darkspot_areas':[297,398] if frame==1 else [348,370],
            'baseline_source':'human-approved Phase 3 audit revision; Phase 4 immutable packages',
            'baseline_commit':commit}
        for mode,key in [('full','expected_full'),('roi-bh','expected_roi_bh'),('auto','expected_auto')]:
            row=next(r for r in revision if r['frame']==frame and r['requested_mode']==mode)
            source=root/f'output/phase3_revision/remapped_results/26_{frame}_{mode}/result.json'
            result=InspectionResult.load_json(source); result.validate_final()
            assert len(result.defects)==(36 if frame==1 else 35)
            assert result.statistics.total_defect_area_px==(20356 if frame==1 else 17709)
            config=InspectionConfig(pipeline_mode=PipelineMode(mode),advanced_debug=mode!='auto')
            if config.config_hash()!=result.algorithm_info.config_hash:
                raise ValueError('cannot initialize: exact original configuration candidate unavailable')
            sample.update(raw_file_name=result.input_info.file_name,raw_sha256=result.input_info.sha256)
            sample[key]={'baseline_commit':'1aa643d186ab2d5374723786a42193082aee3707',
                'algorithm_source_hash':result.algorithm_info.algorithm_version.removeprefix('source-sha256:'),
                'config_hash':result.algorithm_info.config_hash,'config_snapshot':to_dict(config),
                'source':{'result_json':source.relative_to(root).as_posix(),'result_json_sha256':sha256(source),
                    'engine_dir':Path(row['engine_directory']).relative_to(root).as_posix(),
                    'artifact_hashes':artifact_references(result)},
                'snapshot':semantic_snapshot(result,source.parent)}
        samples.append(sample)
    packages=[]
    for row in phase4['cases']:
        directory=Path(phase4['repository_root'])/row['result_id']
        packages.append({'sample_id':f'26_{row["frame"]}','result_id':row['result_id'],
            'directory':directory.relative_to(root).as_posix(),
            'manifest_sha256':sha256(directory/'manifest.json'),
            'baseline_commit':'c90b899b1559d8fcc4460499e4ec1c3474646840'})
    return {'golden_set_version':'1.0','schema_version':'1.0','package_format_version':'1.0',
        'baseline_commit':commit,'samples':samples,'repository_packages':packages}


def publish_candidate(candidate,path,*,approve=False,reason=None,allow_update=False,old_contract=None):
    path=Path(path)
    if not approve or not reason: raise PermissionError('refusing golden write: --approve and --reason required')
    old=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    if old is not None and not allow_update: raise PermissionError('existing golden requires explicit --allow-update and reviewed change report')
    changes=[]
    if old is not None:
        for sample in candidate['samples']:
            prior=next(s for s in old['samples'] if s['sample_id']==sample['sample_id'])
            for key in ('expected_full','expected_roi_bh','expected_auto'):
                before,after=prior[key],sample[key]
                changes.append({'sample_id':sample['sample_id'],'mode':key,
                    'old_algorithm_hash':before['algorithm_source_hash'],'new_algorithm_hash':after['algorithm_source_hash'],
                    'comparison':compare_snapshots(before['snapshot'],after['snapshot']).to_dict()})
    audit={'operation':'INITIALIZE_APPROVED_METADATA' if old is None else 'APPROVED_METADATA_UPDATE',
        'approved':True,'reason':reason,'recorded_at':datetime.now(timezone.utc).isoformat(),
        'old_commit':None if old is None else old['baseline_commit'],'new_commit':candidate['baseline_commit'],
        'changes':changes,'physical_evidence_modified':False}
    path.parent.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    audit_path=path.parent/('golden_change_report_'+stamp+'.json')
    with audit_path.open('x',encoding='utf-8') as stream: json.dump(audit,stream,ensure_ascii=False,indent=2)
    with audit_path.with_suffix('.md').open('x',encoding='utf-8') as stream:
        stream.write('# Golden metadata change audit\n\n'+json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    temporary=path.with_name('.'+path.name+'.tmp')
    with temporary.open('x',encoding='utf-8') as stream:
        json.dump(candidate,stream,ensure_ascii=False,indent=2); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary,path)
    return audit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approve',action='store_true'); parser.add_argument('--allow-update',action='store_true')
    parser.add_argument('--reason'); parser.add_argument('--candidate-manifest',help='explicit reviewed future metadata; does not overwrite physical evidence'); args=parser.parse_args()
    if not args.approve or not args.reason: parser.error('refusing execution: --approve and --reason required')
    root=Path(__file__).resolve().parents[1]
    target=root/'tests/golden/golden_manifest.json'
    if target.exists() and not args.allow_update: parser.error('golden already exists; explicit reviewed --allow-update required')
    commit=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    contract=root/'tests/golden/schema_contract.json'
    if contract.exists() and json.loads(contract.read_text(encoding='utf-8'))!=schema_contract():
        raise RuntimeError('schema contract differs; stop for schema review before any golden write')
    candidate=json.loads(Path(args.candidate_manifest).read_text(encoding='utf-8')) if args.candidate_manifest else build_candidate(root,commit)
    if candidate.get('golden_set_version')!='1.0' or candidate.get('schema_version')!='1.0':
        raise RuntimeError('candidate metadata version unsupported; no golden write')
    publish_candidate(candidate,target,approve=True,reason=args.reason,allow_update=args.allow_update)
    if not contract.exists():
        with contract.open('x',encoding='utf-8') as stream: json.dump(schema_contract(),stream,ensure_ascii=False,indent=2)
    print('GOLDEN_METADATA_INITIALIZED_OR_EXPLICITLY_UPDATED; physical evidence unchanged')


if __name__=='__main__': main()
