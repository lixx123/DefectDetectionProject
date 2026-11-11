"""Archive original-RAW and frozen-source SHA256 provenance AFTER K8I stage 2."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts.run_case03k8i_stage2_fullband_priority_contours import (
    OUT,K8I,K8B,K8A,K8D,K8E,PRIOR)
def digest(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  while True:
   block=f.read(8*1024*1024)
   if not block:break
   h.update(block)
 return h.hexdigest()
def run():
 files=[]
 for fr in (1,2):
  files.extend([
    C.DATA_ROOT/f"26 ({fr}).raw",
    K8I/f"frame26_{fr}"/"end_to_end_candidate_lineage.csv",
    K8I/f"frame26_{fr}"/"render_visibility_reconciliation.json",
    K8B/f"frame26_{fr}"/"original_J5_object_center_workband_classification.csv",
    K8A/f"frame26_{fr}"/"band_id_fullres.png",
    K8D/f"frame26_{fr}"/"all_K8D_original_vs_outer_review.csv",
    K8E/f"frame26_{fr}"/"K8E_unique_group_union_measurements.csv"])
  for p in sorted((K8B/f"frame26_{fr}").glob("band_*_B_hysteresis_mask_cropped.png")):
   files.append(p)
  for p in sorted((K8E/f"frame26_{fr}"/"group_detail").glob("*_EXACT_GROUP_MASK.npz")):
   files.append(p)
 files.extend([
  ROOT/"src/detection/case03k3_spot_contour_pilot.py",
  ROOT/"src/detection/case03k8d_group_stability.py",
  ROOT/"src/detection/case03k8e_group_hypothesis.py",
  ROOT/"scripts/run_case03k8i_stage2_fullband_priority_contours.py",
  ROOT/"scripts/verify_case03k8i_stage2_fullband_priority_contours.py",
  ROOT/"scripts/build_case03k8i_stage2_review_pack.py"])
 rows=[]
 for p in files:
  if not p.is_file():raise FileNotFoundError(p)
  rows.append({"path":str(p),"length_bytes":p.stat().st_size,
               "sha256":digest(p)})
 out=OUT/"read_only_input_SHA256_manifest.json"
 if out.exists():raise FileExistsError(out)
 out.write_text(json.dumps({
    "stage":"K8I_STAGE2_POST_RUN_FROZEN_INPUT_PROVENANCE",
    "no_modification_by_manifest_script":True,
    "SHA256_is_for_future_reproducibility_not_proof_of_historical_truth":True,
    "files":rows},ensure_ascii=False,indent=2),encoding="utf-8")
 print("K8I_STAGE2_INPUT_SHA256_MANIFEST_CREATED",len(rows),
       "raw_sum_bytes",sum(x["length_bytes"] for x in rows if x["path"].endswith(".raw")),
       flush=True)
if __name__=="__main__":run()
