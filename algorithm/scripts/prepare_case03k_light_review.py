"""Case03-K0 (lightweight): prepare BLIND-TO-ALGORITHM manual-review examples.

No automatic labels are fabricated. Random seed and spatial/area strata are
frozen BEFORE any human label. 96 small candidate crops (4 area bins x 24),
plus up to 24 areas without any J5 prediction in the ROI. Unmarked
areas are NOT assumed truly defect-free: operators must inspect them for
missed defects. Candidate reviews are NOT valid Recall/Precision by themselves.
All features are descriptive; no thresholds/model are altered or trained.
"""
from __future__ import annotations
import argparse,json,sys,math
from pathlib import Path
import numpy as np,pandas as pd,cv2
from scipy.spatial import cKDTree
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from scripts.run_case03g_joint_noise_refinement import save_png
J5=cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_1_global_j5_v1"
OUTROOT=cfg.OUTPUT_ROOT/"case03k_light_review"
RNG_SEED=20261012
WINDOW=128
STRATA=("A_1px2","B_2to3px2","C_4to7px2","D_8pluspx2")
LABELS=("REAL_MICRO_DEFECT","BACKGROUND_NOISE","UNCERTAIN")
SHADE_NOTE="ROI percentile1-99.5 stretching is VISUAL only"


def area_stratum(area:int)->str:
    if area==1:return STRATA[0]
    if area<=3:return STRATA[1]
    if area<=7:return STRATA[2]
    return STRATA[3]


def choose_small(df:pd.DataFrame,rng:np.random.Generator,n_per:int=24)->pd.DataFrame:
    small=df.loc[df.grade.eq("SMALL")].copy()
    small["area_group"]=small.source_area_px2.map(area_stratum)
    small["cell_x"]=np.clip((small.center_x_global*4//cfg.RAW_WIDTH).astype(int),0,3)
    small["cell_y"]=np.clip((small.center_y_global*4//cfg.RAW_HEIGHT).astype(int),0,3)
    selected=[]
    used_points=[]
    for band in STRATA:
        pool=small.loc[small.area_group.eq(band)]
        if len(pool)<n_per:raise ValueError("insufficient small sample band "+band)
        groups={}
        for (y,x),part in pool.groupby(["cell_y","cell_x"],sort=False):
            idx=part.index.to_numpy(copy=True)
            rng.shuffle(idx)
            groups[(int(y),int(x))]=list(idx)
        counts={c:0 for c in groups}
        chosen=0
        while chosen<n_per:
            available=[c for c in groups if groups[c]]
            if not available:raise ValueError("exhausted candidates")
            rng.shuffle(available)
            cell=min(available,key=lambda c:counts[c])
            found=None
            while groups[cell]:
                idx=groups[cell].pop()
                candidate=small.loc[idx]
                cx=float(candidate.center_x_global);cy=float(candidate.center_y_global)
                if any(abs(cx-x)<=WINDOW and abs(cy-y)<=WINDOW for x,y in used_points):
                    continue
                found=idx
                used_points.append((cx,cy))
                break
            if found is not None:
                selected.append(found);counts[cell]+=1;chosen+=1
    result=small.loc[selected].copy()
    assert len(result)==len(STRATA)*n_per and result.global_defect_id.is_unique
    return result


def region_has_any_prediction(all_df:pd.DataFrame,
                              rng:np.random.Generator,
                              count:int=24)->list[dict]:
    """Coarse occupancy of ANY predicted bbox, conservative false-negative ROIs."""
    step=16
    H,W=cfg.RAW_HEIGHT,cfg.RAW_WIDTH
    grid=np.zeros(((H+step-1)//step,(W+step-1)//step),dtype=bool)
    for row in all_df.itertuples(index=False):
        ax=int(row.display_bbox_x_global)//step
        ay=int(row.display_bbox_y_global)//step
        bx=int(row.display_bbox_xmax_inclusive)//step+1
        by=int(row.display_bbox_ymax_inclusive)//step+1
        grid[ay:by,ax:bx]=True
    rows=[]
    # six by four spatial bins; one reviewed UNDETECTED-ROI per bin.
    for cy in range(4):
        for cx in range(6):
            xlow=int(cx*W/6)
            xhigh=min(W-WINDOW,int((cx+1)*W/6)-WINDOW)
            ylow=int(cy*H/4)
            yhigh=min(H-WINDOW,int((cy+1)*H/4)-WINDOW)
            for attempt in range(350):
                x=int(rng.integers(xlow,max(xlow+1,xhigh+1)))
                y=int(rng.integers(ylow,max(ylow+1,yhigh+1)))
                # Added 1 coarse cell padding to ensure truly zero objects
                # with bbox intersecting this patch.
                a=max(0,x//step-1);b=max(0,y//step-1)
                c=min(grid.shape[1],(x+WINDOW-1)//step+2)
                e=min(grid.shape[0],(y+WINDOW-1)//step+2)
                if grid[b:e,a:c].any():continue
                rows.append({
                    "sample_id":f"K0_NEGROI_{len(rows)+1:03d}",
                    "sample_kind":"NO_J5_CANDIDATE_ROI",
                    "global_defect_id":"",
                    "area_group":"UNPREDICTED_ROI",
                    "x0":x,"y0":y,"x1":x+WINDOW,"y1":y+WINDOW,
                    "target_x_global":"","target_y_global":"",
                    "spatial_cell":f"{cy}_{cx}",
                    "selection_note":"No existing J5 bounding box intersects this crop; not human-negative"})
                break
    if len(rows)<count:
        raise RuntimeError(f"only {len(rows)}/{count} full-background ROIs available; no silent drop")
    return rows[:count]


def raw_view16(image:np.ndarray)->np.ndarray:
    lo,hi=np.percentile(image.astype(float),[1,99.5])
    hi=max(hi,lo+1.)
    return np.clip((image.astype(float)-lo)/(hi-lo)*255,0,255).astype(np.uint8)


def sample_features(raw:np.ndarray,blackhat:np.ndarray,
                    s:dict,medium_tree:cKDTree)->dict:
    x0,y0,x1,y1=[int(s[k]) for k in ("x0","y0","x1","y1")]
    crop=np.asarray(raw[y0:y1,x0:x1],dtype=np.uint16)
    blur=crop.astype(np.float32)
    dog=cv2.GaussianBlur(blur,(0,0),8)-cv2.GaussianBlur(blur,(0,0),2)
    median=float(np.median(crop))
    mad=float(np.median(np.abs(crop.astype(float)-median)))
    result={
        "window_median_RAW_DN":round(median,4),
        "window_MAD_RAW_DN":round(mad,4),
        "window_STD_RAW_DN":round(float(crop.std()),4),
        "window_01p_RAW_DN":round(float(np.percentile(crop,1)),4),
        "window_995p_RAW_DN":round(float(np.percentile(crop,99.5)),4),
    }
    if s["sample_kind"]!="SMALL_CANDIDATE":
        result.update({
            "target_raw_median_DN":"","target_blackhat_peak_DN":"",
            "background_ring_median_DN":"","target_relative_dark_contrast":"",
            "target_dark_z_MAD":"","target_DoG_median_DN":"",
            "nearest_medium_large_center_distance_px":""
        })
        return result
    bx=int(s["source_bbox_x_global"]);by=int(s["source_bbox_y_global"])
    bw=int(s["source_bbox_width_px"]);bh=int(s["source_bbox_height_px"])
    bb=np.asarray(raw[by:by+bh,bx:bx+bw],dtype=np.uint16)
    bhat=np.asarray(blackhat[by:by+bh,bx:bx+bw],dtype=np.uint16)
    tx=float(s["target_x_global"])-x0
    ty=float(s["target_y_global"])-y0
    yy,xx=np.ogrid[:crop.shape[0],:crop.shape[1]]
    dist2=(xx-tx)**2+(yy-ty)**2
    ring=crop[(dist2>=14**2)&(dist2<=48**2)].astype(float)
    ringmed=float(np.median(ring))
    sig=max(3.,1.4826*float(np.median(np.abs(ring-ringmed))))
    tmed=float(np.median(bb))
    xx0=max(0,bx-x0);yy0=max(0,by-y0)
    xx1=min(crop.shape[1],xx0+bw);yy1=min(crop.shape[0],yy0+bh)
    q=dog[yy0:yy1,xx0:xx1]
    bigdist=float(medium_tree.query(
        np.array([float(s["target_x_global"]),float(s["target_y_global"])]))[0])
    result.update({
        "target_raw_median_DN":round(tmed,4),
        "target_blackhat_peak_DN":int(bhat.max()),
        "background_ring_median_DN":round(ringmed,4),
        "target_relative_dark_contrast":round((ringmed-tmed)/max(1.,ringmed),5),
        "target_dark_z_MAD":round((ringmed-tmed)/sig,5),
        "target_DoG_median_DN":round(float(np.median(q)),4),
        "nearest_medium_large_center_distance_px":round(bigdist,3),
    })
    return result


def candidate_cards(sample:dict,raw:np.ndarray,path:Path)->np.ndarray:
    x0,y0,x1,y1=[int(sample[k]) for k in ("x0","y0","x1","y1")]
    tile=np.asarray(raw[y0:y1,x0:x1],dtype=np.uint16)
    g=raw_view16(tile)
    marked=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
    if sample["sample_kind"]=="SMALL_CANDIDATE":
        bx=int(sample["source_bbox_x_global"])-x0
        by=int(sample["source_bbox_y_global"])-y0
        bw=int(sample["source_bbox_width_px"])
        bh=int(sample["source_bbox_height_px"])
        margin=4
        xlo=max(0,bx-margin);ylo=max(0,by-margin)
        xhi=min(g.shape[1]-1,bx+bw-1+margin)
        yhi=min(g.shape[0]-1,by+bh-1+margin)
        cv2.rectangle(marked,(xlo,ylo),(xhi,yhi),(20,235,235),1)
        cv2.drawMarker(marked,(int(sample["target_x_global"])-x0,
                               int(sample["target_y_global"])-y0),
                       (35,210,230),cv2.MARKER_CROSS,8,1,cv2.LINE_8)
    else:
        cv2.rectangle(marked,(1,1),(g.shape[1]-2,g.shape[0]-2),
                      (20,190,230),1)
    left=cv2.resize(cv2.cvtColor(g,cv2.COLOR_GRAY2BGR),
                    (256,256),interpolation=cv2.INTER_NEAREST)
    right=cv2.resize(marked,(256,256),interpolation=cv2.INTER_NEAREST)
    panel=np.hstack((left,right))
    header=np.full((68,panel.shape[1],3),25,np.uint8)
    cv2.putText(header,sample["sample_id"]+" / "+sample["sample_kind"],
                (10,23),cv2.FONT_HERSHEY_SIMPLEX,.52,(237,237,237),1,
                cv2.LINE_AA)
    cv2.putText(header,"LEFT RAW | RIGHT TARGET MARK (manual label not given)",
                (10,48),cv2.FONT_HERSHEY_SIMPLEX,.40,
                (211,211,211),1,cv2.LINE_AA)
    out=np.vstack((header,panel))
    save_png(path,out)
    return out


def contact(files:list[Path],dest:Path,title:str,columns:int=4)->None:
    cards=[]
    for p in files:
        im=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        if im is None:raise OSError(p)
        cards.append(cv2.resize(im,(384,243),interpolation=cv2.INTER_AREA))
    if not cards:raise ValueError("empty contact sheet")
    while len(cards)%columns:
        cards.append(np.full_like(cards[-1],25,dtype=np.uint8))
    grid=np.vstack([np.hstack(cards[i:i+columns]) for i in range(0,len(cards),columns)])
    save_png(dest,grid)


def run(run_id:str,small_per_band:int=24,negative_count:int=24)->dict:
    dest=OUTROOT/run_id
    if dest.exists():raise FileExistsError(dest)
    for f in ("cards","contact_sheets"):
        (dest/f).mkdir(parents=True)
    source=pd.read_csv(J5/"global_defects.csv",encoding="utf-8-sig")
    report=json.loads((J5/"summary.json").read_text(encoding="utf-8"))
    if report["stage"]!="J5_COMPLETE":raise ValueError("J5 incomplete")
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    blackhat_path=cfg.OUTPUT_ROOT/(
        "case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy")
    fused=np.load(blackhat_path,mmap_mode="r")
    rng=np.random.default_rng(RNG_SEED)
    selection=choose_small(source,rng,small_per_band)
    samples=[]
    for i,rec in enumerate(selection.itertuples(index=False),1):
        cx=int(round(rec.center_x_global));cy=int(round(rec.center_y_global))
        x0=min(max(0,cx-WINDOW//2),cfg.RAW_WIDTH-WINDOW)
        y0=min(max(0,cy-WINDOW//2),cfg.RAW_HEIGHT-WINDOW)
        s={
           "sample_id":f"K0_SMALL_{i:03d}",
           "sample_kind":"SMALL_CANDIDATE",
           "global_defect_id":rec.global_defect_id,
           "area_group":rec.area_group,
           "x0":x0,"y0":y0,"x1":x0+WINDOW,"y1":y0+WINDOW,
           "target_x_global":cx,"target_y_global":cy,
           "spatial_cell":f"{rec.cell_y}_{rec.cell_x}",
           "source_area_px2":int(rec.source_area_px2),
           "source_max_feret_px":float(rec.source_max_feret_px),
           "source_bbox_x_global":int(rec.source_bbox_x_global),
           "source_bbox_y_global":int(rec.source_bbox_y_global),
           "source_bbox_width_px":int(rec.source_bbox_width_px),
           "source_bbox_height_px":int(rec.source_bbox_height_px),
           "selection_note":"Area-stratified and spatially spread, no manual truth",
        }
        samples.append(s)
    negatives=region_has_any_prediction(source,rng,negative_count)
    samples.extend(negatives)
    larger=source[source.grade.ne("SMALL")]
    tree=cKDTree(larger[["center_x_global","center_y_global"]].values)
    records=[]
    for sample in samples:
        row=dict(sample)
        row.update(sample_features(raw,fused,row,tree))
        row.update(
            manual_candidate_label="",
            human_confidence="",
            manual_complete_roi_review="",
            manual_any_missed_defect_in_roi="",
            manual_missed_count="",
            operator_comment="",
        )
        records.append(row)
        candidate_cards(row,raw,dest/"cards"/(row["sample_id"]+".png"))
    # Audit visual files are present; never accidentally reclassify by machine.
    allcols=pd.DataFrame(records)
    allcols.to_csv(dest/"manual_review_template.csv",index=False,
                   encoding="utf-8-sig")
    # Separate unannotated numeric features, with ID to join labels in future.
    feature_only=allcols.drop(columns=[
      "manual_candidate_label","human_confidence",
      "manual_complete_roi_review","manual_any_missed_defect_in_roi",
      "manual_missed_count","operator_comment"])
    feature_only.to_csv(dest/"unlabeled_features.csv",index=False,
                        encoding="utf-8-sig")
    for area in STRATA:
        matched=[dest/"cards"/(r["sample_id"]+".png")
                  for r in records if r["area_group"]==area]
        contact(matched,dest/"contact_sheets"/(area+"_contact.png"),area)
    controls=[dest/"cards"/(r["sample_id"]+".png")
              for r in records if r["sample_kind"]=="NO_J5_CANDIDATE_ROI"]
    contact(controls,dest/"contact_sheets"/"unpredicted_ROI_review_contact.png",
            "No existing J5 objects; check missed defects")
    nump=len(list((dest/"cards").glob("*.png")))
    sheetcount=len(list((dest/"contact_sheets").glob("*.png")))
    expected_n=small_per_band*4+negative_count
    if nump!=expected_n or sheetcount!=5:
        raise AssertionError((nump,expected_n,sheetcount))
    details={
      "stage":"CASE03K0_SAMPLES_PREPARED_NOT_LABELED",
      "source_J5":str(J5),
      "small_candidate_samples":small_per_band*4,
      "small_samples_by_area_stratum":{str(s):small_per_band for s in STRATA},
      "unpredicted_ROI_samples":negative_count,
      "sample_pixel_window":WINDOW,
      "all_review_cards":nump,
      "contact_sheets":sheetcount,
      "sampling_seed":RNG_SEED,
      "no_human_labels_provided":True,
      "no_algorithm_threshold_updated":True,
      "not_a_blind_evaluation_frame":True,
      "future_independent_validation_required":True,
      "no_recall_precision_can_be_claimed_yet":True,
      "raw_image_display_stretch_only":"each ROI P1-P99.5 local 8-bit mapping",
      "predicted_empty_ROIs_are_NOT_confirmed_defect_free":True,
      "human_exhaustive_roi_review_required_for_missed_defect_assessment":True,
      "accepted_manual_candidate_labels":list(LABELS),
      "annotation_guide":(
        "For SMALL_CANDIDATE: set manual_candidate_label to "
        "REAL_MICRO_DEFECT / BACKGROUND_NOISE / UNCERTAIN. "
        "For every ROI, mark manual_complete_roi_review TRUE only after "
        "checking all visible dark spots for missed defects; a no-prediction "
        "ROI is not necessarily negative. Do NOT compute recall from this "
        "partial candidate-focused sample.")
    }
    (dest/"summary.json").write_text(json.dumps(details,ensure_ascii=False,indent=2),
                                     encoding="utf-8")
    print("CASE03K0_COMPLETE",json.dumps(details,ensure_ascii=False),flush=True)
    print("OUTPUT",dest,flush=True)
    return details


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--run-id",default="run_20261012_small_candidate_manual_review_v1")
    parser.add_argument("--small-per-band",type=int,default=24)
    parser.add_argument("--negative-count",type=int,default=24)
    args=parser.parse_args()
    run(args.run_id,args.small_per_band,args.negative_count)
