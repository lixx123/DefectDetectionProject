"""Case03-K2d causal factor isolation on RAW74.

Test original 5 black-hat kernels [3,5,9,15,31] versus adding 41/61/81/101,
while keeping H170/230; separately vary H thresholds keeping same 5 kernel
response. No downstream filter. All outputs are research hypotheses only,
never changes J4/J5 labels, original RAW, or original config.
"""
from pathlib import Path
import json,sys,cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.blackhat import black_hat_uint16
from scripts.run_case03g_joint_noise_refinement import save_png
BASE=cfg.OUTPUT_ROOT/"case03k_light_review/run_20261012_small_candidate_manual_review_v2"
SAVE=BASE/"K2d_074_blackhat_scale_vs_threshold_v1"
if SAVE.exists():raise FileExistsError(SAVE)
SAVE.mkdir()
source_path=BASE/"K2_obvious_spot_074_extent_diagnostic_v1/074_exact_trial_masks.npz"
with np.load(source_path) as d:
    source=d["source_J5_mask_uint8"]>0
    rect=[int(x) for x in d["roi_global_xyxy"]]
    raw128=d["raw_128_u16"].copy()
cx,cy=5699,5670
# 384px patch to avoid artificial boundaries of larger morphological closings.
patch=[cx-192,cy-192,cx+192,cy+192]
xx,yy,xxx,yyy=patch
img=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
              shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
raw=np.asarray(img[yy:yyy,xx:xxx],np.uint16)
sx,sy=rect[0]-xx,rect[1]-yy
yslice=slice(sy,sy+128);xslice=slice(sx,sx+128)
assert np.array_equal(raw[yslice,xslice],raw128)
original_fused=np.load(cfg.OUTPUT_ROOT/
    "case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy",
    mmap_mode="r")
actual=original_fused[rect[1]:rect[3],rect[0]:rect[2]]
ks=list(cfg.BLACKHAT_KERNEL_SIZES_PX)
assert ks==[3,5,9,15,31],ks
fused=np.zeros_like(raw,np.uint16)
response_by_k={}
for k in ks+[41,61,81,101]:
    current=black_hat_uint16(raw,k,cfg.BLACKHAT_KERNEL_SHAPE)
    response_by_k[k]=current
    if k in ks:np.maximum(fused,current,out=fused)
baseline=fused.copy()
fullmatch=np.array_equal(actual,baseline[yslice,xslice])
print("K2d_PRECOMPUTED_BLACKHAT_MATCH",fullmatch,
      "maxabs",int(np.abs(actual.astype(np.int32)-
                          baseline[yslice,xslice].astype(np.int32)).max()),flush=True)
if not fullmatch:raise ValueError("refuse to compare non-equivalent BlackHat source")

# Baseline object is EXACT 24px. Morphological hyst count all component seeds.
J=np.zeros(raw.shape,bool)
J[yslice,xslice]=source
def evaluated(name,arr,low,high):
    lowb=arr>=low;highb=arr>=high
    n,labels,stats,_=cv2.connectedComponentsWithStats(
        np.uint8(lowb),connectivity=8)
    seed_ids=np.unique(labels[highb])
    seed_ids=seed_ids[seed_ids>0]
    whole=np.isin(labels,seed_ids)
    # need one H component which actually intersects the original core,
    # not all nearby independent noise.
    overlap=np.bincount(labels[J],minlength=n)
    overlap[0]=0
    target_id=int(overlap.argmax())
    if not target_id or target_id not in seed_ids:
        region=np.zeros(raw.shape,bool)
    else:
        region=(labels==target_id)
    cut=region[yslice,xslice]
    yc,xc=np.nonzero(cut)
    original_source_inside=int((cut&source).sum())
    result={
      "trial":name,
      "low_threshold_DN":low,"high_threshold_DN":high,
      "n_seeded_H_components_on_patch":int(len(seed_ids)),
      "target_connected_H_pixels_in_128ROI":int(cut.sum()),
      "source_H24_retained_pixels":original_source_inside,
      "target_total_component_pixels_patch":int(region.sum()),
      "target_blackhat_peak_dn":int(arr[yslice,xslice][source].max()),
      "max_response_dn_in_128ROI":int(arr[yslice,xslice].max()),
      "bbox_xywh_global":None,
      "source_all_original_masks_unchanged":True
    }
    if len(xc):
        result["bbox_xywh_global"]=[
            int(xc.min()+rect[0]),int(yc.min()+rect[1]),
            int(np.ptp(xc)+1),int(np.ptp(yc)+1)]
    return result,cut

trials=[]
trials_images=[]
base8=raw128.astype(float)
lo,hi=np.percentile(base8,[1,99.5])
eight=np.uint8(np.clip((base8-lo)/max(hi-lo,1)*255,0,255))
def panel(info,mask):
    a=cv2.cvtColor(eight,cv2.COLOR_GRAY2BGR)
    if mask.any():
        tint=a.copy();tint[mask]=(50,215,228)
        a=cv2.addWeighted(a,.75,tint,.25,0)
        contours,_=cv2.findContours(np.uint8(mask),cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(a,contours,-1,(20,220,250),1)
    orig,_=cv2.findContours(np.uint8(source),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(a,orig,-1,(0,0,255),1)
    image=cv2.resize(a,(360,360),interpolation=cv2.INTER_NEAREST)
    banner=np.full((56,360,3),25,np.uint8)
    cv2.putText(banner,info["trial"],(8,25),cv2.FONT_HERSHEY_SIMPLEX,.50,
                (235,235,235),1)
    cv2.putText(banner,
        f"ROI area {info['target_connected_H_pixels_in_128ROI']}px, peak {info['target_blackhat_peak_dn']}",
        (8,45),cv2.FONT_HERSHEY_SIMPLEX,.38,(211,211,211),1)
    return np.vstack((banner,image))

def add(name,arr,lo,hi):
    record,m=evaluated(name,arr,lo,hi)
    trials.append(record);trials_images.append(panel(record,m))
add("baseline max31 H170/230",baseline,170,230)
for k in (41,61,81,101):
    np.maximum(fused,response_by_k[k],out=fused)
    add(f"max to {k} H170/230",fused,170,230)
for low,high in [(150,230),(130,230),(150,210),(130,200),
                 (110,180)]:
    add(f"max31 H{low}/{high}",baseline,low,high)
# Individual kernel responses expose scale response changes independent of fuse.
for k in (15,31,41,61,81,101):
    vals=response_by_k[k][yslice,xslice]
    trials.append({
       "trial":f"individual_blackhat_{k}_source24_response",
       "low_threshold_DN":None,"high_threshold_DN":None,
       "n_seeded_H_components_on_patch":None,
       "target_connected_H_pixels_in_128ROI":None,
       "source_H24_retained_pixels":None,
       "target_total_component_pixels_patch":None,
       "target_blackhat_peak_dn":int(vals[source].max()),
       "max_response_dn_in_128ROI":int(vals.max()),
       "bbox_xywh_global":None,
       "source_all_original_masks_unchanged":True
    })
while len(trials_images)%5:
    trials_images.append(np.full_like(trials_images[-1],25))
view=np.vstack([np.hstack(trials_images[i:i+5]) for i in range(0,len(trials_images),5)])
png=SAVE/"074_blackhat_kernel_vs_H_threshold_comparison.png"
save_png(png,view)
dataframe=pd.DataFrame(trials)
dataframe.to_csv(SAVE/"factor_ablation_audit.csv",index=False,encoding="utf-8-sig")
rec=json.loads(dataframe.to_json(orient="records"))
summary={
   "baseline_response_exact_case02_fullframe":fullmatch,
   "original_kernels":ks,
   "added_kernels":[41,61,81,101],
   "source_seed_pixels":24,
   "user_verified_edge":False,
   "no_production_parameter_changed":True,
   "meaning":"Object support in 128px ROI from pre-postfilter H hysteresis; not physically validated contour.",
   "trials":rec
}
(SAVE/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print("K2d_074_ABLATION",dataframe[[
    "trial","target_connected_H_pixels_in_128ROI","target_blackhat_peak_dn",
    "n_seeded_H_components_on_patch","bbox_xywh_global"]].to_string(index=False),flush=True)
print("K2d_OUTPUT",str(SAVE),flush=True)
