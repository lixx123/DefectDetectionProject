"""Optional first-pass K review: 24 small candidates + 6 unpredicted ROIs.

One light sheet and a dedicated editable (blank-label) 30-row CSV, sourced
only from the pre-frozen 120 K0 examples. No model modification.
"""
from pathlib import Path
import numpy as np,pandas as pd,cv2,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_case03g_joint_noise_refinement import save_png

P=ROOT/"outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2"
df=pd.read_csv(P/"manual_review_template.csv",encoding="utf-8-sig",keep_default_na=False)
selected=[]
for band in ("A_1px2","B_2to3px2","C_4to7px2","D_8pluspx2"):
    selected.extend(df[df.area_group==band].head(6).sample_id.tolist())
selected.extend(df[df.sample_kind=="NO_J5_CANDIDATE_ROI"].head(6).sample_id.tolist())
if len(selected)!=30 or len(set(selected))!=30:raise ValueError("first pass selections corrupted")
dst=P/"first_pass_review_30.csv"
if dst.exists():raise FileExistsError(dst)
df.set_index("sample_id").loc[selected].reset_index().to_csv(dst,index=False,encoding="utf-8-sig")
cards=[]
for sid in selected:
    path=P/"cards"/(sid+".png")
    im=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    if im is None:raise OSError(path)
    cards.append(cv2.resize(im,(380,241),interpolation=cv2.INTER_AREA))
sheet=np.vstack([np.hstack(cards[i:i+5]) for i in range(0,30,5)])
png=P/"first_pass_review_30_contact.png"
if png.exists():raise FileExistsError(png)
save_png(png,sheet)
again=cv2.imdecode(np.frombuffer(png.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
assert again is not None and again.shape==sheet.shape
print("K0_FIRST_PASS_READY",dst,png,"items",len(selected),"shape",sheet.shape)
