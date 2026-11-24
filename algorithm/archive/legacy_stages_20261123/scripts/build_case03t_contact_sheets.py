"""Case03-T read-only PNG atlas assembler for 18 ROI comparisons and 10 replays."""
from pathlib import Path
import cv2,numpy as np

ROOT=Path(__file__).resolve().parents[1]
DST=ROOT/"outputs/case03t_threshold_pilot/run_20261010_sample26_frame2_three_methods_v1"


def load(p:Path)->np.ndarray:
    img=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    if img is None:raise OSError(p)
    return img


def save(name:str,items:list[Path],cols:int,resize:(int,int))->None:
    if len(items)%cols: raise ValueError("items not divisible by columns")
    ims=[cv2.resize(load(p),resize,interpolation=cv2.INTER_AREA) for p in items]
    rows=[np.hstack(ims[i:i+cols]) for i in range(0,len(ims),cols)]
    dest=DST/name
    if dest.exists():raise FileExistsError(dest)
    out=np.vstack(rows)
    ok,payload=cv2.imencode(".png",out,[cv2.IMWRITE_PNG_COMPRESSION,4])
    if not ok: raise OSError("PNG encode failed")
    dest.write_bytes(payload.tobytes())
    verified=load(dest)
    if verified.shape!=out.shape:raise OSError("PNG size mismatch")
    print("WRITTEN",dest.name,verified.shape,dest.stat().st_size)


save("historical9_contact_sheet.png",
     sorted((DST/"figures_historical9").glob("*.png")),3,(1190,190))
save("spatial_controls9_contact_sheet.png",
     sorted((DST/"figures_controls9").glob("*.png")),3,(1190,190))
save("ten_position_replay_contact_sheet.png",
     sorted((DST/"figures_10_frame1_replay").glob("*.png")),2,(1176,168))
