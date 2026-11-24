"""Export two strictly disjoint presentation views of frozen Case03-J5.

1) medium_large_main.png: only medium (yellow) and large (red) candidate boxes.
2) small_reference.png: only SMALL green candidate marks for human reference.

Both use the exact same sampled RAW background and 1:8 pixel-to-preview
transform, and preserve exact frozen global IDs in complete CSV exports.
This is display-only; original masks, classifier and grade thresholds are
never changed. Output directory is append-only / no overwrite.
"""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from scripts.run_case03g_joint_noise_refinement import gray,save_png
from src.detection.case03i_size_grade import GRADE_COLORS_BGR

J5=cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_1_global_j5_v1"
OUT=J5/"separate_size_views_v1"
STRIDE=8
HEADER=86


def draw_base(raw,df:pd.DataFrame,grade_set:frozenset[str],caption:str):
    pic=gray(np.asarray(raw[::STRIDE,::STRIDE],dtype=np.uint16))
    for row in df.itertuples(index=False):
        if row.grade not in grade_set:continue
        color=GRADE_COLORS_BGR[row.grade]
        if row.grade=="SMALL":
            # Bounding-box center is a display marker, not a source pixel mask.
            x=int((int(row.display_bbox_x_global)+
                   int(row.display_bbox_xmax_inclusive))//(2*STRIDE))
            y=int((int(row.display_bbox_y_global)+
                   int(row.display_bbox_ymax_inclusive))//(2*STRIDE))
            cv2.circle(pic,(x,y),1,color,-1,cv2.LINE_8)
        else:
            x0=int(row.display_bbox_x_global)//STRIDE
            y0=int(row.display_bbox_y_global)//STRIDE
            x1=int(row.display_bbox_xmax_inclusive)//STRIDE
            y1=int(row.display_bbox_ymax_inclusive)//STRIDE
            cv2.rectangle(pic,(x0,y0),(x1,y1),color,1,cv2.LINE_8)
    image=cv2.copyMakeBorder(pic,HEADER,0,0,0,cv2.BORDER_CONSTANT,
                            value=(24,24,24))
    cv2.putText(image,"26 FRAME 1 / CASE03-J5 / "+caption,(12,27),
                cv2.FONT_HERSHEY_SIMPLEX,.56,(239,239,239),1,cv2.LINE_AA)
    cv2.putText(image,
       "Same RAW background / origin(0,0) / scale 1:8 / detector pixels",
       (12,51),cv2.FONT_HERSHEY_SIMPLEX,.41,
       (217,217,217),1,cv2.LINE_AA)
    cv2.putText(image,
       "Candidate objects are unverified; size color is not defect confidence",
       (12,73),cv2.FONT_HERSHEY_SIMPLEX,.37,
       (205,205,205),1,cv2.LINE_AA)
    return image


def run(dest:Path=OUT)->dict:
    if dest.exists():raise FileExistsError("refusing to overwrite "+str(dest))
    dest.mkdir(parents=True)
    status=json.loads((J5/"summary.json").read_text(encoding="utf-8"))
    if status.get("stage")!="J5_COMPLETE":raise ValueError("source J5 incomplete")
    df=pd.read_csv(J5/"global_defects.csv",encoding="utf-8-sig")
    if len(df)!=status["global_candidate_objects"] or df.global_defect_id.duplicated().any():
        raise AssertionError("source global IDs inconsistent")
    main=df.loc[df.grade.isin(("MEDIUM","LARGE"))].copy()
    small=df.loc[df.grade.eq("SMALL")].copy()
    if len(main)+len(small)!=len(df) or len(set(main.global_defect_id)&set(small.global_defect_id)):
        raise AssertionError("split omits or repeats an object")
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",dtype=">u2",mode="r",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    a=draw_base(raw,df,frozenset(("MEDIUM","LARGE")),
                f"MEDIUM+LARGE PRIMARY ({len(main)})")
    b=draw_base(raw,df,frozenset(("SMALL",)),
                f"SMALL REFERENCE ONLY ({len(small)})")
    assert a.shape==b.shape
    save_png(dest/"medium_large_main.png",a)
    save_png(dest/"small_reference.png",b)
    # Ensure same true RAW background on unmarked areas via independent full
    # pixel-level test in tests: graphic overlays do not alter the source.
    main.to_csv(dest/"medium_large_defects.csv",index=False,encoding="utf-8-sig")
    small.to_csv(dest/"small_defects_reference.csv",index=False,encoding="utf-8-sig")
    info={
        "source_J5":str(J5),
        "main_counts":{"MEDIUM":int((main.grade=="MEDIUM").sum()),
                       "LARGE":int((main.grade=="LARGE").sum())},
        "small_candidates":len(small),
        "total_global_candidates":len(df),
        "same_RAW_background":True,
        "same_global_coordinate_origin":[0,0],
        "preview_stride":STRIDE,
        "header_height_px":HEADER,
        "main_and_small_are_disjoint":True,
        "global_id_provenance_preserved":True,
        "source_masks_changed":False,
        "grades_changed":False,
        "display_only":True,
        "small_candidates_may_contain_many_noise_false_positives":True,
        "quality_acceptance_grade":False
    }
    (dest/"summary.json").write_text(json.dumps(info,ensure_ascii=False,indent=2),
                                    encoding="utf-8")
    # Verify output file is actually valid PNG, matching geometry.
    for p in (dest/"medium_large_main.png",dest/"small_reference.png"):
        im=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        assert im is not None and im.shape==a.shape,p
    print("J5_SPLIT_COMPLETE",json.dumps(info,ensure_ascii=False),flush=True)
    print("OUTPUT",dest,flush=True)
    return info


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",default=str(OUT))
    run(Path(p.parse_args().output))
