"""Case03 unified FINAL detector: exact J5 masks + K8A/B/C + K8D/E + approvals.

Only final defects on main PNG; all source candidates conserved in ledger.
No claims of validated precision/recall. Frozen thresholds and source masks
are read-only, pending is never a main-map category.
"""
from pathlib import Path
import sys,json,math,hashlib,traceback
from collections import defaultdict,Counter
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03i_size_grade import SizeGradeConfig,grade_size,max_feret_centers_px
from src.detection.case03k8g_display_boxes import expand_bbox_xyxy,bbox_to_display_px
from scripts.run_case03g_joint_noise_refinement import save_png,gray
BASE=C.OUTPUT_ROOT
I=BASE/"case03k8i_full_frame_lineage/run_20261015_sample26_2frames_fullcandidate_lineage_v1"
K8B=BASE/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
E=BASE/"case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1"
II=BASE/"case03k8i_stage2_RAW_review_and_association/run_20261017_twoframes_priority_evidence_v1"
USR=BASE/"case03k8i_stage2_user_confirmed_reviews/run_20261017_F1_B02_B04_two_darkspots_v1"
K8F=BASE/"case03k8f_confirmed_group_register/run_20261014_F26_2_two_user_approved_G006_G009_v2"
OUT=BASE/"CASE03_UNIFIED_FINAL_DETECTOR_26_1_26_2_20261019_v2"
J4P={1:BASE/"case03j4_fullframe/run_20261012_frame26_1_full_j4_v1",
     2:BASE/"case03j4_fullframe/run_20261012_frame26_2_J4_independent_v1"}
J5P={1:BASE/"case03j5_global/run_20261012_frame26_1_global_j5_v1",
     2:BASE/"case03j5_global/run_20261012_frame26_2_J5_independent_v1"}
SIZE=SizeGradeConfig()
MIN_J5_SCRATCH_LENGTH=C.UNIFIED_FINAL['min_j5_scratch_length_px']
MIN_B_SOURCE_MEDIUM_AREA=C.UNIFIED_FINAL['min_b_source_area_px2']
MAX_UNRELIABLE_RAW_EXPANSION_RATIO=C.UNIFIED_FINAL['max_raw_growth_ratio']
def unpack(path,mkey="review_outer",bkey="roi_xyxy"):
 with np.load(path,allow_pickle=False) as z:
  m=z[mkey].astype(bool);b=tuple(map(int,z[bkey]))
 assert m.shape==(b[3]-b[1],b[2]-b[0])
 return m,b
def tight(m,b):
 ys,xs=np.where(m)
 assert len(xs)
 box=(b[0]+int(xs.min()),b[1]+int(ys.min()),
      b[0]+int(xs.max())+1,b[1]+int(ys.max())+1)
 return m[ys.min():ys.max()+1,xs.min():xs.max()+1],box
def global_intersection(a,b):
 x0=max(a["bbox"][0],b["bbox"][0]);y0=max(a["bbox"][1],b["bbox"][1])
 x1=min(a["bbox"][2],b["bbox"][2]);y1=min(a["bbox"][3],b["bbox"][3])
 if x1<=x0 or y1<=y0:return 0
 ax0,ay0,_,_=a["bbox"];bx0,by0,_,_=b["bbox"]
 return int(np.count_nonzero(
   a["mask"][y0-ay0:y1-ay0,x0-ax0:x1-ax0]&
   b["mask"][y0-by0:y1-by0,x0-bx0:x1-bx0]))
def combine(items):
 x0=min(z["bbox"][0] for z in items);y0=min(z["bbox"][1] for z in items)
 x1=max(z["bbox"][2] for z in items);y1=max(z["bbox"][3] for z in items)
 m=np.zeros((y1-y0,x1-x0),bool)
 for z in items:
  a,b,c,d=z["bbox"]
  m[b-y0:d-y0,a-x0:c-x0]|=z["mask"]
 return tight(m,(x0,y0,x1,y1))
def item(m,b,kind,src,band,approval=False,reason="",priority=1):
 mask,bbox=tight(m,b)
 return {"mask":mask,"bbox":bbox,"kind":kind,"sources":set(src),
         "band":int(band),"user_approved":approval,"reason":reason,
         "priority":priority}
def build_j5(frame,rows,cache):
 med=rows[(rows.stage=="J5")&(rows.primary_visibility_layer=="J5_WORK_MEDLARGE")]
 small=rows[(rows.stage=="J5")&(rows.primary_visibility_layer=="J5_WORK_SMALL")]
 protective=small[(small.source_max_Feret_px>=MIN_J5_SCRATCH_LENGTH)&
            (((small.source_bbox_x1_exclusive-small.source_bbox_x0)/
             (small.source_bbox_y1_exclusive-small.source_bbox_y0).clip(lower=1)>=1.6) |
             ((small.source_bbox_y1_exclusive-small.source_bbox_y0)/
             (small.source_bbox_x1_exclusive-small.source_bbox_x0).clip(lower=1)>=1.6))]
 sel=pd.concat([med,protective]).drop_duplicates("candidate_source_uid")
 membership=pd.read_csv(J5P[frame]/"global_object_membership.csv")
 grouped=membership.groupby("global_defect_id",sort=False)
 results=[]
 for z in sel.itertuples(index=False):
  relevant=grouped.get_group(str(z.source_local_id))
  items=[];read_area=0
  for mem in relevant.itertuples(index=False):
   tile=str(mem.source_tile_id)
   if tile not in cache:
    p=J4P[frame]/"tile_masks"/(tile+".npz")
    with np.load(p,allow_pickle=False) as data:
     cache[tile]=(data["grouped_source_only_i32"],tuple(map(int,data["core_xyxy"])))
   matrix,bbox=cache[tile]
   mask=(matrix==int(mem.source_local_object_index))
   found=int(mask.sum())
   if found!=int(mem.source_area_px2):
    raise AssertionError("J4 source mask mismatch "+z.candidate_source_uid)
   if found:
    items.append({"mask":mask,"bbox":bbox});read_area+=found
  mask,bbox=combine(items)
  if int(mask.sum())!=int(z.source_area_px2) or read_area!=int(z.source_area_px2):
   raise AssertionError("J5 source area mismatch "+z.candidate_source_uid)
  results.append(item(mask,bbox,
    "J5_SIZE_MEDLARGE" if str(z.size_grade)!="SMALL" else "J5_DIRECTIONAL_SMALL_SCRATCH",
    [z.candidate_source_uid],z.band_id,False,
    "J4_H_SEEDED_GAUSSIAN_CLOSING_F_G_H_J1_J2_J5_SOURCE_EXACT",3))
 print("UNIFIED_J5_LOADED",frame,"mediumlarge",len(med),"protected_small",len(protective),flush=True)
 return results
def build_b(frame,allrows):
 b=allrows[allrows.stage=="K8B"].copy()
 b["source_local_id"]=b.source_local_id.astype(int)
 index={(int(z.band_id),int(z.source_local_id)):z for z in b.itertuples(index=False)}
 bsummary=json.loads((K8B/f"frame26_{frame}"/"summary.json").read_text(encoding="utf8"))
 byband={int(z["band_id"]):int(z["ROI_global_xyxy"][1]) for z in bsummary["ROI_crops"]}
 grids={}
 def seed_of(band,label):
  if band not in grids:
   path=K8B/f"frame26_{frame}"/f"band_{band:02d}_B_hysteresis_mask_cropped.png"
   x=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_GRAYSCALE)
   grids[band]=cv2.connectedComponentsWithStats(np.uint8(x>0),connectivity=8,ltype=cv2.CV_32S)
  n,labels,stats,center=grids[band]
  if label<=0 or label>=n:raise IndexError((band,label))
  a,b,w,h,area=map(int,stats[label])
  mask=labels[b:b+h,a:a+w]==label
  return mask,(a,b+byband[band],a+w,b+h+byband[band])
 legacy=pd.read_csv(E/f"frame26_{frame}"/"K8E_unique_group_union_measurements.csv")
 new=pd.read_csv(II/f"frame26_{frame}"/"new_exact_group_union_review.csv")
 approved={}
 if frame==1:
  a=pd.read_csv(USR/"two_user_confirmed_darkspots_no_duplicate_area.csv")
  for z in a.itertuples(index=False):
   approved[str(z.canonical_old_K8E_group_id) if z.band_id==2 else
            str(z.crosschecked_new_K8I2_group_id)]=z
 else:
  for group in ("K8E_F2_B2_G006","K8E_F2_B2_G009"):
   approved[group]=None
 # Green proposals user rejected: reconstruct precise IDs by archived script's
 # visual policy, then ensure they are not introduced under separate B source.
 newtrial=pd.read_csv(II/f"frame26_{frame}"/"new_evidence_RAW_trial_results.csv")
 green_rejected=set()
 for z in new.itertuples(index=False):
  labels=[int(x) for x in str(z.new_source_B_labels).split(";")]
  m=newtrial[(newtrial.band_id==z.band_id)&newtrial.B_label.isin(labels)]
  stable=(len(m)==len(labels) and len(m)>0 and
          m.stage2_review_status.astype(str).str.startswith("STABLE_").all())
  if (stable and str(z.old_K8D_B_mask_overlap_json)=="[]" and frame==1 and str(z.new_group_id) not in approved):
   green_rejected.add(str(z.new_group_id))
 result=[];src_to_main={}
 for z in legacy.itertuples(index=False):
  band=int(z.band_id)
  labs=[int(x) for x in str(z.selected_B_labels).split(";")]
  src=[index[(band,x)] for x in labs]
  source_area=sum(int(q.source_area_px2) for q in src)
  conf=z.group_id in approved
  if not conf and (source_area<MIN_B_SOURCE_MEDIUM_AREA or
      any(str(q.K8C_noise_review_classification) in ("BOUNDARY_REVIEW","MICRO_HIDE_SUGGESTION")
          for q in src)):
   continue
  m,bbox=unpack(E/f"frame26_{frame}"/"group_detail"/
                (str(z.group_id)+"_EXACT_GROUP_MASK.npz"))
  if conf:
   reason="USER_CONFIRMED_K8E_OUTER"
  elif str(z.review_status)=="RAW_SAFETY_UNRESOLVED" or (
        int(m.sum())>MAX_UNRELIABLE_RAW_EXPANSION_RATIO*source_area):
   seeds=[item(*seed_of(band,x),"B_SOURCE",[],band) for x in labs]
   m,bbox=combine(seeds)
   reason="LARGE_SOURCE_RAW_SAFETY_OR_GROWTH_FALLBACK"
  else:
   reason="LARGE_RAW_STABLE_OR_ASSOCIATED_EXACT_OUTER"
  # Only explicitly user-confirmed physical groups can absorb embedded
  # source B fragments; never infer that for a generic K8E proposal.
  if conf and str(z.embedded_B_labels_TO_REVIEW).strip() not in ("","nan","None"):
   labs=sorted(set(labs+[int(float(x)) for x in str(z.embedded_B_labels_TO_REVIEW).split(";") if x.strip()]))
  ids=[index[(band,x)].candidate_source_uid for x in labs]
  result.append(item(m,bbox,"B_K8E_GROUP",ids,band,conf,
                     reason,4 if conf else 2))
  for uid in ids:src_to_main[uid]=str(z.group_id)
 # New user-confirmed Band04 3 B fragments exact union, never prior old E.
 if frame==1:
  c=approved["K8I2_F1_B04_G0096"]
  m,bbox=unpack(Path(c.verified_copy_npz),
                 "verified_binary_mask","global_raw_roi_xyxy")
  labs=[2424,2444,2504]
  result.append(item(m,bbox,"B_K8I2_USER_CONFIRMED_OR",
             [index[(4,x)].candidate_source_uid for x in labs],
             4,True,"USER_CONFIRMED_3_B_EXACT_PIXEL_OR",5))
 # New big *original source* supplemental objects, never enlarge solely from
 # large suspicious stability halo; green proposals user judged nondefects.
 banned=set()
 for z in new.itertuples(index=False):
  if str(z.new_group_id) in green_rejected:
   banned.update((int(z.band_id),int(x)) for x in str(z.new_source_B_labels).split(";"))
 claimed={uid for it in result for uid in it["sources"]}
 for z in b.itertuples(index=False):
  if z.candidate_source_uid in claimed:continue
  if (int(z.band_id),int(z.source_local_id)) in banned:continue
  if (str(z.size_grade) not in ("MEDIUM","LARGE") or
     int(z.source_area_px2)<MIN_B_SOURCE_MEDIUM_AREA):continue
  if str(z.K8C_noise_review_classification) not in (
       "PROMISING_DARK_REVIEW","UNCERTAIN_REVIEW"):continue
  m,bbox=seed_of(int(z.band_id),int(z.source_local_id))
  result.append(item(m,bbox,"B_NOVEL_MEDLARGE_SOURCE_ONLY",
            [z.candidate_source_uid],z.band_id,False,
            "SOURCE_AREA_MEDLARGE_RAW_NO_UNJUSTIFIED_EXPANSION",1))
 print("UNIFIED_B_LOADED",frame,"objects",len(result),
        "negative_green_proposal_group_ids",sorted(green_rejected),
        "user_approved",len(approved),flush=True)
 return result,green_rejected
def consolidate(objects):
 # Global pixel-precise dedup, never derive identity merely from box proximity.
 # Approved regions first: if overlapping source regions, exact union
 # prevents any double-counted pixels.
 objects.sort(key=lambda z:(not z["user_approved"],-z["priority"],-int(z["mask"].sum())))
 parent=list(range(len(objects)))
 def find(i):
  while parent[i]!=i:
   parent[i]=parent[parent[i]];i=parent[i]
  return i
 def union(a,b):
  a=find(a);b=find(b)
  if a!=b:parent[b]=a
 edges=[]
 for i,a in enumerate(objects):
  for j in range(i+1,len(objects)):
   b=objects[j]
   if a["band"]!=b["band"]:continue
   k=global_intersection(a,b)
   if k==0:continue
   amin=min(int(a["mask"].sum()),int(b["mask"].sum()))
   # Merge likely shared defect only with sufficient actual source overlap.
   if k>=3 and k/amin>=.25:
    union(i,j);edges.append({"a":i,"b":j,"overlap_px":k,
                              "type":"PIXEL_TRUE_ASSOCIATION"})
   else:
    edges.append({"a":i,"b":j,"overlap_px":k,
                              "type":"PIXEL_PARTIAL_CONFLICT_NOT_AUTO_MERGED"})
 groups=defaultdict(list)
 for i,v in enumerate(objects):groups[find(i)].append(v)
 out=[]
 for parts in groups.values():
  m,b=combine(parts)
  out.append(item(m,b,"UNIFIED_SAME_OBJECT_OR" if len(parts)>1 else parts[0]["kind"],
                  set().union(*(it["sources"] for it in parts)),
                  parts[0]["band"],any(it["user_approved"] for it in parts),
                  ";".join(sorted({z["reason"] for z in parts})),
                  max(z["priority"] for z in parts)))
  out[-1]["component_count"]=len(parts)
 # Weak partial conflicts: deterministic source pixel owner by priority.
 out.sort(key=lambda v:(not v["user_approved"],-v["priority"],-int(v["mask"].sum())))
 covered={}
 final=[]
 for obj in out:
  m=obj["mask"].copy();x0,y0,x1,y1=obj["bbox"]
  for previous in final:
   a,b,c,d=previous["bbox"]
   x=max(a,x0);y=max(b,y0);xx=min(c,x1);yy=min(d,y1)
   if xx>x and yy>y:
    cut=previous["mask"][y-b:yy-b,x-a:xx-a]
    m[y-y0:yy-y0,x-x0:xx-x0]&=~cut
  if np.any(m):
   m,bb=tight(m,obj["bbox"])
   obj["mask"]=m;obj["bbox"]=bb
   final.append(obj)
  else:
   # No final region left; source lineage and duplicate relationship remain
   # in the independently written ledger, never "lost" as candidate.
   pass
 return final,edges
def draw_contours(im,mask,bbox,color,factor=4,top=90):
 x0,y0,x1,y1=bbox
 cnts,_=cv2.findContours(mask.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
 for c in cnts:
  if len(c)<2:continue
  p=c.reshape(-1,2)+np.array([x0,y0])
  p[:,0]//=factor;p[:,1]=p[:,1]//factor+top
  cv2.polylines(im,[p.astype(np.int32)],True,color,1,lineType=cv2.LINE_8)
def main_frame(fr):
 out=OUT/f"26_{fr}"
 if out.exists():raise FileExistsError("Never overwrite existing FINAL "+str(out))
 out.mkdir(parents=True)
 try:
  lineage=pd.read_csv(I/f"frame26_{fr}"/"end_to_end_candidate_lineage.csv",low_memory=False)
  assert len(lineage)==(32370 if fr==1 else 8332)
  cache={}
  allitems=build_j5(fr,lineage,cache)
  bs,green=build_b(fr,lineage)
  allitems.extend(bs)
  final,edges=consolidate(allitems)
  assert final and sum(z["user_approved"] for z in final)==2
  records=[];lineage_selected={}
  compact=[]
  raw=np.memmap(C.DATA_ROOT/f"26 ({fr}).raw",dtype=">u2",mode="r",
                shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
  view=gray(np.asarray(raw[::4,::4],np.uint16))
  hdr=np.zeros((90,view.shape[1],3),np.uint8)
  hdr[:]=(25,25,25)
  cv2.putText(hdr,f"CASE03 UNIFIED FINAL DEFECTS | RAW 26 ({fr}) | NO PENDING BOXES",
     (10,28),cv2.FONT_HERSHEY_SIMPLEX,.57,(235,235,235),1)
  image=np.vstack([hdr,view])
  stable_source_area=sum(int(v.source_area_px2) for v in lineage.itertuples(index=False))
  for i,rec in enumerate(final,1):
   y,x=np.where(rec["mask"])
   box=rec["bbox"]
   full=np.column_stack((x,y))
   area=len(x)
   feret=float(max_feret_centers_px(full))
   grade,graderule=grade_size(area,feret,SIZE)
   uid=f"F{fr}_FINAL_{i:04d}"
   path=out/"EXACT_FINAL_BINARY_MASKS"/(uid+".npz")
   path.parent.mkdir(parents=True,exist_ok=True)
   np.savez_compressed(path,mask=np.uint8(rec["mask"]),
          global_RAW_bbox_xyxy_exclusive=np.int32(box),
          original_J5_K8B_source_uids=np.array(sorted(rec["sources"]),dtype="U90"))
   center=(float(box[0]+x.mean()),float(box[1]+y.mean()))
   r={"final_ID":uid,"frame":fr,"band_id":rec["band"],
      "final_area_detector_px2":area,"max_Feret_detector_px":round(feret,4),
      "area_detector_image_um2":round(area*C.PIXEL_SIZE_UM**2,3),
      "max_Feret_detector_image_um":round(feret*C.PIXEL_SIZE_UM,3),
      "grade":grade,"grade_rule":graderule,
      "bbox_xyxy_exclusive":json.dumps(box),
      "center_xy":json.dumps([round(v,3) for v in center]),
      "origin_stage":rec["kind"],"acceptance_reason":rec["reason"],
      "human_confirmed_darkspot":bool(rec["user_approved"]),
      "J5_B_or_K8E_sources":";".join(sorted(rec["sources"])),
      "raw_mask_npz":str(path),
      "pixel_exact_area_not_expanded_display_box":True,
      "object_plane_calibration_available":False,
      "user_human_confirmed_all_final_objects":False}
   records.append(r)
   for suid in rec["sources"]:
    if suid in lineage_selected:
     raise AssertionError("Same source assigned to more than one final "+suid)
    lineage_selected[suid]=uid
   col=(45,221,72) if rec["user_approved"] else (
      (51,85,235) if grade=="LARGE" else (40,215,240))
   draw_contours(image,rec["mask"],box,col)
   bb=expand_bbox_xyxy(box,(C.RAW_WIDTH,C.RAW_HEIGHT),1.5)
   a,b,c,d=bbox_to_display_px(bb,(C.RAW_WIDTH,C.RAW_HEIGHT),
                              (view.shape[1],view.shape[0]),4)
   cv2.rectangle(image,(a,b+90),(c,d+90),col,1,cv2.LINE_8)
   txt=f"{uid}:A{area} L{feret:.0f} {grade[0]}"
   cv2.putText(image,txt,(min(a,image.shape[1]-245),max(105,b+87)),
        cv2.FONT_HERSHEY_SIMPLEX,.28,col,1,cv2.LINE_8)
  save_png(out/"00_FINAL_DEFECTS_ONLY_fullframe_1to4.png",image)
  df=pd.DataFrame(records)
  df.to_csv(out/"FINAL_DEFECTS_AND_MEASUREMENTS.csv",
            index=False,encoding="utf-8-sig")
  # All original J5/B labels, even if excluded from final, have explicit,
  # readable fates. Suggested noise is not falsely human verified.
  audit=[]
  for v in lineage.itertuples(index=False):
   chosen=lineage_selected.get(v.candidate_source_uid)
   if chosen:
    status="FINAL_DEFECT_OR_PIXEL_MERGED"
    reason="SOURCE_REFERENCED_BY_EXACT_FINAL_MASK"
   elif v.stage=="J5" and v.band_id==0:
    status="EXCLUDED_FROM_FINAL_ARCHIVED_NONWORK"
    reason="K8A_EXTERIOR_SOURCE_KEPT"
   elif v.stage=="J5":
    status="EXCLUDED_FROM_FINAL_ARCHIVED_SMALL"
    reason="SOURCE_BELOW_MEDIUM_GRADE_AND_NOT_LONG_DIRECTIONAL_PROTECTED"
   elif v.K8C_noise_review_classification=="MICRO_HIDE_SUGGESTION":
    status="ALGORITHM_NOISE_SUGGEST_EXCLUDED_SOURCE_RETAINED"
    reason="K8C_LOCAL_RAW_MAD_DoG_MICRO_HINT_NOT_USER_NEGATIVE_LABEL"
   elif v.K8C_noise_review_classification=="EXISTING_FIXED_H":
    status="DUPLICATE_FIXED_H_REFERENCE_ARCHIVED"
    reason="B_OVERLAPS_FIXED_H_SOURCE_REFERENCE_NOT_INDEPENDENT"
   else:
    status="EXCLUDED_LOW_EVIDENCE_SOURCE_RETAINED"
    reason="DID_NOT_PASS_SIZE_RAW_OR_STREAK_FINAL_FUSION"
   audit.append({
      "candidate_source_uid":v.candidate_source_uid,
      "stage":v.stage,"band_id":v.band_id,
      "source_area_px2":v.source_area_px2,
      "original_visibility_layer":v.primary_visibility_layer,
      "K8C_class":v.K8C_noise_review_classification,
      "final_disposition":status,
      "final_defect_ID":chosen or "",
      "reason":reason,
      "original_source_mask_preserved":True,
      "human_verified_as_noise":False})
  aud=pd.DataFrame(audit)
  assert len(aud)==len(lineage) and aud.candidate_source_uid.is_unique
  aud.to_csv(out/"ALL_ORIGINAL_J5_AND_B_SOURCE_DISPOSITIONS_NO_DROP.csv",
             index=False,encoding="utf-8-sig")
  pd.DataFrame(edges).to_csv(out/"J5_B_K8E_EXACT_PIXEL_OVERLAP_EDGES.csv",
             index=False,encoding="utf-8-sig")
  summary={"status":"COMPLETE_WITH_EXPLICIT_SCOPE",
   "frame":fr,"pipeline":"RAW->J4_Hseed_Gaussian_Closing_FGH_J1J2->J5;K8A->K8B->K8C->K8D/E->Unify",
   "all_frozen_source_components":len(lineage),
   "final_total_defect_objects":len(final),
   "final_human_verified_darkspots":sum(v["human_confirmed_darkspot"] for v in records),
   "all_original_candidate_disposition_written":True,
   "all_J5_B_sources_immutable":True,
   "green_stable_visual_false_candidates_skipped":len(green) if fr==1 else 0,
   "all_green_false_review_group_ids":sorted(green),
   "no_pending_or_noise_overlay_on_final_main":True,
   "final_source_mask_overlaps_between_distinct_final_IDs":False,
   "no_manual_precision_recall_claim":True,
   "detector_plane_not_object_plane_um":True,
   "parameters":{"min_B_original_medium_area_px":MIN_B_SOURCE_MEDIUM_AREA,
     "max_unreliable_RAW_expansion_ratio":MAX_UNRELIABLE_RAW_EXPANSION_RATIO,
     "min_J5_protected_directional_small_length_px":MIN_J5_SCRATCH_LENGTH,
     "J5_grade_policy":"original_J5_MEDIUM_OR_LARGE","no_parameter_change_to_original_J4J5":True}}
  (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),
                                   encoding="utf8")
  print("UNIFIED_FINAL_COMPLETE",fr,"final",len(final),"user_approved",summary["final_human_verified_darkspots"],
        "source_audit",len(audit),"edge_evidence",len(edges),flush=True)
 except Exception as e:
  (out/"FAIL_IN_PROGRESS.json").write_text(json.dumps(
     {"error":str(e),"traceback":traceback.format_exc()},ensure_ascii=False,indent=2),
     encoding="utf8")
  raise
def main():
 if OUT.exists():raise FileExistsError("Release would overwrite "+str(OUT))
 OUT.mkdir(parents=True)
 for f in (1,2):main_frame(f)
 print("CASE03_UNIFIED_FINAL_2FRAMES_READY",OUT,flush=True)
if __name__=="__main__":main()
