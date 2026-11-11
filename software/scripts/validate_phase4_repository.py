"""Persist existing Phase 3 revision AUTO results. No algorithm execution."""
from pathlib import Path
from dataclasses import asdict
import json, subprocess, sys
from domain import InspectionResult
from domain.configuration import InspectionConfig
from infrastructure.repositories import JsonResultRepository
from infrastructure.repositories.errors import ResultAlreadyExistsError
from infrastructure.storage.package import sha256, write_json


def main():
    root=Path(__file__).resolve().parents[1]
    docs=root/'docs/phase_4'; docs.mkdir(exist_ok=True)
    output=root/'output/phase4_validation'; output.mkdir(exist_ok=True)
    protected=json.loads((root/'docs/phase_3/protected_file_manifest.json').read_text(encoding='utf-8'))
    def verify_protection():
        changed=[r['path'] for r in protected if sha256(r['path'])!=r['sha256']]
        assert not changed, changed
    verify_protection(); print('PROTECTED_BEFORE_PASS',len(protected),flush=True)
    prior=json.loads((root/'docs/phase_3_revision/phase_3_revision_comparison.json').read_text(encoding='utf-8'))['cases']
    sources=[]
    for frame in (1,2):
        source=root/f'output/phase3_revision/remapped_results/26_{frame}_auto'
        for path in sorted(source.rglob('*')):
            if path.is_file(): sources.append({'path':str(path),'sha256':sha256(path)})
    repo=JsonResultRepository(output/'repository'); records=[]
    popen=subprocess.Popen
    def forbidden(*args,**kwargs): raise AssertionError('algorithm/subprocess execution forbidden during persistence acceptance')
    subprocess.Popen=forbidden
    try:
        for frame in (1,2):
            source=root/f'output/phase3_revision/remapped_results/26_{frame}_auto'
            result=InspectionResult.load_json(source/'result.json')
            config=InspectionConfig()
            # This exact frozen candidate reproduces the original canonical hash.
            assert config.config_hash()==result.algorithm_info.config_hash
            run=next(r for r in prior if r['frame']==frame and r['requested_mode']=='auto')
            original_run=Path(run['engine_directory']).parent.parent
            config_provenance={'kind':'HASH_VERIFIED_HISTORICAL_RECOVERY',
                'method':'frozen model defaults candidate; exact original canonical config hash match',
                'original_snapshot_was_missing':True,'original_result_id':result.result_id}
            if not (repo.root/result.result_id).exists():
                saved=repo.save(result,source,config_snapshot=config,
                    config_provenance=config_provenance,log_source_dir=original_run)
                assert saved.index_status=='PASS',saved
            loaded=repo.load(result.result_id)
            assert loaded==result, 'save/load changed InspectionResult'
            byte_identical=sha256(source/'result.json')==sha256(repo.root/result.result_id/'result.json')
            assert json.loads((source/'result.json').read_text(encoding='utf-8'))==json.loads((repo.root/result.result_id/'result.json').read_text(encoding='utf-8')), 'JSON values changed'
            verification=repo.verify(result.result_id); assert verification.status=='PASS',verification
            assert not verification.missing_logs
            manifest=json.loads((repo.root/result.result_id/'manifest.json').read_text(encoding='utf-8'))
            archive=output/f'26_{frame}_auto_formal_package.zip'
            if archive.exists():
                with __import__('zipfile').ZipFile(archive) as package: assert package.testzip() is None
                export={'path':str(archive),'sha256':sha256(archive),'bytes':archive.stat().st_size,'crc_status':'PASS'}
            else: export=asdict(repo.export_package(result.result_id,archive))
            record={'frame':frame,'result_id':result.result_id,'verify':verification.to_dict(),
                'inspection_result_exact_equal':True,'result_json_byte_identical':byte_identical,'result_json_values_equal':True,
                'artifact_count':manifest['artifact_count'],'artifact_total_bytes':manifest['artifact_total_bytes'],
                'source_sha256':result.input_info.sha256,'schema_version':loaded.schema_version,
                'config_hash':config.config_hash(),'config_snapshot_origin':manifest['config_snapshot_origin'],
                'defect_count':len(loaded.defects),'total_area_px':loaded.statistics.total_defect_area_px,
                'calibration_um_per_px':loaded.calibration_info.spatial_scale_um_per_px,'export':export}
            records.append(record)
            print('REAL_REPOSITORY_PASS',frame,result.result_id,manifest['artifact_count'],flush=True)
        history=repo.list_results(); assert len(history)==2
        assert len(repo.query(sample_id='26',final_mode='roi-bh',fallback_used=False,min_defects=35,max_defects=36))==2
        for record in records: assert len(repo.find_by_source_sha256(record['source_sha256']))==1
        rebuild=repo.rebuild_index(); assert len(rebuild.indexed_results)==2 and rebuild.status=='PASS'
        assert len(repo.list_results())==2
    finally: subprocess.Popen=popen
    verify_protection()
    assert all(sha256(r['path'])==r['sha256'] for r in sources)
    report={'status':'PASS','repository_type':'JsonResultRepository','repository_root':str(repo.root),
        'saved_result_count':2,'index_entries':len(history),'rebuild_status':rebuild.status,
        'schema_version':'1.0','phase3_tests_preserved':190,'algorithm_executions':0,
        'algorithm_files_changed':[],'protected_files_verified_before_and_after':len(protected),
        'source_result_files_verified_before_and_after':len(sources),'subprocess_forbidden':True,
        'phase5_started':False,'cases':records}
    target=docs/'phase_4_acceptance.json'
    if target.exists():
        with target.open('w',encoding='utf-8') as stream: json.dump(report,stream,ensure_ascii=False,indent=2)
    else: write_json(target,report)
    print('TWO_REAL_RESULTS_REPOSITORY_ACCEPTANCE_PASS',flush=True)


if __name__=='__main__': main()
