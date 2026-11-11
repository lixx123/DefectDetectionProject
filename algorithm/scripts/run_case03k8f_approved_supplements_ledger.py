"""Case03-K8F: visually confirmed G006/G009 added to independent WORK ledger.

User approved 2nd frame G006 (626+658) and G009 (1148+1161+1186)
as darkspots with correct outer contours. ONLY these two groups receive
manual-confirmed status. Frozen J5 objects retain their source IDs, pixel
area, source grades, and unknown true-defect status.
K8E other groups stay pending. Source J5 is never overwritten.
Detector 3.2 um pitch gives IMAGE PLANE EQUIVALENT, not object plane.
"""
from pathlib import Path
import json,hashlib,sys
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03i_size_grade import (
    SizeGradeConfig,max_feret_centers_px,grade_size,GRADE_COLORS_BGR)
from scripts.run_case03g_joint_noise_refinement import save_png

E=C.OUTPUT_ROOT/"case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1"
B=C.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
K8C=C.OUTPUT_ROOT/"case03k8c_outlines_prioritized/run_20261013_K5RAW_contour_expansion_pilot_v1"
OUT=C.OUTPUT_ROOT/"case03k8f_confirmed_group_register/run_20261014_F26_2_two_user_approved_G006_G009_v2"
APPROVALS={
    "K8E_F2_B2_G006":{"expected_primary":626,"expected_member_ids":{626,658},
                    "expected_selected":{626},"expected_embedded":{658},
                    "expected_area":348},
    "K8E_F2_B2_G009":{"expected_primary":1161,"expected_member_ids":{1148,1161,1186},
                    "expected_selected":{1148,1161},"expected_embedded":{1186},
                    "expected_area":370}
}
PITCH=3.2
GRADE=SizeGradeConfig()
SCALE=8

def loadpng(p:Path):
    a=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),
                   cv2.IMREAD_UNCHANGED)
    if a is None:raise IOError(p)
    return a

def bg(frame:int):
    raw=np.memmap(C.DATA_ROOT/f"26 ({frame}).raw",mode="r",dtype=">u2",
                  shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
    part=np.asarray(raw[::SCALE,::SCALE],np.float32)
    lo,hi=np.percentile(part,[1,99.5])
    bgr=cv2.cvtColor(np.uint8(np.clip((part-lo)/max(1,hi-lo)*255,0,255)),
                     cv2.COLOR_GRAY2BGR)
    return bgr

def header(im,headline,description):
    top=np.full((89,im.shape[1],3),26,np.uint8)
    cv2.putText(top,headline[:72],(9,29),cv2.FONT_HERSHEY_SIMPLEX,.56,(240,240,240),1)
    cv2.putText(top,description[:120],(9,62),cv2.FONT_HERSHEY_SIMPLEX,.41,(217,217,217),1)
    return np.vstack((top,im))

def add_J5_large(base,orig):
    out=base.copy()
    objs=orig[orig.grade.isin(["MEDIUM","LARGE"])]
    for s in objs.itertuples(index=False):
        a=int(s.display_bbox_x_global)//SCALE
        b=int(s.display_bbox_y_global)//SCALE
        cc=int(s.display_bbox_xmax_inclusive)//SCALE
        dd=int(s.display_bbox_ymax_inclusive)//SCALE
        cv2.rectangle(out,(a,b),(max(a,cc),max(b,dd)),
                      GRADE_COLORS_BGR[s.grade],1,cv2.LINE_8)
    return out,len(objs)

def drawmask(im,box,mask,color,tag):
    contours,_=cv2.findContours(np.uint8(mask),cv2.RETR_EXTERNAL,
                                cv2.CHAIN_APPROX_SIMPLE)
    for outline in contours:
        pos=outline.reshape(-1,2).astype(np.int32)
        pos[:,0]=(pos[:,0]+box[0])//SCALE
        pos[:,1]=(pos[:,1]+box[1])//SCALE
        cv2.polylines(im,[pos.reshape(-1,1,2)],True,color,1,cv2.LINE_8)
    ys,xs=np.where(mask)
    if len(xs):
        tx=max(5,int((box[0]+np.min(xs))/SCALE))
        ty=max(12,int((box[1]+np.min(ys))/SCALE)-4)
        cv2.putText(im,tag,(tx,ty),cv2.FONT_HERSHEY_SIMPLEX,
                    .38,color,1,cv2.LINE_8)

def read_geometry(frame,id):
    path=E/f"frame26_{frame}"/"group_detail"/(id+"_EXACT_GROUP_MASK.npz")
    with np.load(path,allow_pickle=False) as z:
        box=tuple(map(int,z["roi_xyxy"]))
        m=z["review_outer"].astype(bool)
        selected=set(map(int,z["source_component_labels"]))
        embedded=set(map(int,z["embedded_B_candidate_labels"]))
        labelgrid=z["source_B_label_grid"].astype(np.int32)
    assert m.shape==(box[3]-box[1],box[2]-box[0])
    yy,xx=np.where(m)
    if len(xx)==0:raise ValueError("Empty manually confirmed mask")
    feret=max_feret_centers_px(np.column_stack([xx,yy]))
    grade,reason=grade_size(len(xx),feret,GRADE)
    result={
        "source_K8E_id":id,
        "box":box,"mask":m,
        "source_selected":selected,"source_embedded":embedded,
        "bbox_global_xyxy_exclusive":[box[0]+int(xx.min()),box[1]+int(yy.min()),
                     box[0]+int(xx.max())+1,box[1]+int(yy.max())+1],
        "center_global_x":round(box[0]+float(xx.mean()),4),
        "center_global_y":round(box[1]+float(yy.mean()),4),
        "area_px2":int(len(xx)),"length_px":round(float(feret),4),
        "area_detector_um2":round(len(xx)*PITCH**2,3),
        "length_detector_um":round(float(feret)*PITCH,3),
        "grade":grade,"grade_reason":reason,
        "raw_source_labels_inside_outer":sorted(set(map(int,np.unique(labelgrid[m])))-{0}),
        "npz_path":str(path)
    }
    return result

def frozen_J5_work(frame):
    raw=pd.read_csv(B/f"frame26_{frame}"/
                    "original_J5_object_center_workband_classification.csv",
                    encoding="utf-8-sig")
    old=raw[raw.K8A_region_code_by_original_J5_center==2].copy()
    assert len(old)==(683 if frame==1 else 398)
    assert old.global_defect_id.is_unique
    return raw,old

def baseline_record(frame,s):
    return {
      "frame":frame,"source":"FROZEN_J5_WORK",
      "source_J5_global_defect_id":s.global_defect_id,
      "supplement_K8E_group_id":"",
      "source_B_connected_components":"",
      "source_B_embedded_components":"",
      "position_global_x":round(float(s.center_x_global),4),
      "position_global_y":round(float(s.center_y_global),4),
      "bbox_x0_global":int(s.source_bbox_x_global),
      "bbox_y0_global":int(s.source_bbox_y_global),
      "bbox_x1_exclusive_global":int(s.source_bbox_x_global+s.source_bbox_width_px),
      "bbox_y1_exclusive_global":int(s.source_bbox_y_global+s.source_bbox_height_px),
      "area_detector_px2":int(s.source_area_px2),
      "max_length_detector_px":round(float(s.source_max_feret_px),4),
      "area_detector_image_um2":round(float(s.source_area_px2)*PITCH**2,3),
      "max_length_detector_image_um":round(float(s.source_max_feret_px)*PITCH,3),
      "size_grade":str(s.grade),
      "original_J5_grade_unchanged":True,
      "visual_defect_confirmed_by_user":False,
      "review_state":"EXISTING_J5_CANDIDATE_UNREVIEWED",
      "physical_object_plane_size_calibrated":False,
      "regulatory_acceptance_decision":"",
      "source_masks_untouched":True
    }

def newly_approved_record(frame,item):
    box=item["bbox_global_xyxy_exclusive"]
    return {
      "frame":frame,"source":"K8F_USER_APPROVED_K8E_OUTER",
      "source_J5_global_defect_id":"",
      "supplement_K8E_group_id":item["source_K8E_id"],
      "source_B_connected_components":";".join(map(str,sorted(item["source_selected"]))),
      "source_B_embedded_components":";".join(map(str,sorted(item["source_embedded"]))),
      "position_global_x":item["center_global_x"],
      "position_global_y":item["center_global_y"],
      "bbox_x0_global":box[0],"bbox_y0_global":box[1],
      "bbox_x1_exclusive_global":box[2],"bbox_y1_exclusive_global":box[3],
      "area_detector_px2":item["area_px2"],
      "max_length_detector_px":item["length_px"],
      "area_detector_image_um2":item["area_detector_um2"],
      "max_length_detector_image_um":round(float(item["length_detector_um"]),3),
      "size_grade":item["grade"],"original_J5_grade_unchanged":True,
      "visual_defect_confirmed_by_user":True,
      "review_state":"USER_CONFIRMED_DARKSPOT_AND_OUTER_GROUP_20261014",
      "physical_object_plane_size_calibrated":False,
      "regulatory_acceptance_decision":"",
      "source_masks_untouched":True
    }

def establish(frame):
    target=OUT/f"frame26_{frame}"
    target.mkdir()
    raw,old=frozen_J5_work(frame)
    approved=[]
    remaining=pd.read_csv(E/f"frame26_{frame}"/
                          "K8E_unique_group_union_measurements.csv",
                          encoding="utf-8-sig")
    if frame==2:
        if set(APPROVALS)-set(remaining.group_id):
            raise ValueError("Requested approved groups absent")
        for name,spec in APPROVALS.items():
            match=remaining[remaining.group_id==name]
            assert len(match)==1
            row=match.iloc[0]
            item=read_geometry(frame,name)
            assert int(row.unique_outer_union_px2)==item["area_px2"]==spec["expected_area"]
            assert item["source_selected"]==spec["expected_selected"]
            assert item["source_embedded"]==spec["expected_embedded"]
            assert (item["source_selected"]|item["source_embedded"])==spec["expected_member_ids"]
            assert set(item["raw_source_labels_inside_outer"]).issuperset(spec["expected_member_ids"])
            assert item["grade"]=="LARGE"
            assert str(row.review_status) in ("EMBEDDED_B_SOURCE_REVIEW",
                "MUTUAL_CONTOUR_NEAR_IDENTICAL_REVIEW")
            box=item["bbox_global_xyxy_exclusive"]
            # Conservative check: *any* original J5 display BBox intersection,
            # not just center-based geometric overlap.
            nearby=raw[(
                (raw.display_bbox_x_global<box[2])&
                (raw.display_bbox_xmax_inclusive>=box[0])&
                (raw.display_bbox_y_global<box[3])&
                (raw.display_bbox_ymax_inclusive>=box[1]))]
            item["possible_original_J5_bbox_overlap_count"]=len(nearby)
            if len(nearby):raise RuntimeError(
                "Unresolved J5 existing candidate bbox collision prevents new-record confirmation")
            approved.append(item)
    elif frame==1:
        assert not approved
    else:raise ValueError(frame)
    # register includes ALL already-existing J5 candidate IDs within WORK core,
    # which remain candidates, + exactly human confirmed darkspot supplements.
    records=[baseline_record(frame,x) for x in old.itertuples(index=False)]
    records.extend(newly_approved_record(frame,x) for x in approved)
    # stable index order by original centroid row/column; no ID collision
    records.sort(key=lambda z:(z["position_global_y"],z["position_global_x"],
                               z["source"],z["source_J5_global_defect_id"],
                               z["supplement_K8E_group_id"]))
    for idx,obj in enumerate(records,1):
        obj["work_candidate_review_ID"]=f"WORK_F26_{frame}_{idx:06d}"
        obj["official_original_J5_global_ID_preserved"]=True
        obj["is_certified_production_defect_register"]=False
    csv=target/"workband_unified_candidate_review_register.csv"
    pd.DataFrame(records).to_csv(csv,index=False,encoding="utf-8-sig")
    selected=set(APPROVALS) if frame==2 else set()
    pending=remaining[~remaining.group_id.isin(selected)].copy()
    pending["manual_identity_and_full_outer_approved"]=False
    pending["not_added_to_unified_workband_register"]=True
    pending.to_csv(target/"other_K8E_groups_pending_manual_review.csv",
                   index=False,encoding="utf-8-sig")
    source_trace=pd.read_csv(E/f"frame26_{frame}"/
                     "K8E_source_member_traceability.csv",encoding="utf-8-sig")
    source_trace["confirmed_by_user_as_one_darkspot"]=source_trace.group_id.isin(selected)
    source_trace["source_physical_ID_deleted_or_changed"]=False
    source_trace.to_csv(target/"all_K8E_source_B_members_with_exact_user_approval.csv",
                        encoding="utf-8-sig",index=False)
    background=bg(frame)
    large,nold=add_J5_large(background,old)
    consolidated=large.copy()
    approvedonly=background.copy()
    palette=[(235,200,45),(240,150,60)]
    for i,item in enumerate(approved):
        maskfile=target/(item["source_K8E_id"]+"_outer_mask_128p.png")
        mask_bytes=cv2.imencode('.png',item['mask'].astype(np.uint8)*255)[1].tobytes()
        maskfile.write_bytes(mask_bytes)
        check=loadpng(maskfile)
        assert np.array_equal(check>0,item['mask'])
        tag=item["source_K8E_id"].split("_")[-1]
        drawmask(consolidated,item["box"],item["mask"],palette[i],tag)
        drawmask(approvedonly,item["box"],item["mask"],palette[i],tag)
    # Keep small separately, no new 1/2px hypothesis added
    smallsrc=K8C/f"frame26_{frame}"/"05_SMALL_original_J5_and_K8C_reference.png"
    if smallsrc.exists():
        im=loadpng(smallsrc)
        save_png(target/"04_SMALL_existing_and_K8C_reference.png",im)
    for name,im,title,desc in [
        ("01_J5_existing_MEDLARGE_baseline.png",large,
         f"F26({frame}) FROZEN J5 MED/LARGE",
         f"Existing J5 WORK medium/large candidates {nold}; no new confirmed objects."),
        ("02_MEDLARGE_plus_two_USER_CONFIRMED_DARKSPOTS.png",consolidated,
         f"F26({frame}) WORK J5 + CONFIRMED SUPPLEMENT",
         f"Old J5 MED/LARGE {nold}, visually confirmed new outer groups {len(approved)}; no production verdict"),
        ("03_ONLY_user_confirmed_darkspot_outlines.png",approvedonly,
         f"F26({frame}) USER CONFIRMED DARKSPOT OUTERS",
         f"Number visually confirmed by user = {len(approved)}; 3.2 um = detector pixel pitch only")
        ]:
        save_png(target/name,header(im,title,desc))
    summ={
      "frame":frame,
      "original_J5_WORK_unverified_candidate_count":len(old),
      "original_J5_WORK_MEDLARGE":nold,
      "human_visual_approved_new_darkspots":len(approved),
      "approved_K8E_ids":[x["source_K8E_id"] for x in approved],
      "newly_approved_outer_areas_px2":{x["source_K8E_id"]:x["area_px2"] for x in approved},
      "newly_approved_outer_total_px2":sum(x["area_px2"] for x in approved),
      "all_400_or_683_records_are_not_certified_physical_defects":True,
      "unified_review_candidate_count":len(records),
      "other_unapproved_K8E_group_count":len(pending),
      "newly_approved_J5_bbox_collision_count":sum(
             x["possible_original_J5_bbox_overlap_count"] for x in approved),
      "unified_record_names_are_review_indices_not_original_J5_IDs":True,
      "original_J5_ids_and_sizes_unchanged":True,
      "object_plane_magnification_calibration_present":False,
      "true_defect_count_or_qualification_not_calculated":True}
    (target/"summary.json").write_text(json.dumps(summ,ensure_ascii=False,indent=2),
                                       encoding="utf-8")
    print("K8F_FRAME_REGISTER_COMPLETE",json.dumps(summ,ensure_ascii=False),flush=True)
    return summ

def main():
    if OUT.exists():raise FileExistsError(OUT)
    OUT.mkdir(parents=True)
    frames=[establish(1),establish(2)]
    (OUT/"summary.json").write_text(json.dumps({
      "stage":"CASE03_K8F_TWO_USER_CONFIRMED_SUPPLEMENT_UNIFIED_WORK_REGISTER",
      "user_approved_groups_on_frame2_only":list(APPROVALS),
      "all_other_K8E_review_only":True,
      "do_not_replace_production_original_J5_file":True,
      "source_K8E_readonly":str(E),"source_J5_readonly":str(B),
      "frames":frames},ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":main()
