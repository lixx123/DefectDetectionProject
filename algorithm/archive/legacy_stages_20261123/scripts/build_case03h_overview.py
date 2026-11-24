"""Build ten target contact sheet from existing per-target Case03-H PNG files."""
from pathlib import Path
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/"outputs/case03h_texture/run_20261010_10target_texture_dog_guard_v3"
pictures=sorted((folder/"figures_10_targets").glob("RAW26_MANUAL_*_5panel.png"))
if len(pictures)!=10:raise RuntimeError("Expected exactly ten example PNG files")
tiles=[]
for p in pictures:
    im=cv2.imdecode(np.frombuffer(p.read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
    if im is None or im.shape[:2]!=(510,2400):
        raise RuntimeError(f"invalid image {p.name}: "+str(im.shape if im is not None else None))
    tiles.append(cv2.resize(im,(1200,255),interpolation=cv2.INTER_AREA))
sheet=np.vstack([np.hstack(tiles[i:i+2]) for i in range(0,10,2)])
out=folder/"ten_target_overview_5panel.png"
if out.exists():raise FileExistsError("Refuse overwrite "+str(out))
ok,encoded=cv2.imencode(".png",sheet)
if not ok:raise RuntimeError("PNG encoding failed")
out.write_bytes(encoded.tobytes())
check=cv2.imdecode(np.frombuffer(out.read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
assert check is not None and check.shape[:2]==(1275,2400)
print("VERIFY",out.name,check.shape,out.stat().st_size,"bytes")
