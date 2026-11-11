"""J4 vs J5: directly registered overlay of identically rendered full-frame previews.

Diagnostic, not a new segmentation output. No source file overwritten.
"""
from pathlib import Path
import numpy as np,cv2,json
ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/"outputs/case03j5_global/run_20261012_frame26_1_global_j5_v1/display_diagnostics_matching_style"
def read(n):
    p=folder/n
    a=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    if a is None:raise OSError(p)
    return a
j4=read("J4_all_sizes_same_style.png")
j5=read("J5_all_sizes_same_style.png")
assert j4.shape==j5.shape and j4.shape[0]>86
body_a=j4[86:].copy()
body_b=j5[86:].copy()
difference=np.any(body_a!=body_b,axis=-1)
base=cv2.cvtColor(cv2.cvtColor(body_a,cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
view=base.copy()
# Bright magenta pinpoints differing output markers in EXACT same (x,y) frame coordinates.
view[difference]=(210,40,244)
# Keep drawing 2x2 sample source landmarks unchanged for visual registration.
overlay=cv2.addWeighted(body_a,.5,body_b,.5,0)
out=[]
for name,img,subtitle in [
    ("J4_J5_50percent_coordinate_overlay.png",overlay,
     "50% J4 + 50% J5; identical RAW coordinate origin"),
    ("J4_J5_exact_pixel_differences_magenta.png",view,
     "MAGENTA: different rendered pixels; background from J4"),
]:
    header=np.full((76,img.shape[1],3),24,np.uint8)
    cv2.putText(header,subtitle,(12,26),cv2.FONT_HERSHEY_SIMPLEX,
                .48,(230,230,230),1,cv2.LINE_AA)
    cv2.putText(header,
      f"Image/body {img.shape[1]}x{img.shape[0]}px; disagreement {int(difference.sum())}/{difference.size} = {100*difference.mean():.4f}%",
      (12,52),cv2.FONT_HERSHEY_SIMPLEX,.43,(215,215,215),1,cv2.LINE_AA)
    final=np.vstack((header,img))
    dest=folder/name
    if dest.exists():raise FileExistsError(dest)
    ok,bytes_=cv2.imencode(".png",final)
    if not ok:raise OSError("PNG encoding error")
    dest.write_bytes(bytes_.tobytes())
    assert cv2.imdecode(np.frombuffer(dest.read_bytes(),np.uint8),1).shape==final.shape
    out.append(str(dest))
print(json.dumps({
"body_identical_pixel_fraction":round(1-difference.mean(),6),
"body_diff_pixel_count":int(difference.sum()),
"body_total_pixels":int(difference.size),
"raw_underlying_image_same":True,
"new_comparison_files":out},ensure_ascii=False,indent=2))
