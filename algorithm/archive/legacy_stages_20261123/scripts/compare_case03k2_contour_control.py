"""Case03-K2: check 074 outer-boundary hypothesis against 4 real micro
samples AND 19 visually judged noises before changing production rules.

Descriptive post-hoc, not independent. Never modify original J4/J5 masks.
"""
from pathlib import Path
import json,sys
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from scripts.run_case03g_joint_noise_refinement import save_png
S=cfg.OUTPUT_ROOT/"case03k_light_review/run_20261012_small_candidate_manual_review_v2"
OUT=S/"K2_contour_expansion_control_review_v1"
if OUT.exists():raise FileExistsError(OUT)
OUT.mkdir()
df=pd.read_csv(S/"revision_074_obvious_dark_spot_20261012/first_pass_review_30_labels_corrected.csv",encoding="utf-8-sig",keep_default_na=False)
df=df[df.sample_kind=="SMALL_CANDIDATE"].copy()
mem=pd.read_csv(cfg.OUTPUT_ROOT/
  "case03j5_global/run_20261012_frame26_1_global_j5_v1/global_object_membership.csv",
  encoding="utf-8-sig")
members=mem.groupby("global_defect_id")
rawmem=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
                 shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
J4=cfg.OUTPUT_ROOT/"case03j4_fullframe/run_20261012_frame26_1_full_j4_v1"
cache={}
def original_mask(record):
    x0,y0,x1,y1=(int(record[k]) for k in ("x0","y0","x1","y1"))
    dst=np.zeros((y1-y0,x1-x0),np.uint8)
    for r in members.get_group(str(record["global_defect_id"])).itertuples():
        name=str(r.source_tile_id)
        if name not in cache:
            with np.load(J4/"tile_masks"/(name+".npz")) as z:
                cache[name]=(
                    z["grouped_source_only_i32"].copy(),
                    tuple(int(v) for v in z["core_xyxy"])
                )
        labels,rect=cache[name]
        mx0=max(x0,rect[0]);my0=max(y0,rect[1])
        mx1=min(x1,rect[2]);my1=min(y1,rect[3])
        if mx1<=mx0 or my1<=my0:continue
        region=(labels[my0-rect[1]:my1-rect[1],
                       mx0-rect[0]:mx1-rect[0]]==int(r.source_local_object_index))
        dst[my0-y0:my1-y0,mx0-x0:mx1-x0]|=region.astype(np.uint8)
    if int(dst.sum())!=int(float(record["source_area_px2"])):
        raise AssertionError("original masked source mismatch "+str(record["sample_id"]))
    return dst.astype(bool)

def trial_one(record):
    x0,y0,x1,y1=(int(record[k]) for k in ("x0","y0","x1","y1"))
    image=np.asarray(rawmem[y0:y1,x0:x1],dtype=np.uint16)
    mask=original_mask(record)
    yy,xx=np.mgrid[:image.shape[0],:image.shape[1]]
    tx=int(float(record["target_x_global"]))-x0
    ty=int(float(record["target_y_global"]))-y0
    radius=np.hypot(xx-tx,yy-ty)
    smooth=cv2.GaussianBlur(image.astype(np.float32),(0,0),1.3)
    baseline=cv2.GaussianBlur(image.astype(np.float32),(0,0),20.)
    resid=baseline-smooth
    ann=resid[(radius>=30)&(radius<=48)]
    sigma=1.4826*float(np.median(np.abs(ann-np.median(ann))))
    peak=float(np.percentile(resid[radius<=9],99))
    outcome={
        "sample_id":record["sample_id"],
        "global_defect_id":record["global_defect_id"],
        "user_label":record["manual_candidate_label"],
        "original_area_px2":int(mask.sum()),
        "MAD_residual_sigma_DN":round(sigma,3),
        "peak_residual_DN":round(peak,3)
    }
    trial_masks={}
    for alpha in (.15,.25,.35,.50):
        cut=max(3*sigma,alpha*peak)
        foreground=(resid>=cut)&(radius<=34)
        n,lab,_,_=cv2.connectedComponentsWithStats(np.uint8(foreground),8)
        tally=np.bincount(lab[mask].ravel(),minlength=n)
        tally[0]=0
        best=int(tally.argmax())
        candidate=lab==best if best and tally[best]>0 else np.zeros(mask.shape,bool)
        trial_masks[alpha]=candidate
        outcome[f"candidate_area_alpha{int(alpha*100)}"]=int(candidate.sum())
        outcome[f"candidate_ratio_alpha{int(alpha*100)}"]=round(float(candidate.sum()/max(mask.sum(),1)),2)
        outcome[f"source_pixels_retained_alpha{int(alpha*100)}"]=int(np.count_nonzero(candidate & mask))
    return outcome,trial_masks,image,mask

results=[]
montage_cases={"K0_SMALL_053","K0_SMALL_054","K0_SMALL_073",
               "K0_SMALL_074","K0_SMALL_077","K0_SMALL_001",
               "K0_SMALL_028","K0_SMALL_049","K0_SMALL_075"}
cards=[]
for r in df.to_dict("records"):
    record,trial,image,old=trial_one(r)
    results.append(record)
    if r["sample_id"] in montage_cases:
        grayimage=np.uint8(np.clip((image.astype(np.float32)-np.percentile(image,1))/
           max(1,np.percentile(image,99.5)-np.percentile(image,1))*255,0,255))
        pane=cv2.cvtColor(grayimage,cv2.COLOR_GRAY2BGR)
        enhanced=pane.copy()
        for m,color in [(trial[.35],(70,205,220)),(old,(5,15,235))]:
            contour,_=cv2.findContours(np.uint8(m),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(enhanced,contour,-1,color,1)
        a=cv2.resize(pane,(256,256),interpolation=cv2.INTER_NEAREST)
        b=cv2.resize(enhanced,(256,256),interpolation=cv2.INTER_NEAREST)
        combined=np.hstack([a,b])
        title=np.full((50,512,3),26,np.uint8)
        cv2.putText(title,f'{r["sample_id"]} {r["manual_candidate_label"]}',
                   (8,22),cv2.FONT_HERSHEY_SIMPLEX,.43,(235,235,235),1)
        cv2.putText(title,f'Original area={old.sum()} / alpha35 area={trial[.35].sum()}',
                    (8,41),cv2.FONT_HERSHEY_SIMPLEX,.38,(210,210,210),1)
        cards.append(np.vstack((title,combined)))
table=pd.DataFrame(results)
table.to_csv(OUT/"all_first24_contour_trial_audit.csv",index=False,encoding="utf-8-sig")
if cards:
    while len(cards)%3:cards.append(np.full_like(cards[-1],26))
    mosaic=np.vstack([np.hstack(cards[i:i+3]) for i in range(0,len(cards),3)])
    save_png(OUT/"contour_trial_real_vs_noise_contact.png",mosaic)
stats=table.groupby("user_label").agg(
   n=("sample_id","size"),
   original_median_area=("original_area_px2","median"),
   alpha35_median_area=("candidate_area_alpha35","median"),
   alpha35_median_ratio=("candidate_ratio_alpha35","median"),
   alpha35_max_ratio=("candidate_ratio_alpha35","max"),
   peak_median_DN=("peak_residual_DN","median"),
)
stats.to_csv(OUT/"group_descriptive_statistics.csv",encoding="utf-8-sig")
summ={"status":"K2_DIAGNOSTIC_ONLY_NOT_APPROVED_FOR_PRODUCTION",
      "input_samples":len(table),
      "real_micro":int((table.user_label=="REAL_MICRO_DEFECT").sum()),
      "obvious_real_dark_spot":int((table.user_label=="REAL_OBVIOUS_DARK_SPOT").sum()),
      "noise":int((table.user_label=="BACKGROUND_NOISE").sum()),
      "candidate_contours_are_unvalidated_hypotheses":True,
      "reference_labels_used_for_posthoc_comparison_only":True,
      "no_parameters_changed":True}
(OUT/"summary.json").write_text(json.dumps(summ,ensure_ascii=False,indent=2),encoding="utf-8")
print("K2_BOUNDARY_CONTROL_TABLE")
print(table[["sample_id","user_label","original_area_px2",
   "candidate_area_alpha25","candidate_area_alpha35","candidate_area_alpha50"]].to_string(index=False))
print("K2_BOUNDARY_GROUP_STATS")
print(stats.to_string())
print("RESULT",json.dumps(summ,ensure_ascii=False))
