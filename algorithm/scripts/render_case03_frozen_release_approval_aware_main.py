"""Frozen release approval-aware fullframe view without hiding pending sources."""
from pathlib import Path
import sys,json,cv2,numpy as np,pandas as pd
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k8g_display_boxes import expand_bbox_xyxy,bbox_to_display_px
from scripts.run_case03k8g_1p5_display_boxes import write_lossless
OUT=C.OUTPUT_ROOT/"CASE03_FROZEN_RELEASE_20261019_v2"
U=C.OUTPUT_ROOT/"case03k8i_stage2_user_confirmed_reviews/run_20261017_F1_B02_B04_two_darkspots_v1"
F=C.OUTPUT_ROOT/"case03k8f_confirmed_group_register/run_20261014_F26_2_two_user_approved_G006_G009_v2"
FONT="C:/Windows/Fonts/msyh.ttc"
def decode(p):
 return cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
def main():
 allr=[]
 for fr in (1,2):
  fd=OUT/f"26_{fr}"
  original=fd/"08_FULLFRAME_WITH_STAGE2_ALL_NEW_RAW_GROUPS.png"
  im=decode(original)
  assert im is not None and im.shape==(C.RAW_HEIGHT//4+88,(C.RAW_WIDTH+3)//4,3)
  confirmed=[]
  if fr==1:
   rows=pd.read_csv(U/"two_user_confirmed_darkspots_no_duplicate_area.csv",
                    encoding="utf-8-sig")
   assert len(rows)==2
   for v in rows.itertuples():
    bbox=json.loads(v.RAW_bbox_xyxy_exclusive)
    assert v.user_confirmed_one_physical_darkspot and v.user_confirmed_outer_complete_and_accurate
    confirmed.append({"name":f"B{int(v.band_id):02d} CONFIRMED",
       "area":int(v.area_exact_union_detector_px2),
       "feret":float(v.longest_Feret_detector_image_um),
       "bbox":bbox,"sources":str(v.connected_B_source_labels),
       "approved_source_id":str(v.review_object_id)})
  else:
   ledger=pd.read_csv(F/"frame26_2/workband_unified_candidate_review_register.csv")
   for v in ledger[ledger.source=="K8F_USER_APPROVED_K8E_OUTER"].itertuples():
    assert v.visual_defect_confirmed_by_user
    confirmed.append({"name":str(v.supplement_K8E_group_id).split("_")[-1]+" CONFIRMED",
       "area":int(v.area_detector_px2),
       "feret":round(float(v.max_length_detector_px)*C.PIXEL_SIZE_UM,3),
       "bbox":[int(v.bbox_x0_global),int(v.bbox_y0_global),
               int(v.bbox_x1_exclusive_global),int(v.bbox_y1_exclusive_global)],
       "sources":str(v.source_B_connected_components),
       "approved_source_id":str(v.supplement_K8E_group_id)})
  assert len(confirmed)==2
  # Keep historical all pending boxes undisturbed, add approved outlines last.
  annot=Image.fromarray(cv2.cvtColor(im,cv2.COLOR_BGR2RGB))
  drawer=ImageDraw.Draw(annot)
  font=ImageFont.truetype(FONT,13)
  for v in confirmed:
   bbox=expand_bbox_xyxy(tuple(v["bbox"]),(C.RAW_WIDTH,C.RAW_HEIGHT),1.5)
   a,b,c,e=bbox_to_display_px(bbox,(C.RAW_WIDTH,C.RAW_HEIGHT),
                                (im.shape[1],im.shape[0]-88),4)
   # 1-pixel approval outline and copyable text label.
   drawer.rectangle((a,b+88,c,e+88),outline=(38,240,80),width=1)
   label=f"{v['name']} A={v['area']}px² L={v['feret']:.1f}μm(像面)"
   left=min(max(0,a),im.shape[1]-310)
   top=max(88,b+88-37)
   drawer.rectangle((left,top,left+309,top+30),fill=(18,22,24))
   drawer.text((left+4,top+5),label,font=font,fill=(197,255,206))
  # Add the explanation in an extra top banner. All raw pixel global positions
  # are preserved relative to previous image via 1:4 geometry and +88 shift.
  result=cv2.cvtColor(np.asarray(annot),cv2.COLOR_RGB2BGR)
  fname="00_LATEST_APPROVAL_AWARE_FULLFRAME_ALL_PENDING_PRESERVED.png"
  dest=fd/fname
  if dest.exists():raise FileExistsError(dest)
  write_lossless(dest,result)
  allr.append({"frame":fr,"approved_darkspots_added":2,
      "approved":confirmed,"base_fullframe_image":str(original),
      "new_display":str(dest),
      "not_hide_other_candidates":True,
      "all_original_masks_and_J5_B_source_ids_untouched":True,
      "grade_and_area_not_computed_from_expanded_display_bbox":True})
 state=OUT/"LATEST_APPROVAL_AWARE_MAIN_PNG_MANIFEST.json"
 if state.exists():raise FileExistsError(state)
 state.write_text(json.dumps({"stage":"FROZEN_CURRENT_APPROVAL_MAIN_PNG",
    "not_a_true_defect_detector_for_all_pending_candidates":True,
    "frames":allr},ensure_ascii=False,indent=2),encoding="utf-8")
 print("APPROVAL_AWARE_MAIN_TWO_FRAMES_COMPLETE",allr[0]["new_display"],allr[1]["new_display"],flush=True)
if __name__=="__main__":main()
