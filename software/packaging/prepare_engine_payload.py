"""Copy frozen source bytes and a minimal, explicit historical asset closure."""
from pathlib import Path
import os,sys,json,shutil,hashlib
R=Path(os.environ['ENGINE_PROJECT']);A=Path(os.environ.get('ENGINE_REFERENCE_ROOT',str(R.parent/'DefectDetectionProject')));P=Path(os.environ.get('ENGINE_PAYLOAD_OUT',str(R/'output/engine_payload_v1')));P.mkdir(exist_ok=False);dest=P/'algorithm'
source=[A/'main.py',A/'requirements.txt']
for d in ['config','src','scripts']:source.extend((A/d).rglob('*.py'))
assets=[]
base=A/'outputs'
for frame,j4,j5 in [(1,'run_20261012_frame26_1_full_j4_v1','run_20261012_frame26_1_global_j5_v1'),(2,'run_20261012_frame26_2_J4_independent_v1','run_20261012_frame26_2_J5_independent_v1')]:
 assets.extend(base/'case03j5_global'/j5/n for n in ['global_object_membership.csv','global_defects.csv'])
 assets.append(base/'case03k8i_full_frame_lineage/run_20261015_sample26_2frames_fullcandidate_lineage_v1'/f'frame26_{frame}/end_to_end_candidate_lineage.csv')
 b=base/'case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2'/f'frame26_{frame}'
 assets.append(b/'summary.json');assets.extend(b.glob('band_*_B_hysteresis_mask_cropped.png'))
 e=base/'case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1'/f'frame26_{frame}'
 assets.append(e/'K8E_unique_group_union_measurements.csv');assets.extend((e/'group_detail').glob('*.npz'))
 ii=base/'case03k8i_stage2_RAW_review_and_association/run_20261017_twoframes_priority_evidence_v1'/f'frame26_{frame}'
 assets.extend(ii.glob('*.csv'));assets.extend(ii.rglob('*.npz'))
 assets.append(base/'CASE03_UNIFIED_FINAL_DETECTOR_26_1_26_2_20261019_v2'/f'26_{frame}/summary.json')
usr=base/'case03k8i_stage2_user_confirmed_reviews/run_20261017_F1_B02_B04_two_darkspots_v1'
assets.extend(usr.rglob('*.csv'));assets.extend(usr.rglob('*.npz'))
# NPZ references used by negative_objects and user-confirmed outer masks.
import csv
for f in list(assets):
 if f.suffix=='.csv' and ('new_exact_group_union_review' in f.name or 'two_user_confirmed' in f.name):
  for row in csv.DictReader(f.open(encoding='utf-8-sig')):
   for key in ['npz_file','verified_copy_npz']:
    if row.get(key):assets.append(Path(row[key]))
for p in sorted(set(source+assets)):
 if not p.is_file() or not p.resolve().is_relative_to(A):raise ValueError('Missing/outside packaged asset: '+str(p))
 t=dest/p.relative_to(A);t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,t)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
records=[dict(path=p.relative_to(A).as_posix(),sha256=sha(p)) for p in sorted(set(source))]
digest=hashlib.sha256(json.dumps(records,sort_keys=True,separators=(',',':')).encode()).hexdigest()
meta=dict(algorithm_source_sha256=digest,source_files=len(source),source_records=records,historical_assets=[dict(path=p.relative_to(A).as_posix(),sha256=sha(p)) for p in sorted(set(assets))],purpose='Read-only historical approvals/identity/lineage required by frozen v1; no InspectionResult or final defect output replay',copied_bytes=sum(p.stat().st_size for p in dest.rglob('*') if p.is_file()))
(P/'payload_manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(root=str(P),source_files=len(source),source_records=records,historical_assets=len(set(assets)),algorithm_source_sha256=digest,bytes=meta['copied_bytes'])))
