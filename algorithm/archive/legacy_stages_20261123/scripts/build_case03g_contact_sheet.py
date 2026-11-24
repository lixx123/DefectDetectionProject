"""将十个Case03-G四栏对照图制作成一张总览图。只读取已生成PNG。"""
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/case03g_joint/run_20261010_10target_noise_refinement_v1"
input_dir=OUT/"figures_10_targets"
files=sorted(input_dir.glob("RAW26_MANUAL_*_four_panel.png"))
if len(files)!=10:
    raise RuntimeError(f"Expected 10 individual targets, got {len(files)}")
tiles=[]
for p in files:
    data=np.frombuffer(p.read_bytes(),dtype=np.uint8)
    im=cv2.imdecode(data,cv2.IMREAD_COLOR)
    if im is None or im.shape[1]!=1920 or im.shape[0]!=510:
        raise RuntimeError(f"invalid image {p}: "+str(im.shape if im is not None else None))
    tile=cv2.resize(im,(960,255),interpolation=cv2.INTER_AREA)
    tiles.append(tile)
sheet=np.vstack([np.hstack(tiles[i:i+2]) for i in range(0,10,2)])
ok,encoded=cv2.imencode(".png",sheet)
if not ok:raise RuntimeError("contact sheet PNG encode failed")
dest=OUT/"ten_target_overview.png"
if dest.exists():raise FileExistsError(dest)
dest.write_bytes(encoded.tobytes())
check=cv2.imdecode(np.frombuffer(dest.read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
assert check is not None and check.shape[:2]==(1275,1920)
print("CONTACT_SHEET",dest,"bytes",dest.stat().st_size)
