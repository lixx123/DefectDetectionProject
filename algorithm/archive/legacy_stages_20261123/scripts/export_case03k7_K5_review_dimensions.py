"""Case03-K7: separate original J5 and PROVISIONAL K5 size-labelled review maps.

Area and length in detector-equivalent um and um². NEVER replaces official
source area or creates new approved defect IDs. Outlines drawn 1 DISPLAY px
after resizing. Includes source and estimated outer side by side.
"""
from pathlib import Path
import json,sys
import pandas as pd,numpy as np,cv2
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03i_size_grade import max_feret_centers_px
from scripts.run_case03g_joint_noise_refinement import save_png,gray
from scripts.run_case03k7_physical_annotations import RUN_DIR,SOURCE,PITCH

def card(name,raw,mask,source_color,head,footer):
    a=gray(raw)
    if a.ndim==2:img=cv2.cvtColor(a,cv2.COLOR_GRAY2BGR)
    else:img=a.copy()
    img=cv2.resize(img,(384,384),interpolation=cv2.INTER_NEAREST)
    seg=cv2.resize(np.uint8(mask),(384,384),interpolation=cv2.INTER_NEAREST)
    contour,_=cv2.findContours(seg,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(img,contour,-1,source_color,1,cv2.LINE_8)
    h=np.full((65,384,3),28,np.uint8)
    cv2.putText(h,name,(8,24),cv2.FONT_HERSHEY_SIMPLEX,.51,(235,235,235),1)
    cv2.putText(h,head,(8,48),cv2.FONT_HERSHEY_SIMPLEX,.40,(218,218,218),1)
    b=np.full((46,384,3),28,np.uint8)
    cv2.putText(b,footer,(8,28),cv2.FONT_HERSHEY_SIMPLEX,.43,(221,221,221),1)
    return np.vstack((h,img,b))

def show_case(frame,sid,gid,old,trial,rect,lookup,rawmem,status):
    x0,y0,x1,y1=[int(v) for v in rect]
    roi=np.asarray(rawmem[y0:y1,x0:x1],np.uint16)
    assert old.shape==trial.shape==roi.shape==(128,128)
    row=lookup.loc[gid]
    assert int(old.sum())==int(row.source_area_px2)
    len_src=float(row.source_max_feret_px)*PITCH
    area_src=float(old.sum())*PITCH**2
    len_trial=max_feret_centers_px(np.column_stack(np.where(trial)[::-1]))*PITCH if trial.any() else 0.
    area_trial=float(trial.sum())*PITCH**2
    red=(20,35,240)
    amber=(15,185,240)
    raw_panel=card("FRAME"+str(frame)+" "+sid,roi,np.zeros_like(old,bool),
              amber,"RAW / pixel-to-um = 3.2",
              f"Original J5 ID: {gid}")
    src=card("FROZEN J5 / exact source",roi,old,red,
             f"L={len_src:.1f}um  A={area_src:.1f}um2",
             "OFFICIAL detector-equivalent")
    prop=card("K5 OUTER / REVIEW ONLY",roi,trial,amber,
              f"L~{len_trial:.1f}um  A~{area_trial:.1f}um2",
              status[:38])
    return np.hstack([raw_panel,src,prop]),{
        "sample_id":sid,"global_defect_id":gid,
        "old_source_area_px2":int(old.sum()),
        "old_source_length_um":round(len_src,3),
        "old_source_area_um2":round(area_src,3),
        "trial_contour_area_px2":int(trial.sum()),
        "trial_outer_length_um_estimated":round(len_trial,3),
        "trial_outer_area_um2_estimated":round(area_trial,3),
        "trial_status":status,
        "review_only_not_physical_truth":True,
        "official_J5_not_changed":True
    }

def run_frame(frame):
    dir=RUN_DIR/f"frame26_{frame}"
    dst=dir/"K5_provisional_sizes_separate"
    if dst.exists():raise FileExistsError(dst)
    dst.mkdir()
    rawmem=np.memmap(cfg.DATA_ROOT/f"26 ({frame}).raw",mode="r",
                     dtype=">u2",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    reference=pd.read_csv(SOURCE[frame]/"global_defects.csv").set_index("global_defect_id")
    records=[];cards=[]
    if frame==1:
        root=cfg.OUTPUT_ROOT/"case03k_adaptive_group_trial/run_20261012_K5_adaptive_and_J5_group_review_v2"
        audit=pd.read_csv(root/"k5_23_case_adaptive_and_group_audit.csv")
        cases=[]
        for row in audit.to_dict("records"):
            if int(row["adaptive_outer_area_px2"])==0:continue
            p=root/"reversible_masks"/(row["sample_id"]+".npz")
            with np.load(p,allow_pickle=False) as f:
                old=f["original_J5_source"].astype(bool)
                outer=f["raw_adaptive"].astype(bool)
                xyxy=f["global_roi_xyxy"].copy()
            cases.append((row["sample_id"],row["frozen_J5_ID"],old,outer,xyxy,row["display_status"]))
    else:
        root=cfg.OUTPUT_ROOT/"case03k6_frame2_independent/run_20261012_frame26_2_frozen_K5_v1/reversible_mask_audit_top7"
        audit=pd.read_csv(cfg.OUTPUT_ROOT/
              "case03k6_frame2_independent/run_20261012_frame26_2_frozen_K5_v1/all_288_frozen_K5_audit.csv")
        cases=[]
        for row in audit[audit.K5_adaptive_area_px2>0].to_dict("records"):
            p=root/(row["sample_id"]+"_audit_masks.npz")
            with np.load(p,allow_pickle=False) as f:
                old=f["original_J5_source"].astype(bool)
                outer=f["K5_adaptive_envelope"].astype(bool)
                xyxy=f["global_roi_xyxy"].copy()
            cases.append((row["sample_id"],row["frozen_second_frame_J5_ID"],
                          old,outer,xyxy,row["display_status"]))
    for sid,gid,old,outer,xyxy,status in cases:
        img,info=show_case(frame,sid,gid,old,outer,xyxy,reference,rawmem,status)
        save_png(dst/(sid+"_size_3panel.png"),img)
        cards.append((sid,img))
        records.append(info)
    pd.DataFrame(records).to_csv(dst/"K5_provisional_detector_equiv_sizes_review.csv",
                                 encoding="utf-8-sig",index=False)
    for i in range(0,len(cards),5):
        batch=cards[i:i+5]
        p=dst/(f"contact_{i+1:02d}_to_{i+len(batch):02d}.png")
        save_png(p,np.vstack([img for _,img in batch]))
    stat={
      "frame":frame,
      "K5_estimated_outer_proposals":len(cards),
      "detector_pitch_um":PITCH,
      "displays_native_source_pixels_for_original_statistics":True,
      "trial_outer_area_or_length_is_not_official":True,
      "K5_conceptually_unrelated_to_production_regrade":True
    }
    (dst/"summary.json").write_text(json.dumps(stat,ensure_ascii=False,indent=2),encoding="utf-8")
    assert len(list(dst.glob("*_size_3panel.png")))==len(cards)
    for p in dst.glob("*.png"):
        im=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),1)
        assert im is not None
    print("K7_K5_REVIEW_DIMENSIONS_READY",json.dumps(stat,ensure_ascii=False),flush=True)

if __name__=="__main__":
    for frame in (1,2):run_frame(frame)
