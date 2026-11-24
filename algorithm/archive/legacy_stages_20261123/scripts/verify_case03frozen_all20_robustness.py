"""Independent actual 20 RAW robustness verification and contact sheet QA.

This report records ONLY frozen K8A/B/C screening, NOT all J5/K8D/E replay.
Never tunes thresholds based on unreviewed candidate counts.
"""
from pathlib import Path
from collections import Counter
import sys,json,hashlib,statistics,math
import numpy as np,pandas as pd,cv2
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts.run_case03frozen_all20_robustness import OUT,inputs
from src.detection.case03i_size_grade import SizeGradeConfig,grade_size
from scripts.run_case03g_joint_noise_refinement import save_png
FONT=Path("C:/Windows/Fonts/msyh.ttc")
def load(path):
 im=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
 if im is None:raise IOError(path)
 return im
def audit():
 allin=inputs()
 report=json.loads((OUT/"summary.json").read_text(encoding="utf-8"))
 assert len(allin)==len(report["frames"])==20
 assert report["frames_pass"]==20 and report["frames_fail"]==report["frames_not_yet_run"]==0
 events=[]
 sampled=[]
 for spec in allin:
  folder=OUT/spec["uid"]
  status=json.loads((folder/"status.json").read_text(encoding="utf-8"))
  assert status["status"]=="PASS"
  assert not status["K8D_all_source_RAW_outer_executed"]
  assert status["new_user_confirmed_defect_count"]==0
  assert status["all_B_sources_preserved"]
  rids=load(folder/"K8A_band_id_fullres.png")
  types=load(folder/"K8A_region_type_fullres.png")
  assert rids.shape==types.shape==(C.RAW_HEIGHT,C.RAW_WIDTH)
  assert np.array_equal(rids>0,types==2)
  assert set(np.unique(rids))==set(range(0,status["band_count"]+1))
  # Avoid converting a 9200x11276 band array into a giant Python list.
  del rids,types
  zones=pd.read_csv(folder/"BANDWISE_SCREENING_SUMMARY.csv")
  tab=pd.read_csv(folder/"ALL_B_SOURCE_CANDIDATE_LEDGER.csv",
                  encoding="utf-8-sig",low_memory=False)
  assert len(zones)==status["band_count"]==4
  assert set(zones.band_id)=={1,2,3,4}
  assert len(tab)==status["B_all_source_object_count"]
  assert tab.candidate_source_uid.nunique()==len(tab)
  assert tab.visibility_layer.ne("").all()
  assert tab.K8D_raw_outer_status.eq(
      "UNPROCESSED_OUT_OF_ROBUSTNESS_K8A_B_C_SCOPE").all()
  assert set(tab.classification)==set(status["class_counts"])
  assert dict(Counter(tab.classification))==status["class_counts"]
  total_area=0
  for row in zones.itertuples(index=False):
   band=int(row.band_id)
   bdir=folder/f"band{band:02d}"
   a=load(bdir/"A_fixed170_230_source_pixels.png")
   b=load(bdir/"B_adaptive_SOURCE_UNALTERED.png")
   strong=load(bdir/"K8C_STRONG_RAW_DARK_PENDING.png")
   review=load(bdir/"K8C_REVIEW_OTHER_SOURCES.png")
   micro=load(bdir/"K8C_MICRO_SUGGEST_HIDE_NOT_DELETED.png")
   assert a.shape==b.shape==strong.shape==review.shape==micro.shape
   assert a.shape[1]==C.RAW_WIDTH
   assert all(set(np.unique(x)).issubset({0,255}) for x in (a,b,strong,review,micro))
   assert np.array_equal((strong|review|micro),b)
   assert not np.any((strong&review)|(strong&micro)|(micro&review))
   assert int(b.astype(bool).sum())==row.B_mask_px
   assert int(a.astype(bool).sum())==row.A_mask_px
   assert int(np.count_nonzero((a>0)&(b==0)))==row.A_fixed_pixels_not_selected_by_B_adaptive
   src=tab[tab.band_id==band]
   n,labels,st,ctr=cv2.connectedComponentsWithStats((b>0).astype(np.uint8),8)
   assert n-1==len(src)==row.B_source_components
   assert set(src.band_component_label)==set(range(1,n))
   for o in src.itertuples(index=False):
    if int(st[o.band_component_label,cv2.CC_STAT_AREA])!=int(o.candidate_area_px2):
      raise AssertionError("Exact component area differs "+spec["uid"])
   assert sum(map(int,src.candidate_area_px2))==int(row.B_mask_px)
   assert dict(Counter(src.classification))==json.loads(row.K8C_class_counts.replace("'",'"'))
   total_area+=int(row.B_mask_px)
  assert total_area==status["all_B_source_pixel_count"]
  for name in ("B_ALL","B_STRONG","B_REVIEW","B_MICRO"):
   img=load(folder/(name+"_wholeframe_1to8.png"))
   assert img.shape==(1150,1410,3) or img.shape==(1150,1409,3) or img.shape[:2]==(1150,1410)
  if spec["sample_id"]==26 and spec["frame_id"] in (1,2):
   assert status["K8A_baseline_26_1_2_bitexact"]
   assert status["K8B_original_26_1_2_bitexact"]
   assert status["K8C_original_26_1_2_count_and_class_exact"]
   assert len(tab)==(16766 if spec["frame_id"]==1 else 3892)
  events.append({
    "sample_id":spec["sample_id"],"frame_id":spec["frame_id"],
    "RAW":spec["file"],"bands_auto_detected":status["band_count"],
    "K8A_B_C_source_integrity":"PASS","original_J5_K8A_B_C_replay_26_1_2":
      "BIT_EXACT" if spec["sample_id"]==26 and spec["frame_id"] in (1,2) else "NOT_HISTORICALLY_TESTED",
    "B_candidate_source_objects":len(tab),
    "B_source_pixels":total_area,
    "micro_suggest_hide_without_deletion":int(status["class_counts"].get("MICRO_HIDE_SUGGESTION",0)),
    "strong_dark_pending_candidates":int(status["class_counts"].get("PROMISING_DARK_REVIEW",0)),
    "uncertain_review_candidates":int(status["class_counts"].get("UNCERTAIN_REVIEW",0)),
    "candidate_COUNT_is_not_defect_truth":True,
    "J4_J5_fullprocess":"FROZEN_PRIOR" if spec["sample_id"]==26 and spec["frame_id"] in (1,2) else "NOT_RUN",
    "K8D_E_fullprocess":"PARTIAL_PRIOR" if spec["sample_id"]==26 and spec["frame_id"] in (1,2) else "NOT_RUN",
    "RAW_20_sample_blind_truth_precision_recall":"NOT_MEASURED"})
  print("ROBUST20_QA_FRAME_PASS",spec["uid"],"B",len(tab),
        "candidate_px",total_area,flush=True)
 df=pd.DataFrame(events)
 df.to_csv(OUT/"INDEPENDENT_20_FRAME_PIXEL_SOURCE_AUDIT.csv",index=False,encoding="utf-8-sig")
 vals=np.asarray(df.B_candidate_source_objects,dtype=float)
 median=np.median(vals)
 sig=max(1,1.4826*np.median(np.abs(vals-median)))
 df["candidate_count_robust_deviation_Z"]=(vals-median)/sig
 df["requires_background_noise_distribution_review"]=(
     abs(df.candidate_count_robust_deviation_Z)>=2)
 df.to_csv(OUT/"ROBUSTNESS_COUNT_OUTLIER_REVIEW_ONLY.csv",index=False,encoding="utf-8-sig")
 qs=sorted(df.B_candidate_source_objects.tolist())
 summary={
   "stage":"ALL_20_RAW_K8A_K8B_K8C_INDEPENDENT_PIXEL_AUDIT_PASS",
   "inputs_total":20,"pass_count":20,"fail_count":0,
   "complete_J4_J5_K8D_K8E_All20":False,
   "all_user_confirmations_stay_only_on_originals":True,
   "bands_count_all_frames":dict(Counter(df.bands_auto_detected)),
   "B_source_objects_all20_total":int(vals.sum()),
   "B_source_objects_min":int(vals.min()),
   "B_source_objects_median":float(median),
   "B_source_objects_max":int(vals.max()),
   "B_source_objects_max_min_ratio":round(float(vals.max()/vals.min()),2),
   "K8C_micro_suggest_hide_source_total_not_deleted":
         int(df.micro_suggest_hide_without_deletion.sum()),
   "K8C_strong_raw_support_pending_total":
         int(df.strong_dark_pending_candidates.sum()),
   "count_robust_z_threshold_alert_only":2.,
   "frames_with_count_alert":df.loc[df.requires_background_noise_distribution_review,
                   ["sample_id","frame_id","B_candidate_source_objects"]].to_dict("records"),
   "not_truth_precision_recall":True,
   "cannot_accept_20_full_pipeline":True}
 (OUT/"independent_QA.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
 print("ROBUST20_FINAL_INDEPENDENT_QA_PASS",json.dumps(summary,ensure_ascii=False),flush=True)
 return df,summary

def contact_sheet(df):
    for key,filename in [
        ("RAW_WORKBAND","work_band_overlay_on_RAW.png"),
        ("ALL_B","B_ALL_wholeframe_1to8.png"),
        ("K8C_PROMISING_PENDING","B_STRONG_wholeframe_1to8.png"),
        ("K8C_MICRO_SUGGEST_HIDE","B_MICRO_wholeframe_1to8.png")
    ]:
        w,h=690,570
        canvas=Image.new("RGB",(w*4,h*5),(24,25,27))
        painter=ImageDraw.Draw(canvas)
        f=ImageFont.truetype(str(FONT),17)
        for n,row in df.iterrows():
            uid=f"{int(row.sample_id)}_{int(row.frame_id)}"
            if key=="RAW_WORKBAND":
                image_path=OUT/uid/filename
            else:image_path=OUT/uid/filename
            b=cv2.imread(str(image_path),cv2.IMREAD_COLOR)
            if b is None:
                b=cv2.imdecode(np.frombuffer(image_path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
            assert b is not None
            scale=min(w/b.shape[1],(h-56)/b.shape[0])
            iw=int(b.shape[1]*scale);ih=int(b.shape[0]*scale)
            b=cv2.resize(b,(iw,ih),interpolation=cv2.INTER_AREA)
            pil=Image.fromarray(cv2.cvtColor(b,cv2.COLOR_BGR2RGB))
            x=(n%4)*w;y=(n//4)*h
            canvas.paste(pil,(x+(w-iw)//2,y+48))
            painter.text((x+9,y+4),
                f"{uid}  WORK={row.bands_auto_detected}   B={row.B_candidate_source_objects}",
                font=f,fill=(244,244,244))
        out=OUT/("20_RAW_"+key+"_CONTACT_SHEET_5samples_x_4frames.png")
        canvas.save(out,optimize=True)
        print("ROBUST20_CONTACT_SHEET",out.name,out.stat().st_size,flush=True)

if __name__=="__main__":
 df,_=audit()
 contact_sheet(df)
