"""Case03-K8E: real frame 26(1)/(2) exact outer-UNION display and audits.

Chosen K8D repair objects only (13/19). K8B extra sibling labels are
UNCONFIRMED associations. No J5 official defect IDs, raw, segmentation,
production sizes or grades are modified. Exact pixel union, not area sum.
"""
from pathlib import Path
from dataclasses import asdict
import json,sys
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k8e_group_hypothesis import make_groups,GroupPolicy,union_global
from src.detection.case03i_size_grade import (
    SizeGradeConfig,grade_size,max_feret_centers_px,GRADE_COLORS_BGR)
from scripts.run_case03g_joint_noise_refinement import save_png
K=C.OUTPUT_ROOT/"case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3"
B=C.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
S=C.OUTPUT_ROOT/"case03k8c_outlines_prioritized/run_20261013_K5RAW_contour_expansion_pilot_v1"
OUT=C.OUTPUT_ROOT/"case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1"
POLICY=GroupPolicy();SIZECONF=SizeGradeConfig();STRIDE=8

def load_source_rows(frame):
    file=K/f"frame26_{frame}"/"all_K8D_original_vs_outer_review.csv"
    data=pd.read_csv(file,encoding="utf-8-sig")
    items=[]
    for obj in data.itertuples(index=False):
        file=K/f"frame26_{frame}"/f"band{int(obj.band_id):02d}"/(
            f"F{frame}_B{int(obj.band_id)}_C{int(obj.candidate_label):05d}_K8D_all_masks.npz")
        with np.load(file,allow_pickle=False) as z:
            outer=z["K8D_full_outer"].astype(bool)
            seed=z["original_B_source"].astype(bool)
            box=z["raw_global_roi_xyxy"].astype(int)
            labelgrid=z["B_label_grid_in_roi"].astype(np.int32)
        assert outer.shape==seed.shape==(128,128)
        assert np.all(outer[seed]) and np.all(labelgrid[seed]==obj.candidate_label)
        audit=json.loads(obj.review_evidence_json)
        item={"frame":frame,"band_id":int(obj.band_id),
              "label":int(obj.candidate_label),"box":box.tolist(),
              "mask":outer,"seed":seed,"labelgrid":labelgrid,
              "status":str(obj.status),
              "partial_competitors":audit["group"]["partial_competitors"],
              "embedded_evidence":audit["group"]["member_evidence"],
              "source_npix":int(seed.sum()),
              "original_row":obj}
        items.append(item)
    return items

def frame_data(frame):
    raw=np.memmap(C.DATA_ROOT/f"26 ({frame}).raw",dtype=">u2",
                  mode="r",shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
    px=np.asarray(raw[::STRIDE,::STRIDE],np.float32)
    low,high=np.percentile(px,[1,99.5])
    norm=np.uint8(np.clip((px-low)/max(1.,high-low)*255,0,255))
    bgr=cv2.cvtColor(norm,cv2.COLOR_GRAY2BGR)
    return raw,bgr

def inside_j5_centers(box,mask,old_j5):
    sel=old_j5[old_j5.K8A_region_code_by_original_J5_center==2]
    xs=np.rint(sel.center_x_global).astype(int).to_numpy()
    ys=np.rint(sel.center_y_global).astype(int).to_numpy()
    valid=(xs>=box[0])&(xs<box[2])&(ys>=box[1])&(ys<box[3])
    target=sel.loc[valid].copy()
    if not len(target):return []
    mx=xs[valid]-box[0];my=ys[valid]-box[1]
    overlap=mask[my,mx]
    return [
        {"J5_source_ID":str(o.global_id),"grade":str(o.grade)}
        for o in target.iloc[np.flatnonzero(overlap)].itertuples(index=False)]

def length_grade(mask):
    yy,xx=np.where(mask)
    if not len(xx):return 0.,"NONE"
    feret=float(max_feret_centers_px(np.column_stack([xx,yy])))
    grade,_=grade_size(len(xx),feret,SIZECONF)
    return feret,grade

def draw_on_full(image,box,mask,color,idtext=None):
    region=np.uint8(mask)
    contours,_=cv2.findContours(region,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        pts=cnt.reshape(-1,2).astype(np.int32)
        pts[:,0]=(pts[:,0]+box[0])//STRIDE
        pts[:,1]=(pts[:,1]+box[1])//STRIDE
        cv2.polylines(image,[pts.reshape(-1,1,2)],True,color,1,cv2.LINE_8)
    if idtext:
        xx,yy=box[0]//STRIDE,box[1]//STRIDE
        cv2.putText(image,idtext,(max(1,xx),max(12,yy-5)),
                    cv2.FONT_HERSHEY_SIMPLEX,.37,color,1,cv2.LINE_8)

def header(bg,title,sub):
    top=np.full((95,bg.shape[1],3),25,np.uint8)
    cv2.putText(top,title[:65],(12,31),cv2.FONT_HERSHEY_SIMPLEX,.57,(240,240,240),1)
    cv2.putText(top,sub[:130],(12,62),cv2.FONT_HERSHEY_SIMPLEX,.43,(218,218,218),1)
    return np.vstack((top,bg))

def draw_j5_mediumlarge(bg,original):
    im=bg.copy()
    subset=original[(original.K8A_region_code_by_original_J5_center==2)&
                    original.grade.isin(["MEDIUM","LARGE"])]
    for item in subset.itertuples(index=False):
        a=int(item.display_bbox_x_global)//STRIDE
        b=int(item.display_bbox_y_global)//STRIDE
        c=int(item.display_bbox_xmax_inclusive)//STRIDE
        d=int(item.display_bbox_ymax_inclusive)//STRIDE
        cv2.rectangle(im,(a,b),(max(a,c),max(b,d)),
                      GRADE_COLORS_BGR[item.grade],1,cv2.LINE_8)
    return im,len(subset)

def group_mask_at_original_roi(group,items):
    box=group["box"];h,w=group["mask"].shape
    labels=np.zeros((h,w),np.int32)
    # All K8D crops of SAME work band were derived from one immutable B-mask.
    # A cropped overlapping source label must match pixelwise.
    for item in items:
        if item["label"] not in group["selected_candidate_labels"]:continue
        b=item["box"];sub=item["labelgrid"]
        target=labels[b[1]-box[1]:b[3]-box[1],b[0]-box[0]:b[2]-box[0]]
        both=(target!=0)&(sub!=0)
        if np.any(target[both]!=sub[both]):
            raise AssertionError("Inconsistent B labels in overlapping RAW crop")
        target[target==0]=sub[target==0]
    return labels

def draw_group_card(raw,group,srcitems,groupid,frame):
    box=group["box"]
    x0,y0,x1,y1=box
    crop=np.asarray(raw[y0:y1,x0:x1],np.uint16)
    lo,hi=np.percentile(crop,[1,99.5])
    picture=cv2.cvtColor(np.uint8(np.clip((crop-lo)/max(1,hi-lo)*255,0,255)),
                         cv2.COLOR_GRAY2BGR)
    W=264;H=264
    def thumb(im):return cv2.resize(im,(W,H),interpolation=cv2.INTER_NEAREST)
    union=group["mask"]
    labelgrid=group_mask_at_original_roi(group,srcitems)
    selected=group["selected_candidate_labels"]
    tentative=[x["B_label"] for x in group["embedded_B_source_evidence"]]
    outlines=[("RAW",None,None),
        ("B source components",labelgrid,"seeds"),
        ("K8D outer proposals",union,"outer"),
        ("UNION group contour",union,"union")]
    cards=[]
    for title,mask,mode in outlines:
        img=thumb(picture)
        if mode=="seeds":
            for i,label in enumerate(selected):
                tiny=cv2.resize(np.uint8(labelgrid==label),(W,H),
                                interpolation=cv2.INTER_NEAREST)
                cnt,_=cv2.findContours(tiny,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(img,cnt,-1,(60,60,242) if i==0 else (230,50,210),1)
            for label in tentative:
                tiny=cv2.resize(np.uint8(labelgrid==label),(W,H),
                                interpolation=cv2.INTER_NEAREST)
                cnt,_=cv2.findContours(tiny,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(img,cnt,-1,(40,230,230),1)
        elif mode:
            up=cv2.resize(np.uint8(mask),(W,H),interpolation=cv2.INTER_NEAREST)
            cnt,_=cv2.findContours(up,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(img,cnt,-1,(30,170,245) if "REVIEW" in group["review_status"]
                             else (225,210,25),1)
        top=np.full((82,W,3),25,np.uint8)
        cv2.putText(top,title,(7,23),cv2.FONT_HERSHEY_SIMPLEX,.48,(234,234,234),1)
        short=(f"F{frame} {groupid}" if not mode else
               f"Union={group['exact_group_union_px2']} px2")
        cv2.putText(top,short,(7,50),cv2.FONT_HERSHEY_SIMPLEX,.43,(221,221,221),1)
        cards.append(np.vstack((top,img)))
    note=np.full((57,W*4,3),27,np.uint8)
    src=",".join(map(str,selected))
    emb=",".join(map(str,tentative)) if tentative else "NONE"
    cv2.putText(note,f"SELECTED B labels: {src} | embedded B labels: {emb} (PENDING)",
                (10,20),cv2.FONT_HERSHEY_SIMPLEX,.50,(237,237,237),1)
    cv2.putText(note,group["review_status"]+" | display-only grouping; no official ID merge",
                (10,45),cv2.FONT_HERSHEY_SIMPLEX,.45,(226,226,226),1)
    return np.vstack((np.hstack(cards),note))

def process_one(frame):
    target=OUT/f"frame26_{frame}"
    target.mkdir()
    raw,bg=frame_data(frame)
    items=load_source_rows(frame)
    groups=make_groups(items,POLICY)
    orig=pd.read_csv(B/f"frame26_{frame}/original_J5_object_center_workband_classification.csv")
    old,nold=draw_j5_mediumlarge(bg,orig)
    priority=old.copy();allout=bg.copy();groupreview=bg.copy();singles=bg.copy()
    per=[];display_ids=[];members=[]
    for j,g in enumerate(groups,1):
        gid=f"K8E_F{frame}_B{int(g['band_id'])}_G{j:03d}"
        feret,grade=length_grade(g["mask"])
        duplicates=inside_j5_centers(g["box"],g["mask"],orig)
        assert g["exact_group_union_px2"]==int(g["mask"].sum())
        oldlabels=";".join(map(str,g["selected_candidate_labels"]))
        tentative=";".join(map(str,[a["B_label"] for a in g["embedded_B_source_evidence"]]))
        groupstate=g["review_status"]
        if duplicates:
            groupstate="EXISTING_J5_CENTER_OVERLAP_REVIEW"
        eligible=(grade in ("MEDIUM","LARGE") and
                  groupstate not in ("RAW_SAFETY_UNRESOLVED",
                     "GROUP_CONFLICT_REVIEW","EXISTING_J5_CENTER_OVERLAP_REVIEW"))
        # Colors BGR. Cyan = single stable; orange = linked / unresolved,
        # until a reviewer confirms grouping. These are proposals only.
        color=(230,215,35) if groupstate=="SINGLE_STABLE_REVIEW" else (20,165,245)
        if groupstate in ("RAW_SAFETY_UNRESOLVED",
                          "GROUP_CONFLICT_REVIEW","EXISTING_J5_CENTER_OVERLAP_REVIEW"):
            color=(130,80,210)
        # No drawing small proposals onto main.
        if eligible:
            draw_on_full(priority,g["box"],g["mask"],color,gid.split("_")[-1])
        if g["exact_group_union_px2"]>min(
                 int(x["source_npix"]) for x in items if x["label"] in g["selected_candidate_labels"]
                 and x["band_id"]==g["band_id"]):
            draw_on_full(allout,g["box"],g["mask"],color,gid.split("_")[-1])
            if groupstate=="SINGLE_STABLE_REVIEW":
                draw_on_full(singles,g["box"],g["mask"],color)
            else:
                draw_on_full(groupreview,g["box"],g["mask"],color,gid.split("_")[-1])
        source_items=[x for x in items if x["band_id"]==g["band_id"]]
        fdir=target/"group_detail"
        fdir.mkdir(exist_ok=True)
        cardname=gid+"_RAW_sources_exact_union.png"
        save_png(fdir/cardname,draw_group_card(raw,g,source_items,gid,frame))
        mat=fdir/(gid+"_EXACT_GROUP_MASK.npz")
        np.savez_compressed(mat,
            review_outer=np.uint8(g["mask"]),
            roi_xyxy=np.asarray(g["box"],np.int32),
            source_component_labels=np.asarray(g["selected_candidate_labels"],np.int32),
            embedded_B_candidate_labels=np.asarray([v["B_label"] for v in g["embedded_B_source_evidence"]],np.int32),
            source_B_label_grid=group_mask_at_original_roi(g,source_items))
        record={
            "group_id":gid,"frame":frame,"band_id":g["band_id"],
            "selected_B_labels":oldlabels,"embedded_B_labels_TO_REVIEW":tentative,
            "K8D_selected_source_mask_count":len(g["selected_candidate_labels"]),
            "review_status":groupstate,"source_state_before_J5_check":g["review_status"],
            "original_K8D_masks_sum_px2":g["original_K8D_masks_sum_px2"],
            "unique_outer_union_px2":g["exact_group_union_px2"],
            "duplicate_pixels_removed_from_area_sum":g["deduplicated_pixels"],
            "union_length_detector_um_PROVISIONAL":round(feret*float(C.PIXEL_SIZE_UM),3),
            "union_area_detector_um2_PROVISIONAL":round(g["exact_group_union_px2"]*float(C.PIXEL_SIZE_UM)**2,3),
            "trial_size_grade":grade,"J5_centers_inside_outer":len(duplicates),
            "J5_center_overlap_details":json.dumps(duplicates,ensure_ascii=False),
            "provisional_main_MEDLARGE_eligible":eligible,
            "group_pairwise_geometry_evidence":json.dumps(g["pair_links"],ensure_ascii=False),
            "embedded_source_membership_evidence":json.dumps(g["embedded_B_source_evidence"],ensure_ascii=False),
            "full_RAW_roi_xyxy":json.dumps(g["box"]),
            "human_confirm_same_spot":"","human_confirm_outer_complete":"",
            "can_be_used_as_certified_defect_area":False,
            "official_source_B_J5_IDs_merged":False,
            "raw_J5_K5_K8B_K8C_K8D_input_modified":False,
            "detail_image":str(fdir/cardname),
            "exact_mask":str(mat)}
        per.append(record)
        for lab in g["selected_candidate_labels"]:
            members.append({"group_id":gid,"source_B_label":lab,
                 "role":"K8D_SELECTED_PROPOSAL","confirmed_same_defect":False})
        for lab in g["embedded_B_source_evidence"]:
            members.append({"group_id":gid,"source_B_label":lab["B_label"],
                 "role":"OTHER_B_SEED_EMBEDDED_PENDING_REVIEW",
                 "coverage_by_source_outer":lab["coverage"],
                 "confirmed_same_defect":False})
    pd.DataFrame(per).to_csv(target/"K8E_unique_group_union_measurements.csv",
                             index=False,encoding="utf-8-sig")
    pd.DataFrame(members).to_csv(target/"K8E_source_member_traceability.csv",
                                 index=False,encoding="utf-8-sig")
    pix={}
    layout=[
      ("01_ORIGINAL_J5_MED_LARGE_ONLY.png",old,
       "Only frozen original J5 WORK MED/LARGE; no new source areas"),
      ("02_PRIORITY_J5_MEDLARGE_plus_K8E_GROUPED_REVIEW.png",priority,
       "J5 MED/LARGE + K8E stable cyan / multi-component orange; NOT official merged defects"),
      ("03_GROUPED_RAW_OUTERS_NO_DUPLICATES.png",allout,
       "K8E original pixel-union contours; no double count; colors indicate review state"),
      ("04_MULTI_COMPONENT_ASSOCIATION_REVIEW.png",groupreview,
       "Group/overlap/uncertain RAW envelopes, colors = requires manual identity review"),
      ("05_SINGLE_STABLE_OUTERS_REFERENCE.png",singles,
       "Stable single RAW proposals reference, not a calibrated size measurement")]
    for name,im,sub in layout:
        pic=header(im,f"F26({frame}) K8E: {name[3:-4]}",sub)
        save_png(target/name,pic)
        pix[name]=int(pic.shape[0])*int(pic.shape[1])
    # Show smalls separately: keep earlier K8C view unchanged, re-save without
    # applying any regrade or hiding source pixels from original archive.
    previous=S/f"frame26_{frame}"/"05_SMALL_original_J5_and_K8C_reference.png"
    if previous.exists():
        small=cv2.imdecode(np.frombuffer(previous.read_bytes(),np.uint8),
                           cv2.IMREAD_COLOR)
        save_png(target/"06_SMALL_SOURCE_REFERENCE_UNCHANGED.png",small)
    totalres={
      "frame":frame,"K8D_selected_proposals":len(items),"K8E_display_groups":len(per),
      "grouped_multi_selected":sum(x["K8D_selected_source_mask_count"]>1 for x in per),
      "grouped_single_embedded":sum(
          x["K8D_selected_source_mask_count"]==1 and bool(x["embedded_B_labels_TO_REVIEW"])
          for x in per),
      "original_J5_frozen_work_MEDLARGE_count":nold,
      "mediumlarge_proposals_on_priority_main":sum(x["provisional_main_MEDLARGE_eligible"] for x in per),
      "exact_group_union_total_pixel_area_not_physical_truth":sum(
         x["unique_outer_union_px2"] for x in per),
      "previous_K8D_object_mask_areas_sum":sum(x["original_K8D_masks_sum_px2"] for x in per),
      "per_group_repeated_pixels_removed":sum(x["duplicate_pixels_removed_from_area_sum"] for x in per),
      "all_original_B_J5_and_prior_K8D_data_unmodified":True,
      "all_associations_pending_human_confirmation":True}
    (target/"summary.json").write_text(json.dumps(totalres,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8E_FRAME_DONE",json.dumps(totalres,ensure_ascii=False),flush=True)
    return totalres

def run():
    if OUT.exists():raise FileExistsError("Run exists: preserve traceability")
    OUT.mkdir(parents=True)
    summaries=[process_one(i) for i in (1,2)]
    (OUT/"summary.json").write_text(json.dumps({"stage":"CASE03_K8E_GROUPED_REVIEW",
         "source_K8D":str(K),"policy":asdict(POLICY),"frames":summaries,
         "all_results_are_provisional":True},ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":run()
