"""Case03-K8D full RAW regression: repair too-small-final-contour fallback.

Reuses previous exact 3/2/1.5MAD pixel masks, recomputes raw_outer_envelope
to verify inputs, reconstructs complete B-label membership, then generates
new two-frame 6-panel images and separate MED/LARGE and AMBIGUOUS views.
All input RAW/B/J5/K5/previous trial data are READ ONLY.
"""
from pathlib import Path
from dataclasses import replace,asdict
import json,sys
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k3_spot_contour_pilot import PilotConfig,raw_outer_envelope
from src.detection.case03i_size_grade import SizeGradeConfig,grade_size,max_feret_centers_px,GRADE_COLORS_BGR
from src.detection.case03k8d_group_stability import K8DConfig,resolve
from scripts.run_case03g_joint_noise_refinement import save_png

UP=C.OUTPUT_ROOT/"case03k8c_outlines_prioritized/run_20261013_K5RAW_contour_expansion_pilot_v1"
B=C.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
OUTPUT=C.OUTPUT_ROOT/"case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3"
CFG=K8DConfig()
OLD_CFG=PilotConfig()
GRADE=SizeGradeConfig()
SCALE=8
FLOORS=(3.,2.,1.5)

def decode(p):
    raw=p.read_bytes()
    im=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_UNCHANGED)
    if im is None:raise IOError(p)
    return im

def features(m):
    yy,xx=np.where(m)
    if not len(xx):return {"px":0,"length_um":0.,"area_um2":0.,"grade":"NONE"}
    feret=max_feret_centers_px(np.column_stack([xx,yy]))
    grade,_=grade_size(len(xx),feret,GRADE)
    return {"px":len(xx),"length_um":round(feret*float(C.PIXEL_SIZE_UM),2),
            "area_um2":round(len(xx)*float(C.PIXEL_SIZE_UM)**2,2),
            "grade":grade}

def grayscaled(raw):
    arr=np.asarray(raw,np.float32)
    lo,hi=np.percentile(arr,[1,99.5])
    return cv2.cvtColor(np.uint8(np.clip((arr-lo)/max(hi-lo,1)*255,0,255)),cv2.COLOR_GRAY2BGR)

def panel(raw,mask,title,desc,color):
    base=cv2.resize(grayscaled(raw),(256,256),interpolation=cv2.INTER_NEAREST)
    if mask is not None and mask.any():
        maskbig=cv2.resize(np.uint8(mask),(256,256),interpolation=cv2.INTER_NEAREST)
        cont,_=cv2.findContours(maskbig,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(base,cont,-1,color,1,cv2.LINE_8)
    hdr=np.full((78,256,3),25,np.uint8)
    cv2.putText(hdr,title[:27],(8,25),cv2.FONT_HERSHEY_SIMPLEX,.5,(239,239,239),1)
    cv2.putText(hdr,desc[:36],(8,55),cv2.FONT_HERSHEY_SIMPLEX,.39,(215,215,215),1)
    return np.vstack((hdr,base))

def make6(raw,seed,trials,proposed,decision,frame,band,label):
    col=(235,220,30) if decision["status"].startswith("STABLE_") else (30,160,240)
    series=[
      panel(raw,None,f"F{frame} B{band} C{label} RAW","Original RAW", (240,240,240)),
      panel(raw,seed,"ORIGINAL B SOURCE",f"{int(seed.sum())} px2", (10,25,240))]
    for k in FLOORS:
        series.append(panel(raw,trials[k],f"K5 RAW {k:g}MAD",
                            f"{int(trials[k].sum())} px2",(20,208,245)))
    series.append(panel(raw,proposed,"K8D FULL OUTER",
                f"{int(proposed.sum())} px2 {decision['status'][:12]}",col))
    return np.hstack(series)

def draw_global(dest,mask,xyxy,color,caption=None):
    x0,y0=[int(v) for v in xyxy[:2]]
    contours,_=cv2.findContours(np.uint8(mask),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    curves=[]
    for cnt in contours:
        pts=cnt.reshape(-1,2).astype(np.int32)
        pts[:,0]=(pts[:,0]+x0)//SCALE
        pts[:,1]=(pts[:,1]+y0)//SCALE
        curves.append(pts.reshape(-1,1,2))
    if curves:
        cv2.drawContours(dest,curves,-1,color,1,cv2.LINE_8)
        if caption:
            x=min(int(c[:,0,0].min()) for c in curves)
            y=min(int(c[:,0,1].min()) for c in curves)
            cv2.putText(dest,caption,(max(2,x),max(11,y-4)),
                        cv2.FONT_HERSHEY_SIMPLEX,.34,color,1,cv2.LINE_8)

def make_banner(im,label,desc):
    bar=np.full((90,im.shape[1],3),26,np.uint8)
    cv2.putText(bar,label,(12,31),cv2.FONT_HERSHEY_SIMPLEX,.56,(230,230,230),1)
    cv2.putText(bar,desc[:112],(12,63),cv2.FONT_HERSHEY_SIMPLEX,.42,(214,214,214),1)
    return np.vstack([bar,im])

def background(frame):
    raw=np.memmap(C.DATA_ROOT/f"26 ({frame}).raw",dtype=">u2",mode="r",
                  shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
    return raw,grayscaled(np.asarray(raw[::SCALE,::SCALE],np.uint16))

def frozen_j5(frame,bg):
    src=pd.read_csv(B/f"frame26_{frame}/original_J5_object_center_workband_classification.csv")
    old=src[(src.K8A_region_code_by_original_J5_center==2)&
            (src.grade.isin(["MEDIUM","LARGE"]))]
    dst=bg.copy()
    for r in old.itertuples(index=False):
        x=int(r.display_bbox_x_global)//SCALE
        y=int(r.display_bbox_y_global)//SCALE
        xx=int(r.display_bbox_xmax_inclusive)//SCALE
        yy=int(r.display_bbox_ymax_inclusive)//SCALE
        cv2.rectangle(dst,(x,y),(max(x,xx),max(y,yy)),
                      GRADE_COLORS_BGR[r.grade],1,cv2.LINE_8)
    return dst,len(old)

def overlap_fraction_global(left,right):
    ax,ay,bx,by=map(int,left["box"])
    cx,cy,dx,dy=map(int,right["box"])
    x0=max(ax,cx);x1=min(bx,dx)
    y0=max(ay,cy);y1=min(by,dy)
    if x0>=x1 or y0>=y1:return 0.
    a=left["mask"][y0-ay:y1-ay,x0-ax:x1-ax]
    b=right["mask"][y0-cy:y1-cy,x0-cx:x1-cx]
    n=int((a&b).sum())
    return n/max(min(int(left["mask"].sum()),int(right["mask"].sum())),1)

def process_frame(frame):
    out=OUTPUT/f"frame26_{frame}"
    out.mkdir()
    raw,bg=background(frame)
    baseline,nold=frozen_j5(frame,bg)
    chosen=pd.read_csv(UP/f"frame26_{frame}/all_selected_darkspots_K5RAW_outer_comparison.csv")
    Bmeta=json.loads((B/f"frame26_{frame}/summary.json").read_text(encoding="utf-8"))
    labels_by_band={}
    for spec in Bmeta["ROI_crops"]:
        band=int(spec["band_id"])
        if band not in set(chosen.band_id):continue
        bmask=decode(B/f"frame26_{frame}/band_{band:02d}_B_hysteresis_mask_cropped.png")>0
        n,labels,stats,centers=cv2.connectedComponentsWithStats(np.uint8(bmask),8)
        labels_by_band[band]=(labels,stats[:,cv2.CC_STAT_AREA],int(spec["ROI_global_xyxy"][1]),centers)
    records=[];visual=[]
    for r in chosen.itertuples(index=False):
        band=int(r.band_id);label=int(r.candidate_label)
        p=UP/f"frame26_{frame}"/f"band{band:02d}"/(
           f"F{frame}_B{band}_C{label:05d}_all_masks.npz")
        with np.load(p,allow_pickle=False) as z:
            seed=z["original_B_seed"].astype(bool)
            core=z["core_K8A_work"].astype(bool)
            box=z["full_resolution_roi_global_xyxy"].astype(int)
            saved={3.:z["raw_k3"].astype(bool),2.:z["raw_k2"].astype(bool),
                   1.5:z["raw_k1p5"].astype(bool)}
        x0,y0,x1,y1=map(int,box)
        roi=np.asarray(raw[y0:y1,x0:x1],np.uint16)
        labels,areas,yoffset,centroids=labels_by_band[band]
        labelroi=np.zeros((128,128),np.int32)
        a=max(y0,yoffset);b=min(y1,yoffset+labels.shape[0])
        if a<b:labelroi[a-y0:b-y0,:]=labels[a-yoffset:b-yoffset,x0:x1]
        if not np.array_equal(labelroi==label,seed):
            raise AssertionError(f"Original B labels not aligned F{frame} B{band} C{label}")
        # Match the original K8-B full connected component centroid exactly;
        # never recenter on a window-clipped component fragment.
        globalcen=(round(float(centroids[label,0]),3)-x0,
                   round(float(centroids[label,1]),3)+yoffset-y0)
        # K3 source used the original OpenCV component centroid, which may
        # differ from pixel-center recompute only <0.001 px.
        trials={};audits={}
        for floor in FLOORS:
            m,aud=raw_outer_envelope(
                roi,seed,globalcen,
                replace(PilotConfig(),raw_noise_sigma_multiplier=floor))
            if not np.array_equal(m,saved[floor]):
                raise AssertionError(f"Archived RAW mismatch F{frame}B{band}C{label} k={floor}")
            trials[floor]=m;audits[floor]=aud
        proposed,decision=resolve(seed,trials,audits,core,labelroi,areas,label)
        assert not np.any(seed&~proposed)
        feat0=features(seed);feat1=features(proposed)
        dest=out/f"band{band:02d}"
        dest.mkdir(exist_ok=True)
        basename=f"F{frame}_B{band}_C{label:05d}"
        save_png(dest/(basename+"_K8D_six_panel.png"),
                 make6(roi,seed,trials,proposed,decision,frame,band,label))
        np.savez_compressed(dest/(basename+"_K8D_all_masks.npz"),
            original_B_source=np.uint8(seed),
            raw_k3=np.uint8(trials[3.]),raw_k2=np.uint8(trials[2.]),
            raw_k1p5=np.uint8(trials[1.5]),
            K8D_full_outer=np.uint8(proposed),
            work_core=np.uint8(core),
            B_label_grid_in_roi=np.int32(labelroi),
            raw_global_roi_xyxy=np.int32(box))
        uid=f"F{frame}_B{band}_C{label:05d}"
        record={"uid":uid,"frame":frame,"band_id":band,"candidate_label":label,
          "source_area_px2":feat0["px"],"K8D_review_outer_px2":feat1["px"],
          "source_area_detector_um2":feat0["area_um2"],
          "K8D_area_detector_um2_PROVISIONAL":feat1["area_um2"],
          "K8D_length_detector_um_PROVISIONAL":feat1["length_um"],
          "original_grade":feat0["grade"],
          "proposed_grade_PROVISIONAL":feat1["grade"],
          "RAW_k3_px2":int(trials[3.].sum()),
          "RAW_k2_px2":int(trials[2.].sum()),
          "RAW_k1p5_px2":int(trials[1.5].sum()),
          "selected_noise_sigma":decision["selected_k"],
          "status":decision["status"],
          "rejection_reasons":";".join(decision["reasons"]),
          "associated_B_labels":";".join(map(str,decision["group"]["eligible_siblings"])),
          "partial_B_competitors":";".join(map(str,decision["group"]["partial_competitors"])),
          "group_member_B_labels":";".join(map(str,decision["group"]["proposed_review_B_member_labels"])),
          "review_evidence_json":json.dumps(decision,ensure_ascii=False),
          "manual_confirm_outer":"","manual_confirm_group":"",
          "source_B_and_J5_masks_unchanged":True,
          "physical_object_plane_calibration_confirmed":False,
          "no_automatic_ID_merge":True,
          "six_panel":str(dest/(basename+"_K8D_six_panel.png"))}
        records.append(record)
        visual.append({"row":record,"box":box,"mask":proposed})
        print("K8D_OBJECT",uid,feat0["px"],feat1["px"],decision["status"],flush=True)
    pd.DataFrame(records).to_csv(out/"all_K8D_original_vs_outer_review.csv",
                                 encoding="utf-8-sig",index=False)
    # Display-level de-duplication only: overlap>0.65 of the smaller proposed
    # mask indicates both seeds likely show the same dark region. Any
    # inconsistent original B membership is marked conflict, not auto-merged.
    parent=list(range(len(visual)))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    for i in range(len(visual)):
        for j in range(i+1,len(visual)):
            if visual[i]["row"]["band_id"]!=visual[j]["row"]["band_id"]:continue
            if overlap_fraction_global(visual[i],visual[j])>=.65:
                u=find(i);v=find(j)
                if u!=v:parent[v]=u
    groups={}
    for i in range(len(visual)):
        groups.setdefault(find(i),[]).append(visual[i])
    allimage=bg.copy();stable=baseline.copy();stableonly=bg.copy();ambiguous=bg.copy()
    representative_rows=[];number_stable=0;number_amb=0
    for i,member in groups.items():
        # Larger masks to represent each proposed source group; preserve all
        # ungrouped underlying source trial records, do not blend physical IDs.
        member.sort(key=lambda z:-z["row"]["K8D_review_outer_px2"])
        z=member[0];entry=z["row"]
        statuses=[m["row"]["status"] for m in member]
        eligible=all(s.startswith("STABLE_") for s in statuses)
        has_conflict=any(m["row"]["partial_B_competitors"] for m in member)
        if len(member)>1:
            # Overlapping proposals of distinct B seed identity are NOT an
            # accepted association without a full source pixel audit.
            # Keep as amber review until human confirms.
            eligible=False
            has_conflict=True
        if entry["K8D_review_outer_px2"]<=entry["source_area_px2"]:
            continue
        col=(235,220,35) if eligible and not has_conflict else (30,165,235)
        draw_global(allimage,z["mask"],z["box"],col,
                    f"B{entry['band_id']}-{entry['candidate_label']}")
        if eligible and not has_conflict and entry["proposed_grade_PROVISIONAL"] in ("MEDIUM","LARGE"):
            draw_global(stable,z["mask"],z["box"],col,
                      f"B{entry['band_id']}-{entry['candidate_label']}")
            draw_global(stableonly,z["mask"],z["box"],col)
            number_stable+=1
        else:
            draw_global(ambiguous,z["mask"],z["box"],(30,165,235),
                       f"B{entry['band_id']}-{entry['candidate_label']}")
            number_amb+=1
        representative_rows.append({
            "band_id":entry["band_id"],
            "representative_B_label":entry["candidate_label"],
            "member_B_labels_for_display_only":";".join(
                str(m["row"]["candidate_label"]) for m in member),
            "display_status":"STABLE" if eligible and not has_conflict else "AMBIGUOUS",
            "physical_IDs_merged":False,
            "source_masks_changed":False,
            "manual_review_required":True})
    pd.DataFrame(representative_rows).to_csv(
        out/"deduplicated_review_groups_NO_official_merge.csv",
        index=False,encoding="utf-8-sig")
    products={
      "01_original_J5_WORK_MED_LARGE.png":make_banner(baseline,
           f"FRAME 26({frame}) ORIGINAL J5 WORK MED/LARGE",
           f"Original {nold} J5 medium/large; all small candidates separate"),
      "02_J5_MED_LARGE_plus_STABLE_K8D.png":make_banner(stable,
           f"FRAME 26({frame}) K8D MED/LARGE PRIORITY",
           f"Original J5 {nold} + K8D stable {number_stable}, still under review"),
      "03_ALL_REPAIRED_FULL_OUTERS.png":make_banner(allimage,
           f"FRAME 26({frame}) K8D FULL REVIEW OUTERS",
           f"CYAN stable; ORANGE ambiguous; overlapping suggestions drawn once"),
      "04_AMBIGUOUS_NO_SHRINK_OUTERS.png":make_banner(ambiguous,
           f"FRAME 26({frame}) K8D AMBIGUOUS COMPLETE OUTERS",
           f"{number_amb} review overlays; not reverted to tiny initial seed"),
      "05_STABLE_OUTERS_ONLY.png":make_banner(stableonly,
           f"FRAME 26({frame}) K8D STABLE RAW OUTERS ONLY",
           "Not actual accepted physical defect area, no object-plane calibration")}
    for file,image in products.items():save_png(out/file,image)
    summary={"frame":frame,"objects_processed":len(records),
          "contours_expanded":int(sum(z["K8D_review_outer_px2"]>z["source_area_px2"] for z in records)),
          "stable_mediumlarge_overlays":number_stable,
          "ambiguous_complete_overlays":number_amb,
          "frozen_J5_work_mediumlarge":nold,
          "all_B_source_pixels_preserved":True,
          "original_J5_K5_untouched":True,
          "review_only_no_real_ID_merge":True}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    return summary

def main():
    if OUTPUT.exists():raise FileExistsError("Refuse to overwrite old experimental run "+str(OUTPUT))
    OUTPUT.mkdir(parents=True)
    result=[process_frame(frame) for frame in (1,2)]
    (OUTPUT/"summary.json").write_text(json.dumps({"stage":"K8D_MULTI_SOURCE_STABLE_CONTOURS",
         "frames":result,"config":asdict(CFG),"human_review_required":True,
         "no_original_detection_data_modified":True},ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8D_REAL_RAW_COMPLETED",json.dumps(result,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
