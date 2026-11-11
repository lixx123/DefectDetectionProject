from pathlib import Path
import json, shutil, tempfile, sys
import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts.run_unified_raw_input import fresh_j5, fresh_b
from scripts import run_case03_unified_final_detector_26_1_2 as old
from src.detection.case03k8a_band_locator import (
    BandLocatorConfig, locate_transmission_bands, rasterize_region_masks
)
from src.detection.unified_raw_recovery import recover_objects
from src.detection.case03i_size_grade import max_feret_centers_px
SOURCE_RUN = ROOT / "outputs/AUDIT_20261105_CURRENT_SOURCE_26_1_v1"
AUTO_RUN = ROOT / "outputs/PRODUCTION_AUTO_REPORT_26_1_NO_HISTORY_20261106"
REPORT_DIR = ROOT / "PRODUCTION_AUTO_REPORT_20261106"
ASSET_DIR = REPORT_DIR / "assets_stagewise"
RAW_PATH = C.DATA_ROOT / "26 (1).raw"
FRAME = 1
PREVIEW_W = 1800
PREVIEW_H = round(C.RAW_HEIGHT * PREVIEW_W / C.RAW_WIDTH)
SX = PREVIEW_W / C.RAW_WIDTH
SY = PREVIEW_H / C.RAW_HEIGHT

COLORS = {
    "green": (40, 220, 70),
    "yellow": (0, 220, 255),
    "cyan": (255, 220, 0),
    "blue": (255, 100, 40),
    "orange": (0, 140, 255),
    "red": (30, 30, 245),
    "magenta": (220, 60, 220),
    "gray": (170, 170, 170),
    "white": (245, 245, 245),
}

def save(path, image):
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(path.suffix or ".png", image)
    if not ok:
        raise RuntimeError(f"Could not encode image: {path}")
    encoded.tofile(str(path))

def read_image(path, flags=cv2.IMREAD_UNCHANGED):
    data=np.fromfile(str(path),dtype=np.uint8)
    return cv2.imdecode(data,flags)

def stretch_gray(a, p0=1.0, p1=99.5):
    a = np.asarray(a)
    finite = np.isfinite(a)
    if not np.any(finite):
        return np.zeros(a.shape, np.uint8)
    lo, hi = np.percentile(a[finite], [p0, p1])
    if hi <= lo:
        hi = lo + 1.0
    out = np.zeros(a.shape, np.uint8)
    out[finite] = np.clip((a[finite].astype(np.float32) - lo) * (255.0 / (hi-lo)), 0, 255).astype(np.uint8)
    return out

def header(canvas, title, subtitle=""):
    h = 64
    out = np.zeros((canvas.shape[0] + h, canvas.shape[1], 3), np.uint8)
    out[:h] = (25, 25, 25)
    out[h:] = canvas
    cv2.putText(out, title, (18, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (245,245,245), 2, cv2.LINE_AA)
    if subtitle:
        cv2.putText(out, subtitle[:180], (18, 51), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (210,210,210), 1, cv2.LINE_AA)
    return out

def raw_crop_bgr(raw_crop):
    return cv2.cvtColor(stretch_gray(raw_crop, 1, 99.5), cv2.COLOR_GRAY2BGR)

def add_panel_label(im, label, x=8, y=24):
    cv2.putText(im, label, (x,y), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255,255,255), 1, cv2.LINE_AA)

def overlay_binary(base, mask, color, alpha=0.72):
    m = np.asarray(mask, bool)
    if m.shape[:2] != base.shape[:2]:
        raise ValueError((m.shape, base.shape))
    if np.any(m):
        layer = base.copy()
        layer[m] = color
        return cv2.addWeighted(layer, alpha, base, 1-alpha, 0)
    return base.copy()

def draw_bbox_global(im, bbox, color, thickness=1):
    x0,y0,x1,y1 = map(float, bbox)
    a = (int(round(x0*SX)), int(round(y0*SY)))
    b = (int(round((x1-1)*SX)), int(round((y1-1)*SY)))
    cv2.rectangle(im, a, b, color, thickness, cv2.LINE_AA)

def draw_obj_on_preview(canvas, obj, color, radius=0):
    x0,y0,x1,y1 = map(int, obj["bbox"])
    m = np.asarray(obj["mask"], bool)
    yy,xx = np.nonzero(m)
    if len(xx)==0:
        return
    px = np.clip(np.rint((xx+x0)*SX).astype(np.int32),0,PREVIEW_W-1)
    py = np.clip(np.rint((yy+y0)*SY).astype(np.int32),0,PREVIEW_H-1)
    if radius:
        for x,y in zip(px,py):
            cv2.circle(canvas,(int(x),int(y)),radius,color,-1,cv2.LINE_8)
    else:
        canvas[py,px] = color

def draw_sources_on_preview(canvas, sources, records, color_fn):
    for r in records:
        uid = r.get("candidate_source_uid")
        obj = sources.get(uid)
        if obj is None:
            continue
        x0,y0,x1,y1 = map(int,obj["bbox"])
        yy,xx = np.nonzero(np.asarray(obj["mask"],bool))
        if len(xx)==0:
            continue
        px=np.clip(np.rint((xx+x0)*SX).astype(np.int32),0,PREVIEW_W-1)
        py=np.clip(np.rint((yy+y0)*SY).astype(np.int32),0,PREVIEW_H-1)
        canvas[py,px]=color_fn(r)

def make_base(raw):
    sampled=np.asarray(raw[::4,::4],np.uint16)
    gray=stretch_gray(sampled,1,99.5)
    gray=cv2.resize(gray,(PREVIEW_W,PREVIEW_H),interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)

def draw_mask_outline(im, mask, color, thickness=2):
    cnts,_=cv2.findContours(np.asarray(mask,np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if cnts:
        cv2.drawContours(im,cnts,-1,color,thickness,cv2.LINE_AA)

def panel_grid(panels, cols, cell_w, cell_h, gap=10, bg=(22,22,22)):
    rows=(len(panels)+cols-1)//cols
    out=np.full((rows*cell_h+(rows+1)*gap,cols*cell_w+(cols+1)*gap,3),bg,np.uint8)
    for i,(im,label) in enumerate(panels):
        r=i//cols;c=i%cols
        x=gap+c*cell_w;y=gap+r*cell_h
        im=cv2.resize(im,(cell_w,cell_h),interpolation=cv2.INTER_NEAREST)
        out[y:y+cell_h,x:x+cell_w]=im
        strip=out[y:y+34,x:x+cell_w].copy()
        shade=np.full_like(strip,(18,18,18))
        out[y:y+34,x:x+cell_w]=cv2.addWeighted(strip,0.25,shade,0.75,0)
        cv2.rectangle(out,(x,y),(x+cell_w-1,y+cell_h-1),(100,100,100),1)
        cv2.putText(out,label,(x+8,y+24),cv2.FONT_HERSHEY_SIMPLEX,0.48,(255,255,255),1,cv2.LINE_AA)
    return out

def full_preview_with_header(base, title, subtitle):
    return header(base.copy(),title,subtitle)

def create_j4_images(raw, fused, j4dir, base):
    tile_files=sorted((j4dir/"tile_masks").glob("*.npz"))
    mask_preview=np.zeros((PREVIEW_H,PREVIEW_W),np.uint8)
    bridge_preview=np.zeros_like(mask_preview)
    for p in tile_files:
        with np.load(p,allow_pickle=False) as z:
            x0,y0,x1,y1=map(int,z["core_xyxy"])
            m=z["source_detected_uint8"]>0
            yy,xx=np.nonzero(m)
            if len(xx):
                px=np.clip(np.rint((xx+x0)*SX).astype(int),0,PREVIEW_W-1)
                py=np.clip(np.rint((yy+y0)*SY).astype(int),0,PREVIEW_H-1)
                mask_preview[py,px]=255
            b=z["inferred_bridge_i32"]>0
            yy,xx=np.nonzero(b)
            if len(xx):
                px=np.clip(np.rint((xx+x0)*SX).astype(int),0,PREVIEW_W-1)
                py=np.clip(np.rint((yy+y0)*SY).astype(int),0,PREVIEW_H-1)
                bridge_preview[py,px]=255
    canvas=base.copy()
    canvas[mask_preview>0]=COLORS["green"]
    canvas[bridge_preview>0]=COLORS["cyan"]
    j4csv=pd.read_csv(j4dir/"j4_unmerged_tile_objects.csv",encoding="utf-8-sig")
    large=j4csv[j4csv["size_grade"].isin(["MEDIUM","LARGE"])]
    for z in large.itertuples(index=False):
        draw_bbox_global(canvas,(z.source_bbox_x_global,z.source_bbox_y_global,
                                 z.source_bbox_x_global+z.source_bbox_width_px,
                                 z.source_bbox_y_global+z.source_bbox_height_px),
                         COLORS["red"],1)
    out=header(canvas,"J4 | TILE-LOCAL SOURCE MASK",
               f"tiles={len(tile_files)} | local objects={len(j4csv)} | exact source pixels shown in green; inferred display bridge in cyan")
    save(ASSET_DIR/"05_J4_fullframe_source_mask.png",out)

    # One exact J4 tile, showing the stored internal masks from the production run.
    tile_id="T011_007"
    p=j4dir/"tile_masks"/(tile_id+".npz")
    with np.load(p,allow_pickle=False) as z:
        x0,y0,x1,y1=map(int,z["core_xyxy"])
        source=z["source_detected_uint8"]>0
        grouped=z["grouped_source_only_i32"]
        bridge=z["inferred_bridge_i32"]>0
        continuous=z["continuous_display_i32"]>0
    rc=np.asarray(raw[y0:y1,x0:x1],np.uint16)
    bc=np.asarray(fused[y0:y1,x0:x1],np.uint16)
    rawim=raw_crop_bgr(rc)
    bh=stretch_gray(bc,50,99.7)
    bhim=cv2.applyColorMap(bh,cv2.COLORMAP_TURBO)
    sourceim=overlay_binary(rawim,source,COLORS["green"],0.75)
    grouped_color=np.zeros((*grouped.shape,3),np.uint8)
    vals=np.unique(grouped);vals=vals[vals>0]
    for i,v in enumerate(vals):
        col=tuple(int(q) for q in cv2.applyColorMap(np.array([[int((i*37)%180)]],np.uint8),cv2.COLORMAP_HSV)[0,0])
        grouped_color[grouped==v]=col
    groupedim=cv2.addWeighted(rawim,0.45,grouped_color,0.75,0)
    bridgeim=overlay_binary(rawim,bridge,COLORS["cyan"],0.85)
    contim=overlay_binary(rawim,continuous,COLORS["orange"],0.72)
    panels=[
        (rawim,"1 RAW core"),
        (bhim,"2 fused Black-Hat"),
        (sourceim,"3 J4 source mask"),
        (groupedim,"4 J1 grouped source-only"),
        (bridgeim,f"5 J2 inferred bridge ({int(bridge.sum())} px)"),
        (contim,"6 J2 continuous display mask"),
    ]
    grid=panel_grid(panels,3,500,500)
    save(ASSET_DIR/"06_J4_tile_internal_stages_T011_007.png",
         header(grid,"J4 INTERNAL EXAMPLE | T011_007",
                "All panels come from the same executed tile; bridge pixels are display geometry, not measured source area"))

def create_j5_image(raw, base, j4dir, j5dir):
    membership=pd.read_csv(j5dir/"global_object_membership.csv",encoding="utf-8-sig")
    defects=pd.read_csv(j5dir/"global_defects.csv",encoding="utf-8-sig")
    cross=set(defects.loc[defects["cross_tile_merged"].astype(bool),"global_defect_id"].astype(str))
    allmask=np.zeros((PREVIEW_H,PREVIEW_W),np.uint8)
    crossmask=np.zeros_like(allmask)
    for tid, rows in membership.groupby("source_tile_id", sort=False):
        p=j4dir/"tile_masks"/(str(tid)+".npz")
        with np.load(p,allow_pickle=False) as q:
            grouped=q["grouped_source_only_i32"]
            rect=q["core_xyxy"]
            x0,y0=int(rect[0]),int(rect[1])
            for z in rows.itertuples(index=False):
                local_id=int(z.source_local_object_index)
                yy,xx=np.nonzero(grouped==local_id)
                if len(xx)==0:
                    continue
                px=np.clip(np.rint((xx+x0)*SX).astype(int),0,PREVIEW_W-1)
                py=np.clip(np.rint((yy+y0)*SY).astype(int),0,PREVIEW_H-1)
                allmask[py,px]=255
                if str(z.global_defect_id) in cross:
                    crossmask[py,px]=255
    canvas=base.copy()
    canvas[allmask>0]=COLORS["cyan"]
    canvas[crossmask>0]=COLORS["red"]
    for z in defects[defects["cross_tile_merged"].astype(bool)].itertuples(index=False):
        draw_bbox_global(canvas,(z.source_bbox_x_global,z.source_bbox_y_global,
                                 z.source_bbox_x_global+z.source_bbox_width_px,
                                 z.source_bbox_y_global+z.source_bbox_height_px),
                         COLORS["red"],2)
    save(ASSET_DIR/"07_J5_global_objects_cross_tile_merge.png",
         header(canvas,"J5 | GLOBAL OBJECTS AFTER TILE-SEAM RECONCILIATION",
                f"global candidates={len(defects)} | cross-tile objects={len(cross)} | cyan=all J5 source pixels; red=cross-tile objects"))

def create_object_preview(base, objects, color, title, subtitle, filename):
    canvas=base.copy()
    for obj in objects:
        draw_obj_on_preview(canvas,obj,color)
    save(ASSET_DIR/filename,header(canvas,title,subtitle))

def create_k8b_k8c_images(base, sources, brecords):
    canvas=base.copy()
    def k8b_color(r):
        return COLORS["cyan"] if int(r.get("source_A_fixed_overlap_px") or 0)>0 else COLORS["yellow"]
    draw_sources_on_preview(canvas,sources,brecords,k8b_color)
    counts=pd.Series([int(r.get("band_id",0)) for r in brecords]).value_counts().sort_index()
    band_text=" | ".join(f"B{int(k)}:{int(v)}" for k,v in counts.items())
    save(ASSET_DIR/"09_K8B_perband_B_source_candidates.png",
         header(canvas,"K8B | PER-BAND B-SOURCE CANDIDATES",
                f"all B source components={len(brecords)} | yellow=novel B source; cyan=overlaps fixed A source | {band_text}"))

    cls_colors={
        "PROMISING_DARK_REVIEW":COLORS["green"],
        "UNCERTAIN_REVIEW":COLORS["orange"],
        "BOUNDARY_REVIEW":COLORS["magenta"],
        "MICRO_REVIEW":COLORS["blue"],
        "MICRO_HIDE_SUGGESTION":COLORS["gray"],
        "EXISTING_FIXED_H":COLORS["cyan"],
    }
    canvas=base.copy()
    draw_sources_on_preview(canvas,sources,brecords,
        lambda r: cls_colors.get(str(r.get("classification")),COLORS["white"]))
    s=pd.Series([str(r.get("classification","UNCLASSIFIED")) for r in brecords]).value_counts()
    legend=" | ".join(f"{k}:{int(v)}" for k,v in s.items())
    save(ASSET_DIR/"10_K8C_RAW_evidence_classification.png",
         header(canvas,"K8C | RAW EVIDENCE CLASSIFICATION",
                f"all K8B components classified; {legend}"))

def create_k8d_image(raw, trials):
    stable=next((t for t in trials if str(t["reason"]).startswith("STABLE_")),None)
    censored=next((t for t in trials if str(t["reason"]).startswith("CENSORED_")),None)
    chosen=[("STABLE",stable),("CENSORED",censored)]
    panels=[]
    for label,t in chosen:
        if t is None:
            continue
        z=np.load(t["npz"],allow_pickle=False)
        x0,y0,x1,y1=map(int,z["bbox"])
        rc=np.asarray(raw[y0:y1,x0:x1],np.uint16)
        rawim=raw_crop_bgr(rc)
        seed=z["seed"];m3=z["raw_k3"];m2=z["raw_k2"];m15=z["raw_k1p5"];outer=z["outer"]
        status=str(t["reason"])
        masks=[
            (rawim,f"{label} | RAW + seed"),
            (overlay_binary(rawim,seed,COLORS["green"],0.85),"source seed"),
            (overlay_binary(rawim,m3,COLORS["cyan"],0.85),"3 MAD"),
            (overlay_binary(rawim,m2,COLORS["yellow"],0.85),"2 MAD"),
            (overlay_binary(rawim,m15,COLORS["orange"],0.85),"1.5 MAD"),
            (overlay_binary(rawim,outer,COLORS["magenta"],0.85),"K8D selected proposal"),
        ]
        for im,txt in masks:
            panels.append((im,f"{t['uid'].split(':')[-1]} | {txt}"))
    grid=panel_grid(panels,3,420,420)
    stable_name=stable["uid"] if stable else "none"
    censored_name=censored["uid"] if censored else "none"
    save(ASSET_DIR/"11_K8D_RAW_outer_stability_examples.png",
         header(grid,"K8D | RAW OUTER-ENVELOPE STABILITY",
                f"stable example={stable_name} | censored example={censored_name}; censored proposal is not adopted by fresh_b"))

def create_branch_fusion(base, j5_selected, b_selected):
    panels=[]
    for title,objects,color in [
        ("J5 main branch",j5_selected,COLORS["cyan"]),
        ("K8B-K8D supplement",b_selected,COLORS["orange"]),
        ("J5 + B before RAW Recovery",list(j5_selected)+list(b_selected),COLORS["green"])
    ]:
        c=base.copy()
        for z in objects:
            draw_obj_on_preview(c,z,color)
        panels.append((c,title+f" | n={len(objects)}"))
    grid=panel_grid(panels,3,590,480)
    save(ASSET_DIR/"12_J5_B_branch_fusion.png",
         header(grid,"J5 + B | AUTOMATIC BRANCH FUSION",
                "Same RAW coordinate system; separate branches are shown before Unified RAW Recovery"))

def create_recovery_image(raw, prior, recovered, audit):
    accepted=next((r for r in audit if bool(r.get("accepted"))),None)
    if accepted is None:
        raise RuntimeError("No accepted RAW Recovery example to illustrate")
    uids=set(str(accepted["source_uids"]).split(";"))
    parts=[z for z in prior if set(z["sources"]) & uids]
    if not parts:
        raise RuntimeError("Could not trace accepted recovery sources")
    seed,bb=old.combine(parts)
    outobj=next((z for z in recovered if set(z["sources"])==uids),None)
    if outobj is None:
        outobj=next((z for z in recovered if uids.issubset(set(z["sources"]))),None)
    if outobj is None:
        raise RuntimeError("Could not find recovered object")
    x0,y0,x1,y1=map(int,json.loads(accepted["roi"]))
    rawim=raw_crop_bgr(np.asarray(raw[y0:y1,x0:x1],np.uint16))
    source=np.zeros((y1-y0,x1-x0),bool)
    sx0,sy0,sx1,sy1=map(int,bb)
    source[sy0-y0:sy1-y0,sx0-x0:sx1-x0]=seed
    after=np.zeros_like(source)
    ox0,oy0,ox1,oy1=map(int,outobj["bbox"])
    after[oy0-y0:oy1-y0,ox0-x0:ox1-x0]=outobj["mask"]
    added=after&~source
    p1=overlay_binary(rawim,source,COLORS["green"],0.85)
    p2=rawim.copy()
    p2=overlay_binary(p2,source,COLORS["green"],0.82)
    p2=overlay_binary(p2,added,COLORS["orange"],0.88)
    panels=[(rawim,"RAW local ROI"),
            (p1,f"source union | {int(source.sum())} px"),
            (p2,f"recovered | {int(after.sum())} px | added {int(added.sum())}")]
    grid=panel_grid(panels,3,520,520)
    save(ASSET_DIR/"13_Unified_RAW_Recovery_before_after.png",
         header(grid,"UNIFIED RAW RECOVERY | ACCEPTED EXAMPLE",
                f"source UID count={len(uids)} | {int(accepted['prior_area_px2'])} → {int(accepted['final_area_px2'])} px² | accepted={accepted['reason']}"))

def create_consolidate_image(base, recovered, final, edges):
    pre=base.copy()
    for z in recovered:
        draw_obj_on_preview(pre,z,COLORS["orange"])
    post=base.copy()
    for z in final:
        draw_obj_on_preview(post,z,COLORS["green"])
    edge_types=pd.Series([e.get("type","") for e in edges]).value_counts().to_dict()
    panels=[(pre,f"before | {len(recovered)} objects"),
            (post,f"after | {len(final)} objects")]
    grid=panel_grid(panels,2,PREVIEW_W//2,PREVIEW_H//2)
    save(ASSET_DIR/"14_Consolidate_pixel_dedup.png",
         header(grid,"CONSOLIDATE | GLOBAL PIXEL-LEVEL DEDUPLICATION",
                f"overlap edges={len(edges)} | edge types={edge_types} | orange=pre-consolidation; green=final non-overlapping masks"))

def farthest_pair(mask):
    yy,xx=np.nonzero(mask)
    pts=np.column_stack([xx,yy]).astype(np.float32)
    hull=cv2.convexHull(pts).reshape(-1,2)
    if len(hull)<2:
        return (0,0),(0,0),0.0
    delta=hull[:,None,:]-hull[None,:,:]
    d2=np.sum(delta*delta,axis=2)
    i,j=np.unravel_index(np.argmax(d2),d2.shape)
    return tuple(hull[i]),tuple(hull[j]),float(np.sqrt(d2[i,j]))

def create_measurement_image(raw, final):
    obj=max(final,key=lambda z:int(np.asarray(z["mask"],bool).sum()))
    x0,y0,x1,y1=map(int,obj["bbox"])
    rc=np.asarray(raw[y0:y1,x0:x1],np.uint16)
    rawim=raw_crop_bgr(rc)
    mask=np.asarray(obj["mask"],bool)
    maskim=np.zeros((*mask.shape,3),np.uint8)
    maskim[mask]=(245,245,245)
    overlay=overlay_binary(rawim,mask,COLORS["green"],0.70)
    p1,p2,feret=farthest_pair(mask)
    cv2.line(overlay,(int(p1[0]),int(p1[1])),(int(p2[0]),int(p2[1])),COLORS["blue"],2,cv2.LINE_AA)
    cv2.rectangle(overlay,(0,0),(mask.shape[1]-1,mask.shape[0]-1),COLORS["red"],1)
    area=int(mask.sum())
    grade="LARGE"
    try:
        df=pd.read_csv(AUTO_RUN/"FINAL_DEFECTS_AND_MEASUREMENTS.csv",encoding="utf-8-sig")
        source_key=";".join(sorted(obj["sources"]))
        row=df.loc[df["source_uids"].astype(str)==source_key].iloc[0]
        grade=str(row["grade"])
        feret=float(row["max_Feret_detector_px"])
        label=str(row["final_ID"])
    except Exception:
        label="largest final object"
    panels=[(rawim,"RAW crop"),
            (maskim,f"exact binary mask | A={area} px²"),
            (overlay,f"{label} | L={feret:.2f} px | {grade}")]
    grid=panel_grid(panels,3,520,520)
    save(ASSET_DIR/"15_Final_mask_measurement_example.png",
         header(grid,"FINAL MASK | AREA AND MAXIMUM FERET MEASUREMENT",
                "Green=exact mask overlay; blue line=maximum-Feret point pair; red frame=exact object bounding box"))

def main():
    ASSET_DIR.mkdir(parents=True,exist_ok=True)
    raw=np.memmap(RAW_PATH,mode="r",dtype=">u2",shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
    saved_ids=read_image(SOURCE_RUN/"band_id_fullres.png",cv2.IMREAD_UNCHANGED)
    saved_types=read_image(SOURCE_RUN/"region_type_fullres.png",cv2.IMREAD_UNCHANGED)
    fused=np.load(SOURCE_RUN/"fused_blackhat.npy",mmap_mode="r")
    loc=locate_transmission_bands(raw,BandLocatorConfig())
    types,ids=rasterize_region_masks(raw.shape,loc["bands"],loc["exterior"],BandLocatorConfig())
    if saved_ids is None or not np.array_equal(ids,saved_ids):
        raise AssertionError("Recomputed K8A band IDs do not match the saved production run")
    if saved_types is None or not np.array_equal(types,saved_types):
        raise AssertionError("Recomputed K8A region types do not match the saved production run")
    base=make_base(raw)

    # Stage 1: original RAW input.
    save(ASSET_DIR/"01_RAW_input_26_1.png",
         header(base.copy(),"RAW INPUT | 26_1",
                f"{C.RAW_WIDTH} × {C.RAW_HEIGHT} | big-endian uint16 container | effective {C.EFFECTIVE_BITS}-bit | display stretch only"))

    # Stage 2: K8A work-band localization.
    ids_small=cv2.resize(ids,(PREVIEW_W,PREVIEW_H),interpolation=cv2.INTER_NEAREST)
    k8a=base.copy()
    maxid=int(ids.max())
    palette=[COLORS["yellow"],COLORS["green"],COLORS["cyan"],COLORS["magenta"],COLORS["orange"]]
    for bid in range(1,maxid+1):
        m=(ids_small==bid).astype(np.uint8)
        cnts,_=cv2.findContours(m,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        col=palette[(bid-1)%len(palette)]
        cv2.drawContours(k8a,cnts,-1,col,2,cv2.LINE_AA)
        yy,xx=np.where(m>0)
        if len(xx):
            cv2.putText(k8a,f"BAND {bid}",(int(np.median(xx))-35,int(np.median(yy))),
                        cv2.FONT_HERSHEY_SIMPLEX,0.55,col,2,cv2.LINE_AA)
    save(ASSET_DIR/"02_K8A_workband_localization.png",
         header(k8a,"K8A | AUTOMATIC TRANSMISSION WORK-BAND LOCALIZATION",
                f"detected bands={len(loc['bands'])} | only these WORK regions are eligible for defect reporting"))

    # Stage 3: Two-level ROI and original J4 grid schedule.
    plan=json.loads((SOURCE_RUN/"detection_plan.json").read_text(encoding="utf-8"))
    roi=base.copy()
    for t in plan["tiles"]:
        x0,y0,x1,y1=map(int,t["core_xyxy"])
        a=(int(x0*SX),int(y0*SY));b=(int((x1-1)*SX),int((y1-1)*SY))
        cv2.rectangle(roi,a,b,(95,95,95),1,cv2.LINE_8)
    for rect in plan["detection_rectangles"]:
        x0,y0,x1,y1=map(int,rect)
        cv2.rectangle(roi,(int(x0*SX),int(y0*SY)),(int((x1-1)*SX),int((y1-1)*SY)),COLORS["green"],2)
    save(ASSET_DIR/"03_TwoLevel_ROI_tile_schedule.png",
         header(roi,"TWO-LEVEL ROI | SAFE DETECTION REGION + J4 TILE GRID",
                f"scheduled tiles={len(plan['tiles'])}/{plan['full_tiles']} | skipped={plan['skipped_tiles']} | algorithm halo={plan['algorithm_halo_px']} px | review margin={plan['review_margin_px']} px"))

    # Stage 4: fused multi-scale Black-Hat response.
    sample=np.asarray(fused[::4,::4],np.float32)
    valid=sample<65535
    vals=sample[valid]
    lo=float(np.percentile(vals,35));hi=float(np.percentile(vals,99.7))
    if hi<=lo:hi=lo+1
    disp=np.zeros(sample.shape,np.uint8)
    disp[valid]=np.clip((sample[valid]-lo)*255/(hi-lo),0,255).astype(np.uint8)
    disp=cv2.resize(disp,(PREVIEW_W,PREVIEW_H),interpolation=cv2.INTER_AREA)
    heat=cv2.applyColorMap(disp,cv2.COLORMAP_TURBO)
    vsmall=cv2.resize(valid.astype(np.uint8),(PREVIEW_W,PREVIEW_H),interpolation=cv2.INTER_NEAREST)>0
    heat[~vsmall]=(30,30,30)
    save(ASSET_DIR/"04_ROI_multiscale_BlackHat_response.png",
         header(heat,"ROI BLACK-HAT | FIVE-SCALE FUSED DARK RESPONSE",
                "Actual fused uint16 response; display contrast stretched only for visualization; dark gray=uncomputed sentinel region"))

    j4dir=SOURCE_RUN/"upstream_J4/fresh"
    j5dir=SOURCE_RUN/"upstream_J5/fresh"
    create_j4_images(raw,fused,j4dir,base)
    create_j5_image(raw,base,j4dir,j5dir)

    # Rebuild production fresh branches without any historical approvals or negatives.
    j5_selected,jrecords=fresh_j5(raw,ids,j4dir,j5dir,FRAME)
    temp=Path(tempfile.mkdtemp(prefix="auto_report_figures_",dir=str(ASSET_DIR)))
    try:
        b_selected,brecords,sources=fresh_b(raw,fused,ids,loc,temp,FRAME)
        # Stage 7: actual fresh_j5 selection.
        j5area=sum(int(np.asarray(z["mask"],bool).sum()) for z in j5_selected)
        create_object_preview(base,j5_selected,COLORS["yellow"],"fresh_j5 | SELECTED J5 MAIN-BRANCH MASKS",
            f"selected objects={len(j5_selected)} | source mask area={j5area} px² | MEDIUM/LARGE + directional small scratches",
            "08_fresh_j5_selected_main_branch.png")

        # Stage 8 and 9: K8B source masks and K8C classifications.
        create_k8b_k8c_images(base,sources,brecords)

        # Stage 10: K8D RAW trials.
        trials=pd.read_csv(temp/"RAW_trials.csv",encoding="utf-8-sig")
        trial_records=trials.to_dict("records")
        # Use the freshly generated npz paths from the returned records (not stale paths).
        create_k8d_image(raw,trial_records)

        # Stage 11: automatic branch fusion before Unified RAW Recovery.
        create_branch_fusion(base,j5_selected,b_selected)

        # Stage 12: Unified RAW Recovery, with empty human-negative list.
        prior=list(j5_selected)+list(b_selected)
        recovered,recovery_audit=recover_objects(prior,raw,ids,[])
        pd.DataFrame(recovery_audit).to_csv(ASSET_DIR/"raw_recovery_stage_audit.csv",index=False,encoding="utf-8-sig")
        create_recovery_image(raw,prior,recovered,recovery_audit)

        # Stage 13: exact global pixel-level consolidation.
        final,edges=old.consolidate(list(recovered))
        create_consolidate_image(base,recovered,final,edges)

        # Stage 14: exact final mask measurement example.
        create_measurement_image(raw,final)

        # Verify the reconstructed no-history chain against the saved final output.
        saved=pd.read_csv(AUTO_RUN/"FINAL_DEFECTS_AND_MEASUREMENTS.csv",encoding="utf-8-sig")
        reconstructed_areas=sorted(int(np.asarray(z["mask"],bool).sum()) for z in final)
        saved_areas=sorted(saved["final_area_detector_px2"].astype(int).tolist())
        if reconstructed_areas!=saved_areas:
            raise AssertionError("Reconstructed final masks do not match saved no-history run")
        if len(final)!=len(saved) or sum(reconstructed_areas)!=int(saved["final_area_detector_px2"].sum()):
            raise AssertionError("Final object count/area mismatch")
        summary={
            "source_run":str(SOURCE_RUN),
            "no_history_run":str(AUTO_RUN),
            "raw_input":str(RAW_PATH),
            "j4_tiles":len(list((j4dir/"tile_masks").glob("*.npz"))),
            "j5_global_objects":len(pd.read_csv(j5dir/"global_defects.csv")),
            "fresh_j5_selected":len(j5_selected),
            "k8b_sources":len(brecords),
            "k8d_trials":len(trial_records),
            "raw_recovery_trials":len(recovery_audit),
            "raw_recovery_accepted":sum(bool(x.get("accepted")) for x in recovery_audit),
            "consolidate_before":len(recovered),
            "consolidate_after":len(final),
            "consolidate_edges":len(edges),
            "final_objects":len(final),
            "final_area_px2":sum(reconstructed_areas),
            "figures":[p.name for p in sorted(ASSET_DIR.glob("*.png"))],
            "verified_against_saved_final_csv":True,
            "historical_manual_approval_loaded":False,
            "historical_negative_loaded":False,
        }
        (ASSET_DIR/"figure_manifest.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
        # Copy the exact final production images from the pure-auto export.
        shutil.copy2(AUTO_RUN/"00_FINAL_DEFECTS_ONLY_fullframe_1to4.png",ASSET_DIR/"16_Final_1p5_display_boxes.png")
        shutil.copy2(AUTO_RUN/"01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK.png",ASSET_DIR/"17_Final_exact_binary_mask.png")
        summary["figures"]=[p.name for p in sorted(ASSET_DIR.glob("*.png"))]
        (ASSET_DIR/"figure_manifest.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(summary,ensure_ascii=False,indent=2))
    finally:
        shutil.rmtree(temp,ignore_errors=True)

if __name__=="__main__":
    main()
