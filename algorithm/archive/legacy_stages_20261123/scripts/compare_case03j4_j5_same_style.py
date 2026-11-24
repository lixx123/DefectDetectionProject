"""Diagnostic: render J4 and J5 with *exactly the same* preview convention.

J4 standard preview did not draw SMALL. J5 all-sizes did.
This figure intentionally uses bbox-center for SMALL in both stages, 1px
radius at 1/8 original scale. It is a presentation-only comparison.
"""
from pathlib import Path
import sys
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from scripts.run_case03g_joint_noise_refinement import gray,save_png
from src.detection.case03i_size_grade import GRADE_COLORS_BGR

J4=cfg.OUTPUT_ROOT/"case03j4_fullframe/run_20261012_frame26_1_full_j4_v1"
J5=cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_1_global_j5_v1"
OUT=J5/"display_diagnostics_matching_style"
OUT.mkdir(parents=True,exist_ok=True)
raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
              shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
bg=gray(np.asarray(raw[::8,::8],np.uint16))
a=pd.read_csv(J4/"j4_unmerged_tile_objects.csv",encoding="utf-8-sig")
b=pd.read_csv(J5/"global_defects.csv",encoding="utf-8-sig")


def render(table:pd.DataFrame,phase:str,include_small:bool)->np.ndarray:
    result=bg.copy()
    gcol="size_grade" if phase=="J4" else "grade"
    count={k:int((table[gcol]==k).sum())
           for k in ("SMALL","MEDIUM","LARGE")}
    for o in table.itertuples(index=False):
        level=getattr(o,gcol)
        x0=int(o.display_bbox_x_global)//8
        y0=int(o.display_bbox_y_global)//8
        x1=int(o.display_bbox_xmax_inclusive)//8
        y1=int(o.display_bbox_ymax_inclusive)//8
        c=GRADE_COLORS_BGR[level]
        if level=="SMALL":
            if include_small:
                cx=int((o.display_bbox_x_global+
                       o.display_bbox_xmax_inclusive)/16)
                cy=int((o.display_bbox_y_global+
                       o.display_bbox_ymax_inclusive)/16)
                cv2.circle(result,(cx,cy),1,c,-1,cv2.LINE_8)
        else:
            cv2.rectangle(result,(x0,y0),(x1,y1),c,1,cv2.LINE_8)
    heading=(
        f"{phase} | SAME DISPLAY | "
        f"GREEN {count['SMALL']} YELLOW {count['MEDIUM']} RED {count['LARGE']}"
    )
    header=86
    out=cv2.copyMakeBorder(result,header,0,0,0,
                          cv2.BORDER_CONSTANT,value=(24,24,24))
    cv2.putText(out,heading,(10,28),cv2.FONT_HERSHEY_SIMPLEX,.48,
                (235,235,235),1,cv2.LINE_AA)
    cv2.putText(out,
                ("SMALL = green 1px dot at bbox center; "
                 "MEDIUM/LARGE = 1px bbox; same RAW gamma and scale"),
                (10,51),cv2.FONT_HERSHEY_SIMPLEX,.38,
                (216,216,216),1,cv2.LINE_AA)
    cv2.putText(out,
                "J4 unmerged local objects / J5 merged global candidates; "
                "neither is confirmed defect truth",
                (10,73),cv2.FONT_HERSHEY_SIMPLEX,.35,
                (207,207,207),1,cv2.LINE_AA)
    return out


for with_small,suffix in [(True,"all_sizes"),(False,"medium_large_only")]:
    pic4=render(a,"J4",with_small)
    pic5=render(b,"J5",with_small)
    assert pic4.shape==pic5.shape
    outputs=[
        (f"J4_{suffix}_same_style.png",pic4),
        (f"J5_{suffix}_same_style.png",pic5),
        (f"J4_vs_J5_{suffix}_side_by_side.png",np.hstack((pic4,pic5)))
    ]
    for fn,img in outputs:
        path=OUT/fn
        if path.exists():raise FileExistsError("refuse existing comparison "+str(path))
        save_png(path,img)
        decoded=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),
                             cv2.IMREAD_COLOR)
        assert decoded is not None and decoded.shape==img.shape
        print("VERIFIED",path.name,img.shape,path.stat().st_size,flush=True)
print("TOTAL_AREA_J4",int(a.source_area_px2.sum()),
      "TOTAL_AREA_J5",int(b.source_area_px2.sum()),flush=True)
