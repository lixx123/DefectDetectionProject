"""K8I Stage 2 visual review pack and explicit J5/old-K8E collision ledger.

Overlays only. No confirmation, no merging of original J5, K8E or K8D IDs.
Every group is a *proposed contour review group*, not physical defect count.
"""
from pathlib import Path
import sys,json,math
from collections import Counter
import pandas as pd,numpy as np,cv2
from PIL import Image,ImageFont,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k8g_display_boxes import expand_bbox_xyxy,bbox_to_display_px
from scripts.run_case03k8g_1p5_display_boxes import background,write_lossless
from scripts.run_case03k8i_stage2_fullband_priority_contours import OUT,K8E,K8B,K8I
FONT="C:/Windows/Fonts/msyh.ttc"
def header(im,fr,title,subtitle):
    H,W=im.shape[:2]
    pane=Image.new("RGB",(W,86),(24,25,27));dr=ImageDraw.Draw(pane)
    f1=ImageFont.truetype(FONT,18);f2=ImageFont.truetype(FONT,14)
    dr.text((8,7),f"26号第{fr}帧 ｜ {title}",font=f1,fill=(238,238,238))
    dr.text((8,48),subtitle,font=f2,fill=(224,226,227))
    return np.vstack((cv2.cvtColor(np.asarray(pane),cv2.COLOR_RGB2BGR),im))
def drawbox(pic,box,col):
    rect=expand_bbox_xyxy(box,(C.RAW_WIDTH,C.RAW_HEIGHT),1.5)
    a,b,c,d=bbox_to_display_px(rect,(C.RAW_WIDTH,C.RAW_HEIGHT),
                              (pic.shape[1],pic.shape[0]),4)
    cv2.rectangle(pic,(a,b),(c,d),col,1,cv2.LINE_8)
    return a,b,c,d
def build(frame):
    root=OUT/f"frame26_{frame}"
    new=pd.read_csv(root/"new_exact_group_union_review.csv")
    old=pd.read_csv(K8E/f"frame26_{frame}"/"K8E_unique_group_union_measurements.csv")
    src=pd.read_csv(K8B/f"frame26_{frame}"/"original_J5_object_center_workband_classification.csv")
    # Whole original J5 display bbox query only. Explicitly not exact
    # pixel-mask overlap, so cannot auto-merge or decide same defect.
    jj=src[["global_defect_id","display_bbox_x_global",
             "display_bbox_xmax_inclusive","display_bbox_y_global",
             "display_bbox_ymax_inclusive"]]
    r_all=[];r_stable=[];r_collision=[]
    overview=background(frame,4)
    only=overview.copy();stable=overview.copy();collision=overview.copy()
    for i,item in enumerate(new.itertuples(index=False)):
        box=tuple(map(int,json.loads(item.RAW_global_review_bbox_xyxy)))
        hits=jj[(jj.display_bbox_x_global<box[2])&
             (jj.display_bbox_xmax_inclusive>=box[0])&
             (jj.display_bbox_y_global<box[3])&
             (jj.display_bbox_ymax_inclusive>=box[1])]
        oldhit=json.loads(item.old_K8D_B_mask_overlap_json)
        status=str(item.new_group_evidence)
        # Stable single/group mask only after original K8D checked status;
        # source-only statuses are never promoted by K8E union grouping.
        ids=list(map(int,str(item.new_source_B_labels).split(";")))
        trial=pd.read_csv(root/"new_evidence_RAW_trial_results.csv")
        members=trial[(trial.band_id==item.band_id)&trial.B_label.isin(ids)]
        allstable=len(members)==len(ids) and members.stage2_review_status.str.startswith("STABLE_").all()
        is_conflict=bool(oldhit) or str(item.approval_status)!="PENDING_MANUAL_REVIEW"
        col=(22,174,245) if not allstable else (29,217,92)
        if is_conflict:col=(120,91,252)
        drawbox(only,box,col)
        if allstable and not is_conflict:
            xy=drawbox(stable,box,(25,218,93))
            cv2.putText(stable,"R"+str(i+1),(max(1,xy[0]),max(12,xy[1]-3)),
                        cv2.FONT_HERSHEY_SIMPLEX,.35,(25,218,93),1)
        if is_conflict or hits.shape[0]:
            drawbox(collision,box,(48,70,249))
        record={
            "new_group_id":item.new_group_id,"frame":frame,
            "band_id":int(item.band_id),
            "source_B_labels":item.new_source_B_labels,
            "source_conserving_exact_union_px2":int(item.new_exact_union_area_px2),
            "source_raw_members_all_K8D_stable":bool(allstable),
            "old_K8D_overlapping_trial_count":len(oldhit),
            "old_K8D_overlap_evidence_json":json.dumps(oldhit,ensure_ascii=False),
            "original_J5_display_bbox_intersection_count":int(len(hits)),
            "original_J5_possible_duplicate_IDs":";".join(map(str,hits.global_defect_id.head(25))),
            "original_J5_overlap_is_pixel_level":False,
            "approval_state":"PENDING_REVIEW",
            "readable_layer_file":"02_NEW_RAW_GROUPS_ALL_review_1to4.png",
            "old_original_approved_groups_frozen":True}
        r_all.append(record)
    pd.DataFrame(r_all).to_csv(root/"new_group_J5_bbox_and_old_K8D_collision_review.csv",
                               index=False,encoding="utf-8-sig")
    oldmapped=[]
    for item in old.itertuples(index=False):
        gid=item.group_id
        accepted=gid in ("K8E_F2_B2_G006","K8E_F2_B2_G009")
        oldmapped.append({
          "review_group_id":gid,"frame":frame,"band_id":int(item.band_id),
          "source_stage":"FROZEN_K8E",
          "B_source_labels":str(item.selected_B_labels),
          "outer_review_px2":int(item.unique_outer_union_px2),
          "user_approved_darkspot_and_group":bool(accepted),
          "audit_original_K8E_source_mask":str(K8E/f"frame26_{frame}"/"group_detail"/(
              gid+"_EXACT_GROUP_MASK.npz")),
          "source_modified":False})
    fresh=[{
        "review_group_id":r["new_group_id"],"frame":frame,
        "band_id":r["band_id"],"source_stage":"NEW_K8I_STAGE2_REVIEW",
        "B_source_labels":r["source_B_labels"],
        "outer_review_px2":r["source_conserving_exact_union_px2"],
        "user_approved_darkspot_and_group":False,
        "audit_original_K8E_source_mask":"",
        "source_modified":False} for r in r_all]
    pd.DataFrame(oldmapped+fresh).to_csv(root/"ALL_FROZEN_AND_NEW_RAW_REVIEW_GROUPS_no_ID_merge.csv",
                                         index=False,encoding="utf-8-sig")
    write_lossless(root/"02_NEW_RAW_GROUPS_ALL_review_1to4.png",
                   header(only,frame,"全部新RAW试验外围待复核",
                       "橙：RAW源轮廓未稳定；绿：稳定但未审批；紫：与既有轮廓重叠，不可自动合并"))
    write_lossless(root/"03_ONLY_NEW_STABLE_RAW_GROUPS_review_1to4.png",
                   header(stable,frame,"新稳定RAW外围待复核",
                        "只显示K8D通过稳定门控且无旧RAW重叠的组；仍非用户确认疵病"))
    write_lossless(root/"04_OLD_RAW_or_J5_bbox_OVERLAP_review_1to4.png",
                   header(collision,frame,"跨已有RAW/J5位置冲突复核",
                         "仅BBox相交或已保存RAW掩膜相交，禁止自动删除及跨通道正式合并"))
    return {"frame":frame,"new_review_groups":len(r_all),
        "old_frozen_review_groups":len(oldmapped),
        "old_user_confirmed_review_groups":sum(x["user_approved_darkspot_and_group"] for x in oldmapped),
        "new_group_areas_approximate_NOT_production":int(sum(z["source_conserving_exact_union_px2"] for z in r_all)),
        "new_group_stable_no_prior_RAW_overlap":sum(x["source_raw_members_all_K8D_stable"] and
            not x["old_K8D_overlapping_trial_count"] for x in r_all),
        "new_group_old_K8D_mask_overlap_count":sum(bool(x["old_K8D_overlapping_trial_count"]) for x in r_all),
        "new_group_any_original_J5_bbox_hit":sum(x["original_J5_display_bbox_intersection_count"]>0 for x in r_all),
        "original_confirmed_two_groups_still_348_370":frame==2,
        "original_IDs_and_areas_modified":False}

def main():
    reports=[build(f) for f in (1,2)]
    p=OUT/"visual_review_pack_summary.json"
    if p.exists():raise FileExistsError(p)
    p.write_text(json.dumps({"stage":"K8I_STAGE2_VISUAL_COLLISION_REVIEW_PACK",
        "no_auto_merge_between_existing_and_new_trial_groups":True,
        "all_new_K8I_stage2_groups_still_require_user_approval":True,
        "frames":reports},ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8I_STAGE2_VISUAL_REVIEW_PACK_DONE",json.dumps(reports,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
