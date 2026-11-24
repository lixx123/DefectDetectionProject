"""K6 audit archive: exact source-vs-K5 masks for seven second-frame
outer-contour proposals; deduplicate proposed J5 membership ID sets.
No original J4/J5 source masks or labels are changed.
"""
from pathlib import Path
from collections import defaultdict
import json,sys
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.blackhat import black_hat_uint16
from src.detection.case03k3_spot_contour_pilot import (
    PilotConfig,component_seeded_H,raw_outer_envelope)
from src.detection.case03k5_adaptive_grouping import (
    AdaptiveConfig,choose_adaptive_envelope,audit_object_membership)
from scripts.run_case03k6_second_frame_K5 import (
    J4,J5,RAW,RESP,OUT,original_id_map
)
PLT=PilotConfig();ADP=AdaptiveConfig()
D=OUT/"reversible_mask_audit_top7"
if D.exists():raise FileExistsError(D)
D.mkdir()
sel=pd.read_csv(OUT/"fixed_selection_and_blank_manual_review.csv",
                encoding="utf-8-sig",keep_default_na=False)
res=pd.read_csv(OUT/"all_288_frozen_K5_audit.csv",encoding="utf-8-sig")
interesting=res[res.K5_adaptive_area_px2>0]
assert len(interesting)==7
members=pd.read_csv(J5/"global_object_membership.csv",encoding="utf-8-sig")
frame=pd.read_csv(J5/"global_defects.csv",encoding="utf-8-sig")
area=dict(zip(frame.global_defect_id,frame.source_area_px2.astype(int)))
lookup=dict(zip(zip(members.source_tile_id,members.source_local_object_index.astype(int)),
                members.global_defect_id))
raw=np.memmap(RAW,mode="r",dtype=">u2",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
resp=np.load(RESP,mmap_mode="r",allow_pickle=False)
byselection=sel.set_index("sample_id")
out=[]
groupproposals=[]
for record in interesting.to_dict("records"):
    sid=record["sample_id"]
    case=byselection.loc[sid].to_dict()
    case["sample_id"]=sid
    idmap,source=original_id_map(case,lookup)
    x0,y0,x1,y1=map(int,(case["x0"],case["y0"],case["x1"],case["y1"]))
    im=np.asarray(raw[y0:y1,x0:x1],np.uint16)
    work=np.asarray(raw[y0-72:y1+72,x0-72:x1+72],np.uint16)
    bh0=np.asarray(resp[y0-72:y1+72,x0-72:x1+72],np.uint16)
    bh61=np.maximum(bh0,black_hat_uint16(work,61,"ellipse"))
    seed=np.zeros(work.shape,bool)
    seed[72:200,72:200]=source
    H31=component_seeded_H(bh0,seed,PLT)[72:200,72:200]
    H61=component_seeded_H(bh61,seed,PLT)[72:200,72:200]
    center=(float(case["center_x_global"])-x0,float(case["center_y_global"])-y0)
    hyp,audit,meta=choose_adaptive_envelope(im,source,center,int(H61.sum()),PLT,ADP)
    prior,prioraudit=raw_outer_envelope(im,source,center,PLT)
    assert int(hyp.sum())==int(record["K5_adaptive_area_px2"])
    assert int(prior.sum())==int(record["raw_k3_area_px2"])
    assert int(H61.sum())==int(record["H61_area_px2"])
    assert int(source.sum())==int(record["original_source_area_px2"])
    assert meta["floor_selected_sigma"]==record["noise_multiplier_chosen"]
    sibling=audit_object_membership(hyp,case["source_global_defect_id"],
            idmap,area,audit,ADP)
    assert sibling["group_status"]==record["group_status"]
    np.savez_compressed(D/(sid+"_audit_masks.npz"),
        global_roi_xyxy=np.asarray((x0,y0,x1,y1),np.int32),
        original_J5_source=source.astype(np.uint8),
        other_J5_original_sources=((idmap!="")&~source).astype(np.uint8),
        original_H31=H31.astype(np.uint8),
        augmented_H61=H61.astype(np.uint8),
        original_RAW_k3_envelope=prior.astype(np.uint8),
        K5_adaptive_envelope=hyp.astype(np.uint8))
    out.append({
      "sample_id":sid,
      "frame2_global_ID":case["source_global_defect_id"],
      "J5_source_area_px2":int(source.sum()),
      "H61_area_px2":int(H61.sum()),
      "K5_outer_area_px2":int(hyp.sum()),
      "group_status":sibling["group_status"],
      "IDs_covered_by_outer":sibling["competing_J5_ids"],
      "total_original_J5_IDs_touched":len(sibling["competing_J5_ids"])+1,
      "official_J5_membership_unchanged":True,
      "physical_contour_ground_truth_available":False
    })
    if sibling["group_status"]=="COHERENT_GROUP_REVIEW":
        groupproposals.append({
            "sample_id":sid,
            "member_IDs":sibling["proposed_review_group_ids"],
            "K5_area_px2":int(hyp.sum())
        })
proposals=defaultdict(list)
for g in groupproposals:proposals[tuple(sorted(g["member_IDs"]))].append(g)
dedup=[]
for i,(members,trial) in enumerate(sorted(proposals.items()),1):
    dedup.append({
       "review_group_id":f"FRAME2_K6_GROUP_{i:03d}",
       "member_IDs":list(members),
       "supporting_samples":[q["sample_id"] for q in trial],
       "outer_candidates_area_px2":[q["K5_area_px2"] for q in trial],
       "manual_confirm_same_physical_spot":"",
       "manual_confirm_outer_extent":"",
       "manual_comments":"",
       "J5_original_IDs_unmodified":True
    })
(D/"seven_object_pixel_audit.json").write_text(
 json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
(D/"deduplicated_candidate_groups_review.json").write_text(
 json.dumps(dedup,ensure_ascii=False,indent=2),encoding="utf-8")
m=pd.DataFrame([{
    "review_group_id":g["review_group_id"],
    "old_J5_member_IDs":";".join(g["member_IDs"]),
    "supporting_K6_samples":";".join(g["supporting_samples"]),
    "trial_area_px2":";".join(map(str,g["outer_candidates_area_px2"])),
    "human_same_physical_spot":"",
    "human_contour_coverage":"",
    "review_notes":"",
    "source_IDs_preserved":True,
} for g in dedup])
m.to_csv(D/"deduplicated_candidate_groups_review_blank.csv",
         encoding="utf-8-sig",index=False)
pending=pd.DataFrame([{
     "sample_id":r["sample_id"],
     "frame2_J5_ID":r["frame2_global_ID"],
     "source_area_px2":r["J5_source_area_px2"],
     "K5_outer_px2":r["K5_outer_area_px2"],
     "group_status":r["group_status"],
     "human_is_real_dark_spot":"",
     "human_coverage_percent_estimate":"",
     "human_other_J5_belongs_to_same_spot":"",
     "human_comments":""
} for r in out])
pending.to_csv(D/"seven_new_outlines_manual_review_blank.csv",
               encoding="utf-8-sig",index=False)
print("K6_SECOND_FRAME_MASKS_ARCHIVED",json.dumps({
    "seven_pixel_exact_reproductions":len(out),
    "source_saved_mask_pixels_unchanged":True,
    "group_proposals_before_dedup":len(groupproposals),
    "distinct_groups_after_dedup":len(dedup),
    "needs_human_labels":True,
    "path":str(D)
},ensure_ascii=False),flush=True)
