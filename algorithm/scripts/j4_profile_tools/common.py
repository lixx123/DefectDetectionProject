"""Read-only baseline discovery and diagnostic serialization."""
from pathlib import Path
import json,hashlib,csv,sys
ROOT=Path(__file__).resolve().parents[2]
RAW=Path(r'D:\疵病检测\疵病实测数据\260624批次表观（5片）\27-1_000.raw')
SOFT=Path(r'D:\疵病检测\DefectInspectionSoftware')
PRIOR=Path(r'C:\Users\lixia\Documents\Codex\2026-10-20\an\outputs\RAW_Performance_20261106_27_1_retry1')
OUT=ROOT/'outputs/J4_PROFILE_27_1_20261107'
def native(p):
    p=Path(p).absolute();return p if str(p).startswith('\\\\?\\') else Path('\\\\?\\'+str(p))
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def dump(p,d):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def csvwrite(p,rows,fields=None):
    rows=list(rows);fields=fields or list(rows[0]);
    with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
def baseline():return native(read(OUT/'PROFILE_BASELINE_RUN.json')['run_directory'])
def preflight():
    if OUT.exists():
        assert (OUT/'protected_original_sources.json').exists()
        assert all(sha(ROOT/p)==h for p,h in read(OUT/'protected_original_sources.json').items())
    else:OUT.mkdir(parents=True,exist_ok=False)
    original={str(p.relative_to(ROOT)):sha(p) for folder in ['src','scripts','config'] for p in (ROOT/folder).rglob('*.py') if 'j4_profile_tools' not in p.parts and p.name!='profile_j4_performance.py'}
    original['main.py']=sha(ROOT/'main.py')
    dump(OUT/'protected_original_sources.json',original)
    target_sha=sha(RAW);runs=[]
    # Enumerate native algorithm outputs, including failed/incomplete inputs.
    for p in native(ROOT/'outputs').rglob('input.json'):
        if p.is_relative_to(native(OUT)):continue
        try:d=read(p)
        except Exception:continue
        if d.get('SHA256')!=target_sha and '27-1_000' not in str(d.get('path','')):continue
        a=read(p.parent/'acceptance.json') if (p.parent/'acceptance.json').exists() else {}
        j=p.parent/'upstream_J4/fresh/run_status.json';complete=(p.parent/'FINAL_DEFECTS_AND_MEASUREMENTS.csv').exists() and j.exists() and read(j).get('stage')=='J4_COMPLETE'
        runs.append(dict(path=str(p.parent),classification='COMPLETE_ALGORITHM_HISTORY' if complete else 'FAILED_OR_INCOMPLETE',acceptance=a.get('status'),J4_seconds=a.get('J4_seconds')))
    prior=read(PRIOR/'timing_report.json');assert prior['status']=='PASS'
    b=native(Path(prior['run_dir'])/'engine/roi-bh');receipt=read(b.parents[3]/'engine_receipt.json')
    assert receipt['status']=='PASS' and receipt['input_sha256']==target_sha
    a=read(b/'acceptance.json');assert read(b/'upstream_J4/fresh/run_status.json')['stage']=='J4_COMPLETE'
    runs.append(dict(path=str(b),classification='LATEST_COMPLETE_SHIPPED_ENGINE_20261106',outer_receipt='PASS',J4_seconds=a['J4_seconds']))
    csvwrite(OUT/'baseline_run_inventory.csv',runs,['path','classification','acceptance','outer_receipt','J4_seconds'])
    # Compare current production sources to the exact recorded frozen source bytes.
    mismatches=[];checked=[]
    for entry in read(b/'source_SHA256_at_start.json'):
        relative=entry['path'].replace('\\','/').split('/algorithm/',1)[1];p=ROOT/relative
        actual=sha(p) if p.exists() else None
        checked.append(dict(path=relative,baseline_sha256=entry['sha256'],current_sha256=actual))
        if actual!=entry['sha256']:mismatches.append(relative)
    dump(OUT/'baseline_source_match.json',dict(checked=checked,mismatches=mismatches))
    import ast
    class StripDocs(ast.NodeTransformer):
        def generic_visit(self,node):
            node=super().generic_visit(node)
            if isinstance(node,(ast.Module,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and node.body and isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant) and isinstance(node.body[0].value.value,str):node.body.pop(0)
            return node
    behavioral=[]
    for name in mismatches:
        entry=next(e for e in read(b/'source_SHA256_at_start.json') if e['path'].replace('\\','/').endswith('/'+name))
        def tree(text):return ast.dump(StripDocs().visit(ast.parse(text)),include_attributes=False)
        if tree((ROOT/name).read_text(encoding='utf-8'))!=tree(Path(entry['path']).read_text(encoding='utf-8')):behavioral.append(name)
    dump(OUT/'baseline_source_match.json',dict(checked=checked,byte_mismatches=mismatches,behavioral_mismatches=behavioral,comparison='AST ignores comments and standalone docstrings; every original file hash preserved separately'))
    assert not behavioral,('Production executable AST differs from baseline',behavioral)
    d=dict(run_directory=str(b),input=str(RAW),input_sha256=target_sha,source_sha256=receipt['engine']['algorithm_source_sha256'],source_files_compared=len(checked),production_source_files_byte_equal=not mismatches,production_executable_AST_equal=True,doc_comment_only_differences=mismatches,client_requested_mode=prior['mode'],**a,outer_status='PASS',software_head=prior['head'],selection='Latest successful 2026-11-06 shipped-engine run, despite residing outside algorithm outputs; not a failed run or historical replay')
    dump(OUT/'PROFILE_BASELINE_RUN.json',d)
    required=['main.py','config/user_config.py','scripts/run_two_level_unified.py','scripts/run_case03j4_fullscan.py','scripts/run_case03j5_global_merge.py','scripts/run_case03t_threeway_comparison.py','src/detection/two_level_roi.py','src/detection/case03k8a_band_locator.py','src/detection/case03e2_hseeded.py','src/detection/case03t_hseeded_variable.py','src/detection/local_boundary_refinement.py','src/detection/case03g_joint_gate.py','src/detection/case03h_background_texture.py','src/detection/case03j_fragment_association.py','src/detection/case03j_continuous_contour.py']
    (OUT/'production_code_readings.txt').write_text('\n'.join('\n### '+p+'\n'+(ROOT/p).read_text(encoding='utf-8') for p in required),encoding='utf-8')
    print('BASELINE_IDENTIFIED',b,flush=True)
def verify_sources():
    expected=read(OUT/'protected_original_sources.json');changed=[p for p,h in expected.items() if sha(ROOT/p)!=h]
    dump(OUT/'source_protection_after.json',dict(original_files_checked=len(expected),changed=changed,raw_sha256=sha(RAW),algorithm_parameters_changed=False))
    assert not changed and sha(RAW)==read(OUT/'PROFILE_BASELINE_RUN.json')['input_sha256']
