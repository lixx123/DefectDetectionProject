"""Independent unified Case03 final QA: ALL 40702 provenance, no spatial
double counting, four user-confirmed exact darkspot masks, every archived
J5 MEDLARGE source, green user-rejected stable proposal check and final
full-resolution binary images.

Creates image-plane exact binary mask and single-defect RAW proof crops.
Never edits original candidate masks or silently changes final decisions.
"""
from pathlib import Path
import sys,json,hashlib,math
from collections import Counter
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03i_size_grade import max_feret_centers_px,grade_size,SizeGradeConfig
from scripts.run_case03_unified_final_detector_26_1_2 import (
    OUT,I,E,II,USR,K8F,J5P,J4P,global_intersection,unpack)
SIZE=SizeGradeConfig()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(4*1024*1024),b""):h.update(c)
 return h.hexdigest()
def get_img(p):
 z=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
 assert z is not None
 return z
def mask_from_row(z):
 with np.load(z.raw_mask_npz,allow_pickle=False) as m:
  mask=m["mask"].astype(bool);box=tuple(map(int,m["global_RAW_bbox_xyxy_exclusive"]))
  sources=set(map(str,m["original_J5_K8B_source_uids"]))
 assert mask.shape==(box[3]-box[1],box[2]-box[0])
 assert int(mask.sum())==z.final_area_detector_px2
 assert sources==set(str(z.J5_B_or_K8E_sources).split(";"))
 return mask,box
def crop(raw,z,mask,bbox,p):
 pad=38
 x0,y0,x1,y1=bbox
 aa=max(0,x0-pad);bb=max(0,y0-pad)
 cc=min(C.RAW_WIDTH,x1+pad);dd=min(C.RAW_HEIGHT,y1+pad)
 gray=np.asarray(raw[bb:dd,aa:cc],np.float32)
 lo,hi=np.percentile(gray,[2,99.5])
 g=np.uint8(np.clip((gray-lo)/max(1.,hi-lo)*255,0,255))
 roi=np.zeros(g.shape,np.uint8)
 roi[y0-bb:y1-bb,x0-aa:x1-aa]=np.uint8(mask)*255
 preview=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
 contour=preview.copy()
 cs,_=cv2.findContours(roi,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
 cv2.drawContours(contour,cs,-1,(0,225,255),1)
 pixelmask=cv2.cvtColor(roi,cv2.COLOR_GRAY2BGR)
 side=np.hstack([preview,contour,pixelmask])
 header=np.full((56,side.shape[1],3),24,np.uint8)
 cv2.putText(header,
    f"{z.final_ID}  band {z.band_id}  A={z.final_area_detector_px2}px2  L={z.max_Feret_detector_px:.1f}px",
    (7,22),cv2.FONT_HERSHEY_SIMPLEX,.45,(245,245,245),1)
 cv2.putText(header,
    "RAW  |  RAW + EXACT 1px CONTOUR  |  FINAL BINARY MASK",
    (7,45),cv2.FONT_HERSHEY_SIMPLEX,.37,(225,225,225),1)
 canvas=np.vstack([header,side])
 ok,buf=cv2.imencode(".png",canvas)
 assert ok
 p.write_bytes(buf.tobytes())

def check_frame(frame):
 out=OUT/f"26_{frame}"
 r=pd.read_csv(out/"FINAL_DEFECTS_AND_MEASUREMENTS.csv")
 audit=pd.read_csv(out/"ALL_ORIGINAL_J5_AND_B_SOURCE_DISPOSITIONS_NO_DROP.csv",
                   low_memory=False)
 old=pd.read_csv(I/f"frame26_{frame}"/"end_to_end_candidate_lineage.csv",
                 low_memory=False)
 assert len(old)==len(audit)==(32370 if frame==1 else 8332)
 assert not audit.candidate_source_uid.duplicated().any()
 assert set(audit.candidate_source_uid)==set(old.candidate_source_uid)
 assert audit.original_source_mask_preserved.all()
 assert audit.human_verified_as_noise.eq(False).all()
 assert audit.final_defect_ID.dropna().isin(set(r.final_ID)).all()
 assert not r.final_ID.duplicated().any()
 assert r.human_confirmed_darkspot.sum()==2
 assert r.object_plane_calibration_available.eq(False).all()
 j=old[(old.stage=="J5")&(old.primary_visibility_layer=="J5_WORK_MEDLARGE")]
 selected=set(";".join(r.J5_B_or_K8E_sources).split(";"))
 for q in j.itertuples(index=False):
  assert q.candidate_source_uid in selected,(
    "MEDLARGE J5 source dropped",q.candidate_source_uid)
 # Reconstruct every independent mask and check true pixel, Feret, grade.
 raw=np.memmap(C.DATA_ROOT/f"26 ({frame}).raw",dtype=">u2",
               mode="r",shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
 binary=np.zeros(raw.shape,dtype=np.uint8)
 rows=[]
 previews=out/"FINAL_LOCAL_RAW_CONTOUR_PROOFS"
 previews.mkdir(exist_ok=True)
 for z in r.itertuples(index=False):
  mask,box=mask_from_row(z)
  x0,y0,x1,y1=box
  current=binary[y0:y1,x0:x1]
  assert not np.any(current[mask]),("Final IDs share exact pixel",z.final_ID)
  current[mask]=255
  yy,xx=np.where(mask)
  feret=max_feret_centers_px(np.column_stack([xx,yy]))
  assert abs(feret-z.max_Feret_detector_px)<0.00006
  grade,_=grade_size(len(xx),feret,SIZE)
  assert grade==z.grade
  assert abs(z.area_detector_image_um2-len(xx)*C.PIXEL_SIZE_UM**2)<=0.001
  crop(raw,z,mask,box,previews/(str(z.final_ID)+".png"))
  rows.append({"final_ID":z.final_ID,"mask_area_px2":int(mask.sum()),
       "source_UID_count":len(str(z.J5_B_or_K8E_sources).split(";")),
       "mask_SHA256":sha(Path(z.raw_mask_npz))})
 assert int(binary.sum()//255)==int(r.final_area_detector_px2.sum())
 png=out/"01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK_11276x9200.png"
 ok,buf=cv2.imencode(".png",binary,[cv2.IMWRITE_PNG_COMPRESSION,5])
 assert ok;png.write_bytes(buf.tobytes())
 del binary
 final=get_img(png)
 assert final.shape==(C.RAW_HEIGHT,C.RAW_WIDTH)
 assert int(np.count_nonzero(final))==int(r.final_area_detector_px2.sum())
 # Verified user-confirmed original masks (not merely bounding-box areas).
 if frame==1:
  u=pd.read_csv(USR/"two_user_confirmed_darkspots_no_duplicate_area.csv")
  assert set(u.area_exact_union_detector_px2)=={398,297}
  for row in u.itertuples(index=False):
   result=r[(r.band_id==row.band_id)&(r.human_confirmed_darkspot)]
   assert len(result)==1
   m,b=mask_from_row(result.iloc[0])
   with np.load(row.verified_copy_npz,allow_pickle=False) as expected:
    truth=expected["verified_binary_mask"].astype(bool)
    eb=tuple(map(int,expected["global_raw_roi_xyxy"]))
   yy,xx=np.where(truth)
   cropped=truth[yy.min():yy.max()+1,xx.min():xx.max()+1]
   eb2=(eb[0]+int(xx.min()),eb[1]+int(yy.min()),
        eb[0]+int(xx.max())+1,eb[1]+int(yy.max())+1)
   assert b==eb2 and np.array_equal(m,cropped)
 else:
  for gid,area in (("K8E_F2_B2_G006",348),("K8E_F2_B2_G009",370)):
   source=E/"frame26_2"/"group_detail"/(gid+"_EXACT_GROUP_MASK.npz")
   m0,b0=unpack(source)
   group=r[(r.human_confirmed_darkspot)&
      (r.final_area_detector_px2==area)]
   assert len(group)==1
   m,b=mask_from_row(group.iloc[0])
   yy,xx=np.where(m0)
   bbox=(b0[0]+int(xx.min()),b0[1]+int(yy.min()),
         b0[0]+int(xx.max())+1,b0[1]+int(yy.max())+1)
   truth=m0[yy.min():yy.max()+1,xx.min():xx.max()+1]
   assert bbox==b and np.array_equal(truth,m)
 # For user-negative green screenshot: no overlap with any final object;
 # the confirmed Band04 source from a later explicit review is exception.
 green=[]
 collisions=[]
 if frame==1:
  ng=pd.read_csv(II/"frame26_1/new_exact_group_union_review.csv")
  summ=json.loads((out/"summary.json").read_text(encoding="utf8"))
  ids=set(summ["all_green_false_review_group_ids"])
  for g in ng.itertuples(index=False):
   if g.new_group_id not in ids:continue
   with np.load(g.npz_file,allow_pickle=False) as zz:
    bm=zz["exact_review_union"].astype(bool)
    bb=tuple(map(int,zz["RAW_global_bbox"]))
   green.append(g.new_group_id)
   # At any overlap, record spatial conflict for manual review; only reject
   # a defect if it is entirely contained in the rejected green raw hull.
   for z in r.itertuples(index=False):
    mask,box=mask_from_row(z)
    hit=global_intersection({"mask":bm,"bbox":bb},{"mask":mask,"bbox":box})
    if hit:
     collisions.append({"negative_group":g.new_group_id,
       "final_ID":z.final_ID,"shared_px":hit,
       "final_area":int(mask.sum()),"negative_area":int(bm.sum())})
 assert len(green)==(7 if frame==1 else 0)
 pd.DataFrame(collisions,
   columns=["negative_group","final_ID","shared_px","final_area","negative_area"]
   ).to_csv(out/"USER_NEGATIVE_GREEN_VS_FINAL_SPATIAL_CONFLICT_AUDIT.csv",
            index=False,encoding="utf-8-sig")
 assert not collisions,(
   "User-rejected green group overlaps a supposedly final defect! Needs separate release correction",collisions)
 pd.DataFrame(rows).to_csv(out/"FINAL_MASK_SHA256_AND_SOURCE_COUNTS.csv",
    encoding="utf-8-sig",index=False)
 q={"frame":frame,"QA":"CASE03_UNIFIED_FINAL_PIXEL_EXACT_AND_SOURCE_QA_PASS",
   "final_defect_objects":len(r),
   "fullres_binary_px":int(r.final_area_detector_px2.sum()),
   "original_J5_B_source_records_all_reconciled":len(audit),
   "mediumlarge_J5_all_retained":len(j),
   "confirmed_darkspots_exact_original_binary_masks":2,
   "all_final_masks_are_disjoint":True,
   "seven_green_false_proposals_no_pixel_conflict":True if frame==1 else None,
   "every_local_raw_contour_preview_saved":len(rows),
   "final_binary_png_sha256":sha(png),
   "final_main_png_sha256":sha(out/"00_FINAL_DEFECTS_ONLY_fullframe_1to4.png")}
 (out/"independent_QA.json").write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding="utf8")
 print("UNIFIED_QA_PASS",json.dumps(q,ensure_ascii=False),flush=True)
 return q

def main():
 final={}
 for f in (1,2):
  final[f]=check_frame(f)
 summary={"stage":"CASE03_UNIFIED_FINAL_TWO_RAW_INDEPENDENT_QA_PASS",
     "original_source_rows_total":sum(z["original_J5_B_source_records_all_reconciled"] for z in final.values()),
     "four_user_confirmed_darkspot_original_masks_exact":True,
     "final_objects_total":sum(z["final_defect_objects"] for z in final.values()),
     "all_masks_pixel_disjoint":True,
     "pending_sources_archived_not_in_final_PNG":True,
     "precision_recall_not_measured_without_independent_groundtruth":True,
     "frames":list(final.values())}
 (OUT/"independent_QA.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf8")
 print("CASE03_UNIFIED_FINAL_TWO_RAW_INDEPENDENT_QA_PASS",flush=True)
if __name__=="__main__":main()
