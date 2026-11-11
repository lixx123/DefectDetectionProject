"""Auditable side-by-side K8I stage2 RAW vs source and OR-union reference."""
from pathlib import Path
import sys,json
import numpy as np,cv2,pandas as pd
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts.run_case03k8g_1p5_display_boxes import write_lossless
from scripts.run_case03k8i_stage2_fullband_priority_contours import OUT,K8D

FONT="C:/Windows/Fonts/msyh.ttc"
def transform(srcmask,old,box):
 out=np.zeros((box[3]-box[1],box[2]-box[0]),bool)
 l=max(old[0],box[0]);t=max(old[1],box[1])
 r=min(old[2],box[2]);b=min(old[3],box[3])
 if l<r and t<b:
  out[t-box[1]:b-box[1],l-box[0]:r-box[0]] = srcmask[t-old[1]:b-old[1],l-old[0]:r-old[0]]
 return out
def line(img,mask,color):
 cs,_=cv2.findContours(np.uint8(mask),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
 cv2.drawContours(img,cs,-1,color,1,cv2.LINE_8)
def panel(pic,title,desc,scale=4):
 w,h=384,384
 pic=cv2.resize(pic,(w,h),interpolation=cv2.INTER_NEAREST)
 v=Image.fromarray(cv2.cvtColor(pic,cv2.COLOR_BGR2RGB))
 top=Image.new("RGB",(w,80),(23,25,27))
 p=ImageDraw.Draw(top)
 f1=ImageFont.truetype(FONT,15);f2=ImageFont.truetype(FONT,12)
 p.text((9,11),title,fill=(240,240,240),font=f1)
 p.text((9,43),desc,fill=(218,223,226),font=f2)
 out=Image.new("RGB",(w,h+80),(25,25,25))
 out.paste(top,(0,0));out.paste(v,(0,80))
 return cv2.cvtColor(np.asarray(out),cv2.COLOR_RGB2BGR)
def background(raw,box):
 x0,y0,x1,y1=box
 sample=np.asarray(raw[y0:y1,x0:x1],np.float32)
 l,h=np.percentile(sample,[1,99.5])
 return cv2.cvtColor(np.uint8(np.clip((sample-l)/max(1,h-l)*255,0,255)),cv2.COLOR_GRAY2BGR)
def create_b4():
 f=1
 folder=OUT/"frame26_1"
 groups=pd.read_csv(folder/"new_exact_group_union_review.csv")
 row=groups[groups.new_source_B_labels=="2424;2444;2504"].iloc[0]
 with np.load(row.npz_file,allow_pickle=False) as z:
  box=tuple(map(int,z["RAW_global_bbox"]))
  union=z["exact_review_union"].astype(bool)
 raw=np.memmap(C.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
 pic=background(raw,box)
 seeds=pic.copy();trialview=pic.copy();merge=pic.copy()
 props=[]
 palette=[(10,30,240),(200,30,210),(10,204,230)]
 for label,col in zip((2424,2444,2504),palette):
  p=folder/"band04"/f"F1_B4_C{label:05d}_full_RAW_trial.npz"
  with np.load(p,allow_pickle=False) as z:
   roi=tuple(map(int,z["RAW_roi_global_xyxy"]))
   seed=transform(z["original_B_source"].astype(bool),roi,box)
   outer=transform(z["new_full_RAW_review_outer"].astype(bool),roi,box)
  line(seeds,seed,col);line(trialview,outer,col)
  props.append(outer)
 assert np.array_equal(np.logical_or.reduce(props),union)
 line(merge,union,(32,222,48))
 im=np.hstack([
    panel(pic,"原RAW灰度","同一原像素区域，无标注"),
    panel(seeds,"三个原B候选源种子","B2424红、B2444紫、B2504青"),
    panel(trialview,"三个独立K8D外围","面积289 / 295 / 286 px²"),
    panel(merge,"精确OR并集外围","870累加 → 297 px²（待复核）")])
 name="05_B04_TRIPLE_RAW_sources_outer_exact_union_REVIEW.png"
 write_lossless(folder/name,im)
 print("K8I2_REVIEW_TRIPLE_CASE_READY",name,"shape",im.shape,flush=True)
def create_b2():
 folder=OUT/"frame26_1";pnew=folder/"band02"/"F1_B2_C01787_full_RAW_trial.npz"
 oldfile=K8D/"frame26_1"/"band02"/"F1_B2_C01902_K8D_all_masks.npz"
 with np.load(pnew,allow_pickle=False) as z:
  new=z["new_full_RAW_review_outer"].astype(bool)
  bnew=tuple(map(int,z["RAW_roi_global_xyxy"]))
  seed=z["original_B_source"].astype(bool)
 with np.load(oldfile,allow_pickle=False) as z:
  old=z["K8D_full_outer"].astype(bool)
  bold=tuple(map(int,z["raw_global_roi_xyxy"]))
 box=(min(bnew[0],bold[0]),min(bnew[1],bold[1]),
      max(bnew[2],bold[2]),max(bnew[3],bold[3]))
 a=transform(new,bnew,box)
 b=transform(old,bold,box)
 s=transform(seed,bnew,box)
 inter=int((a&b).sum());un=int((a|b).sum())
 raw=np.memmap(C.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
 base=background(raw,box)
 newpic=base.copy();oldpic=base.copy();combine=base.copy()
 line(newpic,s,(10,40,240));line(newpic,a,(16,225,235))
 line(oldpic,b,(42,217,45))
 line(combine,a,(16,225,235));line(combine,b,(45,215,39))
 im=np.hstack([
     panel(base,"原RAW区域","旧K8D B1902 与新B1787邻接"),
     panel(newpic,"新增B1787种子+外围","23 → 398 px²（待复核）"),
     panel(oldpic,"既有K8D B1902外围","旧提案398 px²，不更改"),
     panel(combine,"两外围重叠审查",f"重合{inter} px²，并集{un} px²；禁止重复计量")])
 name="06_B02_1787_vs_OLD_B1902_overlap_REVIEW.png"
 write_lossless(folder/name,im)
 print("K8I2_REVIEW_OVERLAP_CASE_READY",name,"intersection",inter,
       "union",un,"image_shape",im.shape,flush=True)
if __name__=="__main__":
 create_b4()
 create_b2()
