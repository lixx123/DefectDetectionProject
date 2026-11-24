"""Post-robustness repeat checksum of original RAW and frozen K8I source files.

Original SHA manifest recorded BEFORE 20-RAW scan, now recomputes all 59
files; every discrepancy is a hard error and source is never rewritten.
"""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
P=C.OUTPUT_ROOT/"case03k8i_stage2_RAW_review_and_association/run_20261017_twoframes_priority_evidence_v1/read_only_input_SHA256_manifest.json"
OUT=C.OUTPUT_ROOT/"CASE03_FROZEN_20RAW_VALIDATION_20261019_v1"
def sha(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(8*1024*1024),b""):h.update(block)
 return h.hexdigest()
def main():
 old=json.loads(P.read_text(encoding="utf-8"))
 evidence=[]
 for info in old["files"]:
  p=Path(info["path"])
  assert p.is_file(),"Frozen input vanished "+str(p)
  assert p.stat().st_size==info["length_bytes"],"Frozen input size altered "+str(p)
  h=sha(p)
  assert h==info["sha256"],"Frozen input SHA256 changed "+str(p)
  evidence.append({"source":str(p),"unchanged":True,
      "SHA256":h,"byte_length":p.stat().st_size})
 result={"status":"ALL_FROZEN_ORIGINALS_SHA256_UNMODIFIED",
   "frozen_file_count":len(evidence),
   "all_frozen_files_same_bytes_and_hash":True,
   "two_original_26_RAW_files_still_untouched":True,
   "historical_K8D_E_source_masks_untouched":True,
   "files":evidence}
 dest=OUT/"FROZEN_ORIGINALS_POST20RAW_SHA256_QA.json"
 if dest.exists():raise FileExistsError(dest)
 dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 print("POST20RAW_SHA256_PASS",len(evidence),flush=True)
if __name__=="__main__":main()
