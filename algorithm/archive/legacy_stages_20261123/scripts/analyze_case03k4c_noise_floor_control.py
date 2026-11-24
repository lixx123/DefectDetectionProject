"""Case03-K4c: hold all spot gate parameters; change only RAW noise floor
on the *entire first 24 labelled control set*. Labels never used as inputs
to masks/gates; report user judgements only after evaluation. Read-only.
"""
from pathlib import Path
from dataclasses import replace
import json,sys
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03k3_spot_contour_pilot import (
    PilotConfig,raw_outer_envelope,decision
)
BASE=cfg.OUTPUT_ROOT/"case03k_light_review/run_20261012_small_candidate_manual_review_v2"
S=BASE/"K3_dualstage_contour_pilot_v1"
OUT=cfg.OUTPUT_ROOT/"case03k_expanded_validation/run_20261012_240_green_scale_sensitivity_v1/K4c_noise_floor_safety_control_v1"
if OUT.exists():raise FileExistsError(OUT)
OUT.mkdir()
manual=pd.read_csv(BASE/"revision_074_obvious_dark_spot_20261012/first_pass_review_30_labels_corrected.csv",keep_default_na=False,encoding="utf-8-sig")
manual=manual[manual.sample_kind=="SMALL_CANDIDATE"].copy()
assert len(manual)==24
raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
cfg0=PilotConfig()
results=[]
for item in manual.to_dict("records"):
    sid=item["sample_id"]
    with np.load(S/"masks"/(sid+".npz"),allow_pickle=False) as z:
        source=z["original_J5_detected"].astype(bool)
        other=z["competitor_J5_detected"].astype(bool)
        h31=z["old_H170_230_anchor"].astype(bool)
        h61=z["add61_H170_230_anchor"].astype(bool)
    x0,y0,x1,y1=[int(item[k]) for k in ("x0","y0","x1","y1")]
    image=np.asarray(raw[y0:y1,x0:x1],np.uint16)
    center=(float(item["target_x_global"])-x0,
            float(item["target_y_global"])-y0)
    for floor in (3.,2.,1.5):
        cc=replace(cfg0,raw_noise_sigma_multiplier=floor)
        proposed,audit=raw_outer_envelope(image,source,center,cc)
        status,reasons=decision(source,h31,h61,proposed,other,audit,cc)
        results.append({
            "sample_id":sid,
            "noise_floor":floor,
            "visual_human_label_posthoc":item["manual_candidate_label"],
            "source_J5_area":int(source.sum()),
            "BH61_area":int(h61.sum()),
            "raw_candidate_area":int(proposed.sum()),
            "overlaps_competing_J5_px":int(np.count_nonzero(proposed&other)),
            "noise_floor_threshold_DN":audit["raw_boundary_threshold_DN"],
            "provisional_guard_pass":status=="PROVISIONAL_OUTER_SUGGESTION",
            "rejection_reasons":";".join(reasons),
            "source_masks_unchanged":True
        })
df=pd.DataFrame(results)
df.to_csv(OUT/"first24_noise_floor_3_2_1p5_audit.csv",encoding="utf-8-sig",index=False)
summary={
 "sample_count":len(manual),
 "conditions":[3,2,1.5],
 "source_frame":"26 (1).raw",
 "new_human_labels":0,
 "labels_used_for_candidate_selection":False,
 "method_already_developed_on_these_24":True,
 "manual_labels_are_posthoc_only":True,
 "original_source_and_J5_unchanged":True,
 "changes_to_main_K3_production":False,
 "passes_by_floor_and_human_label":[
    {"floor":float(k),"human_label":str(label),"total":int(len(g)),
     "pass":int(g.provisional_guard_pass.sum())}
    for (k,label),g in df.groupby(["noise_floor","visual_human_label_posthoc"])
 ],
 "note":"Posthoc developer controls; cannot estimate independent performance"
}
(OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),
                                 encoding="utf-8")
print("K4C_CONTROL_COUNTS")
print(df.groupby(["noise_floor","visual_human_label_posthoc"]).provisional_guard_pass.agg(["size","sum"]).to_string())
print("K4C_CASES_PROVISIONAL")
print(df[df.provisional_guard_pass][["sample_id","noise_floor","visual_human_label_posthoc","raw_candidate_area"]].to_string(index=False))
print("K4C_DONE",str(OUT))
