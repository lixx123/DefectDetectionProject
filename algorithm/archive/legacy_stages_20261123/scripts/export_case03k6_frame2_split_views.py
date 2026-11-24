"""Case03-K6: split frozen SECOND-frame J5 visualizations by size.

Maintains same physical RAW coordinate frame and preview factor=8.
Does NOT change J5 source classification/IDs or infer defect-free zones.
"""
from pathlib import Path
import json,sys
import pandas as pd,numpy as np,cv2
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03i_size_grade import GRADE_COLORS_BGR
from scripts.run_case03g_joint_noise_refinement import save_png,gray
SRC=cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_2_J5_independent_v1"
OUT=SRC/"second_frame_separate_size_views_v1"
STRIDE=8

def run():
    if OUT.exists():raise FileExistsError(OUT)
    if not (SRC/"summary.json").is_file():raise FileNotFoundError("J5 incomplete")
    state=json.loads((SRC/"summary.json").read_text(encoding="utf-8"))
    assert state["stage"]=="J5_COMPLETE" and state["source_area_unchanged"]
    frame=pd.read_csv(SRC/"global_defects.csv",encoding="utf-8-sig")
    assert len(frame)==int(state["global_candidate_objects"])
    assert frame.global_defect_id.is_unique
    small=frame[frame.grade=="SMALL"].copy()
    main=frame[frame.grade.isin(("MEDIUM","LARGE"))].copy()
    assert len(small)+len(main)==len(frame)
    raw=np.memmap(cfg.DATA_ROOT/"26 (2).raw",mode="r",dtype=">u2",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    preview=gray(np.asarray(raw[::STRIDE,::STRIDE],np.uint16))
    def draw(which,types):
        img=preview.copy()
        for row in frame.itertuples():
            if row.grade not in types:continue
            color=GRADE_COLORS_BGR[row.grade]
            if row.grade=="SMALL":
                cv2.circle(img,(int(row.center_x_global)//STRIDE,
                                int(row.center_y_global)//STRIDE),1,color,-1,cv2.LINE_8)
            else:
                box=(int(row.display_bbox_x_global)//STRIDE,
                     int(row.display_bbox_y_global)//STRIDE)
                edge=(int(row.display_bbox_xmax_inclusive)//STRIDE,
                      int(row.display_bbox_ymax_inclusive)//STRIDE)
                cv2.rectangle(img,box,edge,color,1,cv2.LINE_8)
        banner=86
        img=cv2.copyMakeBorder(img,banner,0,0,0,cv2.BORDER_CONSTANT,value=(25,25,25))
        cv2.putText(img,f"26 FRAME 2 | FROZEN J5 | {which}",
                   (12,27),cv2.FONT_HERSHEY_SIMPLEX,.52,(237,237,237),1)
        cv2.putText(img,"RAW 26(2) | native coords origin(0,0) | preview scale 1:8",
                   (12,52),cv2.FONT_HERSHEY_SIMPLEX,.43,(216,216,216),1)
        cv2.putText(img,
           "Unverified detection size grade, NOT a human confirmed defect",
           (12,74),cv2.FONT_HERSHEY_SIMPLEX,.39,(216,216,216),1)
        return img
    OUT.mkdir(parents=True)
    mainpath=OUT/"medium_large_main.png"
    smallpath=OUT/"small_reference.png"
    a=draw("MEDIUM+LARGE MAIN",("MEDIUM","LARGE"))
    b=draw("SMALL / REVIEW ONLY",("SMALL",))
    assert a.shape==b.shape
    save_png(mainpath,a);save_png(smallpath,b)
    main.to_csv(OUT/"medium_large_defects.csv",encoding="utf-8-sig",index=False)
    small.to_csv(OUT/"small_defects_reference.csv",encoding="utf-8-sig",index=False)
    for p in (mainpath,smallpath):
        im=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        assert im is not None and im.shape==a.shape
    result={
       "frame":2,"stage":"J5_SECOND_FRAME_SPLIT_VISUALS",
       "medium":int((main.grade=="MEDIUM").sum()),
       "large":int((main.grade=="LARGE").sum()),
       "small":len(small),"objects":len(frame),
       "same_frozen_RAW_backdrop":True,"same_origin":[0,0],
       "same_preview_stride":STRIDE,
       "source_J5_modified":False
    }
    (OUT/"summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K6_J5_SPLIT_COMPLETE",json.dumps(result,ensure_ascii=False),flush=True)
    return result
if __name__=="__main__":run()
