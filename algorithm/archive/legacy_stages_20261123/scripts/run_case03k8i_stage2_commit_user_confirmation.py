"""K8I-2 human-reviewed two separate dark spots in F26(1), 2026-10-17.

The user has explicitly confirmed both identities and complete contours:
- Band02 K8B labels 1787+1902: one dark spot, exact 398px2 RAW envelope;
  source canonical frozen K8E F1 B02 G004, not newly recomputed 1787.
- Band04 labels 2424+2444+2504: one dark spot, exact OR union 297px2;
  source canonical NEW K8I2 F1 B04 G0096.
Never modify any prior K8B/J5/K8D/E/F/G/H/I1/I2 files. This script
records review decisions in a distinct ledger, not production J5 IDs.
"""
from pathlib import Path
import sys,json,hashlib,math,shutil
import pandas as pd,numpy as np,cv2
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03i_size_grade import max_feret_centers_px,grade_size,SizeGradeConfig
from src.detection.case03k8g_display_boxes import expand_bbox_xyxy,bbox_to_display_px
from scripts.run_case03k8g_1p5_display_boxes import background,write_lossless
K8E=C.OUTPUT_ROOT/"case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1"
K8I2=C.OUTPUT_ROOT/"case03k8i_stage2_RAW_review_and_association/run_20261017_twoframes_priority_evidence_v1"
K8I1=C.OUTPUT_ROOT/"case03k8i_full_frame_lineage/run_20261015_sample26_2frames_fullcandidate_lineage_v1"
K8B=C.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
OUT=C.OUTPUT_ROOT/"case03k8i_stage2_user_confirmed_reviews/run_20261017_F1_B02_B04_two_darkspots_v1"
PITCH=float(C.PIXEL_SIZE_UM)
FONT="C:/Windows/Fonts/msyh.ttc"
CASES=[
    {"band":2,"stage":"K8E_FROZEN_CANONICAL",
     "review_id":"K8I2_USER_F1_B02_DARKSPOT_001",
     "old_group":"K8E_F1_B2_G004","new_group":"K8I2_F1_B02_G0021",
     "members":[1787,1902],"area":398,"darkspot_count":1},
    {"band":4,"stage":"K8I2_EXACT_NEW_UNION_CANONICAL",
     "review_id":"K8I2_USER_F1_B04_DARKSPOT_001",
     "old_group":"","new_group":"K8I2_F1_B04_G0096",
     "members":[2424,2444,2504],"area":297,"darkspot_count":1},
]
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for blk in iter(lambda:f.read(1048576),b""):h.update(blk)
    return h.hexdigest()
def open_group(p,maskname,rectname):
    with np.load(p,allow_pickle=False) as z:
        mask=z[maskname].astype(bool)
        box=tuple(map(int,z[rectname]))
    assert mask.ndim==2 and len(box)==4
    assert mask.shape==(box[3]-box[1],box[2]-box[0])
    return {"mask":mask,"box":box,"file":p}
def align_mask(info,global_box):
    x0,y0,x1,y1=info["box"]
    X0,Y0,X1,Y1=global_box
    out=np.zeros((Y1-Y0,X1-X0),bool)
    l=max(x0,X0);r=min(x1,X1);top=max(y0,Y0);bottom=min(y1,Y1)
    if l<r and top<bottom:
        out[top-Y0:bottom-Y0,l-X0:r-X0]=info["mask"][
             top-y0:bottom-y0,l-x0:r-x0]
    return out

def source_proof():
    old=pd.read_csv(K8E/"frame26_1/K8E_unique_group_union_measurements.csv",
                    encoding="utf-8-sig")
    new=pd.read_csv(K8I2/"frame26_1/new_exact_group_union_review.csv",
                    encoding="utf-8-sig")
    approvals=[]
    members=[]
    new_masks=[]
    provenance=[]
    j5=pd.read_csv(K8B/"frame26_1/original_J5_object_center_workband_classification.csv",
                   encoding="utf-8-sig")
    for c in CASES:
        cnew=new[new.new_group_id==c["new_group"]]
        assert len(cnew)==1 and int(cnew.iloc[0].band_id)==c["band"]
        cr=cnew.iloc[0]
        if c["band"]==2:
            assert str(cr.new_source_B_labels)=="1787"
            assert int(cr.new_exact_union_area_px2)==398
            assert str(cr.old_K8D_B_mask_overlap_json)!="[]"
            pair=json.loads(cr.old_K8D_B_mask_overlap_json)
            match=[z for z in pair if int(z["old_B_label"])==1902]
            assert len(match)==1 and match[0]["intersection_px2"]==398 and match[0]["iou"]==1.0
            oldrow=old[old.group_id==c["old_group"]]
            assert len(oldrow)==1 and int(oldrow.iloc[0].unique_outer_union_px2)==398
            assert str(oldrow.iloc[0].embedded_B_labels_TO_REVIEW) in ("1787","1787.0")
            frozen=K8E/"frame26_1/group_detail"/(c["old_group"]+"_EXACT_GROUP_MASK.npz")
            canonical=open_group(frozen,"review_outer","roi_xyxy")
        else:
            assert str(cr.new_source_B_labels)=="2424;2444;2504"
            assert int(cr.new_exact_union_area_px2)==297
            assert int(cr.new_RAW_source_areas_sum_px2)==870
            assert int(cr.new_internal_duplicate_pixels_removed)==573
            assert str(cr.old_K8D_B_mask_overlap_json)=="[]"
            canonical=open_group(Path(cr.npz_file),"exact_review_union","RAW_global_bbox")
        proposed=open_group(Path(cr.npz_file),"exact_review_union","RAW_global_bbox")
        bbox_union=(
           min(canonical["box"][0],proposed["box"][0]),
           min(canonical["box"][1],proposed["box"][1]),
           max(canonical["box"][2],proposed["box"][2]),
           max(canonical["box"][3],proposed["box"][3]))
        original=align_mask(canonical,bbox_union)
        overlay=align_mask(proposed,bbox_union)
        assert np.array_equal(original,overlay)  # no alternate outer allowed
        assert original.sum()==c["area"]
        ys,xs=np.where(canonical["mask"])
        x0,y0,x1,y1=canonical["box"]
        bbox=(x0+int(xs.min()),y0+int(ys.min()),x0+int(xs.max())+1,y0+int(ys.max())+1)
        feret=float(max_feret_centers_px(np.column_stack((xs,ys))))
        grade,grade_rule=grade_size(int(len(xs)),feret,SizeGradeConfig())
        possible_j5=j5[(j5.display_bbox_x_global<bbox[2])&
            (j5.display_bbox_xmax_inclusive>=bbox[0])&
            (j5.display_bbox_y_global<bbox[3])&
            (j5.display_bbox_ymax_inclusive>=bbox[1])]
        assert len(possible_j5)==0,("Crosschannel J5 bbox overlap: review separately!",c["band"])
        sample_ID=c["review_id"]
        outmask=OUT/"confirmed_mask_reviewonly"/(sample_ID+"_verified_exact_raw_union.npz")
        outmask.parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(outmask,
            verified_binary_mask=np.uint8(canonical["mask"]),
            global_raw_roi_xyxy=np.int32(canonical["box"]),
            source_B_connected_labels=np.int32(c["members"]),
            human_review_one_darkspot_and_complete_outer=np.uint8([1]),
            source_canonical_mask_sha256=np.array([sha(canonical["file"])]))
        with np.load(outmask,allow_pickle=False) as z:
            assert np.array_equal(z["verified_binary_mask"].astype(bool),canonical["mask"])
            assert tuple(map(int,z["global_raw_roi_xyxy"]))==canonical["box"]
        r={
            "review_object_id":sample_ID,"frame":1,"band_id":c["band"],
            "user_confirmed_one_physical_darkspot":True,
            "user_confirmed_outer_complete_and_accurate":True,
            "user_confirmation_basis":"USER_MESSAGE_2026_10_17_BAND02_AND_BAND04_EACH_ONE_DARKSPOT_OUTER_COMPLETE",
            "connected_B_source_labels":";".join(map(str,c["members"])),
            "canonical_mask_source_stage":c["stage"],
            "canonical_old_K8E_group_id":c["old_group"],
            "crosschecked_new_K8I2_group_id":c["new_group"],
            "independent_physical_darkspot_count_for_this_review":1,
            "area_exact_union_detector_px2":int(canonical["mask"].sum()),
            "longest_Feret_detector_px":round(feret,4),
            "area_detector_image_um2":round(int(len(xs))*PITCH**2,3),
            "longest_Feret_detector_image_um":round(feret*PITCH,3),
            "trial_size_grade_not_physical_plane":grade,
            "grade_rule":grade_rule,
            "RAW_bbox_xyxy_exclusive":json.dumps(bbox),
            "RAW_center_xy":json.dumps((round(float(x0+xs.mean()),3),
                                        round(float(y0+ys.mean()),3))),
            "overlap_original_J5_display_bbox_candidate_count":len(possible_j5),
            "canonical_source_mask_npz":str(canonical["file"]),
            "crosscheck_new_mask_npz":str(proposed["file"]),
            "verified_copy_npz":str(outmask),
            "original_J5_and_B_IDs_unchanged":True,
            "production_quality_approval_not_asserted":True,
            "optical_object_plane_size_calibrated":False
            }
        approvals.append(r)
        for lid in c["members"]:
            members.append({"review_object_id":sample_ID,"frame":1,"band_id":c["band"],
                "source_B_connected_component_label":lid,
                "all_one_physical_darkspot_user_confirmed":True,
                "member_role":("HISTORICAL_K8D_SOURCE" if c["band"]==2 and lid==1902
                          else "NEW_K8I2_RAW_SOURCE" if c["band"]==2 and lid==1787
                          else "NEW_K8I2_RAW_SOURCE"),
                "do_not_double_count_same_darkspot":True,
                "original_source_B_label_still_preserved":True})
        provenance.extend((canonical["file"],proposed["file"]))
        new_masks.append((c,canonical,bbox,feret))
    tab=pd.DataFrame(approvals)
    assert len(tab)==2 and len(members)==5
    assert tab.area_exact_union_detector_px2.sum()==695
    assert tab.independent_physical_darkspot_count_for_this_review.sum()==2
    tab.to_csv(OUT/"two_user_confirmed_darkspots_no_duplicate_area.csv",
               index=False,encoding="utf-8-sig")
    pd.DataFrame(members).to_csv(OUT/"five_B_source_components_to_two_user_confirmed_darkspots.csv",
                index=False,encoding="utf-8-sig")
    return new_masks,approvals,provenance

def draw_overlay(groups):
    base=background(1,4)
    H,W=base.shape[:2]
    full=base.copy()
    names=ImageFont.truetype(FONT,17)
    sub=ImageFont.truetype(FONT,14)
    cv2palette=[(228,189,35),(33,212,241)]
    # WORK J5 MEDLARGE from frozen source; purposefully omit all other
    # pending K8I sources in this dedicated approval-only comparison.
    j5=pd.read_csv(K8B/"frame26_1/original_J5_object_center_workband_classification.csv")
    existing=j5[(j5.K8A_region_code_by_original_J5_center==2)&
                (j5.grade.isin(["MEDIUM","LARGE"]))]
    assert len(existing)==25
    for j in existing.itertuples(index=False):
        old=(float(j.display_bbox_x_global),float(j.display_bbox_y_global),
             float(j.display_bbox_xmax_inclusive)+1,float(j.display_bbox_ymax_inclusive)+1)
        expanded=expand_bbox_xyxy(old,(C.RAW_WIDTH,C.RAW_HEIGHT),1.5)
        a,b,c,d=bbox_to_display_px(expanded,(C.RAW_WIDTH,C.RAW_HEIGHT),(W,H),4)
        cv2.rectangle(full,(a,b),(c,d),
                      (29,214,241) if j.grade=="MEDIUM" else (42,54,243),1)
    confirmed=base.copy()
    labels=[]
    for idx,(config,source,bbox,feret) in enumerate(groups):
        expanded=expand_bbox_xyxy(bbox,(C.RAW_WIDTH,C.RAW_HEIGHT),1.5)
        xy=bbox_to_display_px(expanded,(C.RAW_WIDTH,C.RAW_HEIGHT),(W,H),4)
        for canvas in (full,confirmed):
            cv2.rectangle(canvas,(xy[0],xy[1]),(xy[2],xy[3]),cv2palette[idx],1,cv2.LINE_8)
        labels.append((config,xy,feret))
    for img,label,detail,filename in (
        (full,"第一帧原J5中大 + 新确认Band02、Band04两处暗斑",
         "此图仅显示原J5中大与两处人工确认补漏；完整未确认候选请看原K8I第二阶段专图。",
         "01_FRAME1_2_CONFIRMED_plus_frozen_J5_MEDLARGE.png"),
        (confirmed,"第一帧两处人工确认暗斑（Band02 / Band04）",
         "1.5倍细框，原RAW精确轮廓用于面积及最长Feret；所有旧候选ID保留。",
         "02_ONLY_B02_B04_two_confirmed_darkspots.png")):
        pil=Image.fromarray(cv2.cvtColor(img,cv2.COLOR_BGR2RGB))
        d=ImageDraw.Draw(pil)
        for conf,xy,feret in labels:
            key=f"B{conf['band']:02d}"
            area=conf["area"]
            p=(min(xy[0]+7,W-310), max(0,xy[1]-41))
            d.rectangle((p[0],p[1],p[0]+305,p[1]+39),fill=(22,24,27))
            d.text((p[0]+5,p[1]+2),f"{key} 一处暗斑 | A={area} px²",font=sub,fill=(243,243,243))
            d.text((p[0]+5,p[1]+20),f"Feret={feret*PITCH:.1f} μm(像面)",font=sub,fill=(218,218,219))
        out=cv2.cvtColor(np.asarray(pil),cv2.COLOR_RGB2BGR)
        header=Image.new("RGB",(W,92),(25,26,29));dr=ImageDraw.Draw(header)
        dr.text((8,7),label,font=names,fill=(244,244,244))
        dr.text((8,41),detail,font=sub,fill=(226,226,226))
        dr.text((8,67),"原J5/B源、历史K8E和本轮K8I2未覆盖；尺寸为探测器像面当量，不是物面尺寸。",font=sub,fill=(211,217,222))
        write_lossless(OUT/filename,np.vstack((
            cv2.cvtColor(np.asarray(header),cv2.COLOR_RGB2BGR),out)))

def main():
    if OUT.exists():raise FileExistsError("Refuse overwrite "+str(OUT))
    OUT.mkdir(parents=True)
    masks,records,files=source_proof()
    draw_overlay(masks)
    # Review images that the user actually examined, copied unchanged.
    original=[
        (K8I2/"frame26_1/05_B04_TRIPLE_RAW_sources_outer_exact_union_REVIEW.png",
         "03_Band04_verified_source_image_UNCHANGED.png"),
        (K8I2/"frame26_1/06_B02_1787_vs_OLD_B1902_overlap_REVIEW.png",
         "04_Band02_verified_source_image_UNCHANGED.png")]
    for src,name in original:
        shutil.copyfile(src,OUT/name)
        assert sha(src)==sha(OUT/name)
    summary={
       "stage":"K8I_STAGE2_HUMAN_CONFIRMED_EXACT_TWO_SEPARATE_DARKSPOTS",
       "approved_scope":"F26(1) band02 original B 1787+1902 AND band04 B 2424+2444+2504, each ONE physical darkspot and complete accurate outline",
       "confirmed_physical_spot_count_in_this_review":2,
       "original_B_connected_components_contributing":5,
       "unique_source_mask_area_sum_px2_for_these_two_spots":695,
       "do_not_double_count_B02_1787_with_old_B1902":True,
       "do_not_sum_B04_three_289_295_286_as_distinct_spots":True,
       "K8E_F2_B2_G006_and_G009_prior_confirmations_unchanged":True,
       "ALL_OTHER_NEW_K8I2_REVIEW_GROUPS_STILL_UNCONFIRMED":True,
       "official_J5_source_IDs_source_masks_and_all_historical_results_unchanged":True,
       "image_plane_pixel_pitch_um":PITCH,
       "true_optical_object_plane_calibration_available":False,
       "records":records,
       "source_mask_SHA256":{str(x):sha(x) for x in dict.fromkeys(files)}}
    (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),
                                      encoding="utf-8")
    print("K8I2_TWO_USER_CONFIRMATIONS_WRITTEN",
          json.dumps({"areas":[x["area_exact_union_detector_px2"] for x in records],
                      "rows":len(records),"source_fragments":5},ensure_ascii=False),
          flush=True)

if __name__=="__main__":main()
