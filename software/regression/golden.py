"""Frozen real evidence, current decoders/mappers and isolated repository checks."""
from contextlib import contextmanager
from pathlib import Path
import copy, json, shutil, subprocess
from domain import InspectionResult
from infrastructure.storage.package import artifact_references, sha256
from infrastructure.storage.paths import safe_path
from infrastructure.repositories import JsonResultRepository
from infrastructure.repositories.verifier import ResultPackageVerifier
from core.adapters.audit_mapper import map_audit
from core.runtime.resources import ResourceCollector
from .comparator import semantic_snapshot, compare_snapshots, digest, plain, normalize_ids, content_refs


@contextmanager
def no_engine_execution():
    original=subprocess.Popen
    def reject(*args,**kwargs): raise RuntimeError('GOLDEN forbids subprocess/reference engine execution')
    subprocess.Popen=reject
    try: yield
    finally: subprocess.Popen=original


def load_manifest(root,manifest_path=None):
    path=Path(manifest_path) if manifest_path else Path(root)/'tests/golden/golden_manifest.json'
    payload=json.loads(path.read_text(encoding='utf-8'))
    if payload.get('golden_set_version')!='1.0' or len(payload.get('samples',[]))!=2:
        raise ValueError('expected version 1.0 and two approved golden samples')
    return payload


def run_golden(root,scratch,*,manifest_path=None):
    root,scratch=Path(root),Path(scratch); scratch.mkdir(parents=True,exist_ok=True)
    report={'status':'FAIL','golden_set_version':'1.0','cases':[],'repository_cases':[],
        'algorithm_executions':0,'errors':[],'warnings':[],'repository_status':'FAIL'}
    try: manifest=load_manifest(root,manifest_path)
    except Exception as exc: report['errors'].append(str(exc)); return report
    tracked_before={}
    with no_engine_execution():
        for sample in manifest['samples']:
            for mode in ('full','roi-bh','auto'):
                expected=sample[{'full':'expected_full','roi-bh':'expected_roi_bh','auto':'expected_auto'}[mode]]
                record={'sample_id':sample['sample_id'],'mode':mode,'status':'FAIL','errors':[]}
                try:
                    source=safe_path(root,expected['source']['result_json'])
                    tracked_before[str(source)]=sha256(source)
                    if sha256(source)!=expected['source']['result_json_sha256']: raise ValueError('frozen result JSON hash changed')
                    result=InspectionResult.load_json(source); result.validate_final()
                    current=semantic_snapshot(result,source.parent)
                    comparison=compare_snapshots(expected['snapshot'],current)
                    refs=artifact_references(result)
                    if refs!=expected['source']['artifact_hashes']: raise ValueError('artifact reference set/hash changed')
                    for relative,wanted in refs.items():
                        path=safe_path(source.parent,relative); tracked_before[str(path)]=sha256(path)
                        if sha256(path)!=wanted: raise ValueError('golden artifact bytes changed: '+relative)
                    # Exercise the current audit mapper against the real immutable engine CSVs.
                    engine=root/expected['source']['engine_dir']
                    ownership={uid:d.identity.defect_id for d in result.defects for uid in d.detection.candidate_ids}
                    remapped=map_audit(engine,ownership,ResourceCollector(scratch/(sample['sample_id']+'_'+mode+'_audit')),
                        reference_root=root.parent/'DefectDetectionProject')
                    temporary=copy.copy(result); temporary.audit_log=remapped
                    remapped_view=semantic_snapshot(temporary,source.parent)
                    if remapped_view['audit']!=expected['snapshot']['audit']: raise ValueError('current audit mapper differs from frozen semantics')
                    # Scale is an actual historical field, never supplied by current global YAML.
                    scale=result.calibration_info.spatial_scale_um_per_px
                    if scale!=3.2: raise ValueError('historical scale changed')
                    for defect in result.defects:
                        if defect.geometry.length_um!=defect.geometry.length_px*scale: raise ValueError('linear scale mismatch')
                        if defect.geometry.area_um2!=defect.geometry.area_px*scale**2: raise ValueError('area scale mismatch')
                    approved=sorted(d.geometry.area_px for d in result.defects if d.extensions.get('human_confirmed_darkspot'))
                    if approved!=sample['approved_darkspot_areas']: raise ValueError('confirmed darkspots disappeared/changed')
                    record.update(status=comparison.status,comparison=comparison.to_dict(),artifact_count=len(refs),
                        mask_hash_match=not comparison.mask_changes,object_level_match=not any((comparison.added_objects,comparison.disappeared_objects,comparison.object_semantic_changes)),
                        roi_band_match=not comparison.ROI_changes,audit_semantics_match=not comparison.audit_changes,
                        statistics_match=not comparison.statistics_changes,defect_count=len(result.defects),
                        total_area_px=result.statistics.total_defect_area_px,validate_final='PASS',current_audit_mapper='PASS')
                except Exception as exc: record['errors'].append(f'{type(exc).__name__}: {exc}')
                report['cases'].append(record)
        repository=JsonResultRepository(scratch/'repository')
        for package in manifest['repository_packages']:
            record={'sample_id':package['sample_id'],'result_id':package['result_id'],'status':'FAIL','errors':[]}
            try:
                source=root/package['directory']
                if sha256(safe_path(source,'manifest.json'))!=package['manifest_sha256']: raise ValueError('frozen package manifest changed')
                verification=ResultPackageVerifier().verify(source)
                if verification.status!='PASS': raise ValueError(str(verification.to_dict()))
                for relative in ['manifest.json',*[e['relative_path'] for e in json.loads((source/'manifest.json').read_text(encoding='utf-8'))['package_files']]]:
                    path=safe_path(source,relative); tracked_before[str(path)]=sha256(path)
                destination=repository.root/package['result_id']
                shutil.copytree(source,destination,symlinks=True)
                loaded=repository.load(package['result_id'])
                sample=next(s for s in manifest['samples'] if s['sample_id']==package['sample_id'])
                compared=compare_snapshots(sample['expected_auto']['snapshot'],semantic_snapshot(loaded,destination))
                if compared.status=='FAIL': raise ValueError(str(compared.to_dict()))
                archive=repository.export_package(package['result_id'],scratch/(package['sample_id']+'.zip'))
                record.update(status='PASS',verify=verification.to_dict(),comparison=compared.to_dict(),zip_crc=archive.crc_status,zip_sha256=archive.sha256)
            except Exception as exc: record['errors'].append(f'{type(exc).__name__}: {exc}')
            report['repository_cases'].append(record)
        rebuilt=repository.rebuild_index()
        queried=repository.query(sample_id='26',final_mode='roi-bh',fallback_used=False)
        report['repository_index_entries']=len(rebuilt.indexed_results)
        report['repository_query_count']=len(queried)
        report['repository_status']='PASS' if (rebuilt.status=='PASS' and len(rebuilt.indexed_results)==2 and len(queried)==2 and all(r['status']=='PASS' for r in report['repository_cases'])) else 'FAIL'
        changed=[path for path,value in tracked_before.items() if not Path(path).is_file() or sha256(path)!=value]
        report['source_evidence_files_checked']=len(tracked_before)
        report['golden_evidence_changed']=changed
        if changed: report['errors'].append('golden inputs mutated during validation')
    failures=[r for r in report['cases'] if r['status']=='FAIL']
    if not failures and len(report['cases'])==6 and report['repository_status']=='PASS' and not report['errors']:
        report['status']='PASS_WITH_WARNINGS' if any(r['status']=='PASS_WITH_WARNINGS' for r in report['cases']) else 'PASS'
    return report
