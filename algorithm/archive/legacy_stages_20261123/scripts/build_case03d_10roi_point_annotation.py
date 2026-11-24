"""Build offline RAW 10-ROI point-and-rectangle annotation for exact defect locations.

Existing H candidate ID is the review context, not automatically the clicked
physical anomaly. Annotation does not train classifier or overwrite original
RAW, masks, CSV/JSON user submissions.
"""
from __future__ import annotations
import json,sys
from pathlib import Path
import cv2
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.visualization.case03d_detected_atlas import roi_from_current

SOURCE=ROOT/"outputs/case03d_manual_review_analysis/run_20261010_092200"
RUN=ROOT/"outputs/case03d_autodetect/run_20261009_autodetect_final"
DEST=SOURCE/"ten_roi_true_target_click_annotation"
TEMPLATE=ROOT/"src/visualization/case03d_10roi_annotation_template.html"
SIZE=160

def main():
    if DEST.exists():raise FileExistsError("Never overwrite existing manual annotation UI")
    DEST.mkdir(parents=True)
    assets=DEST/"assets"
    assets.mkdir()
    rows=pd.read_csv(SOURCE/"ROI_annotation_scope_exceptions_10.csv",low_memory=False)
    if len(rows)!=10 or rows["candidate_id"].duplicated().any():
        raise ValueError("Expected precisely 10 unique scope exceptions")
    with np.load(RUN/"candidate_status_map_lossless.npz",allow_pickle=False) as z:
        statuses=z["class_map"]
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    assert raw.shape==statuses.shape==(9200,11276)
    items=[]
    for i,rec in enumerate(rows.to_dict("records"),1):
        x0,y0,x1,y1=roi_from_current(rec,raw.shape,SIZE)
        sub=np.asarray(raw[y0:y1,x0:x1],dtype=np.float32)
        lo,hi=np.percentile(sub,[1,99.5]);hi=max(hi,lo+1)
        grey=np.uint8(np.rint(np.clip((sub-lo)/(hi-lo),0,1)*255))
        rgb=cv2.cvtColor(grey,cv2.COLOR_GRAY2BGR)
        annotated=rgb.copy()
        state=statuses[y0:y1,x0:x1]
        annotated[state==3]=(38,220,64)
        annotated[state==2]=(21,188,244)
        annotated[state==1]=(170,56,170)
        stem=f"{i:02d}_{rec['candidate_id']}"
        relraw="assets/"+stem+"_raw.png"
        relmask="assets/"+stem+"_status.png"
        for rel,im in [(relraw,rgb),(relmask,annotated)]:
            ok,encoded=cv2.imencode(".png",im,[cv2.IMWRITE_PNG_COMPRESSION,4])
            if not ok:raise IOError(rel)
            (DEST/rel).write_bytes(encoded.tobytes())
        items.append({
            "index":i,"candidate_id":rec["candidate_id"],
            "human_note":rec["note"],
            "original_label":rec["manual_label"],
            "roi_x0":int(x0),"roi_y0":int(y0),
            "bbox_x":int(rec["bbox_x"]),"bbox_y":int(rec["bbox_y"]),
            "bbox_w":int(rec["bbox_w"]),"bbox_h":int(rec["bbox_h"]),
            "centroid_x":float(rec["centroid_x"]),
            "centroid_y":float(rec["centroid_y"]),
            "raw_image":relraw,"status_image":relmask
        })
    template=TEMPLATE.read_text(encoding="utf-8")
    if template.count("__DATA__")!=1:
        raise ValueError("Exactly one HTML data placeholder required")
    data=json.dumps(items,ensure_ascii=False).replace("<","\\u003c")
    (DEST/"index.html").write_text(template.replace("__DATA__",data),encoding="utf-8")
    pd.DataFrame(items).to_csv(DEST/"ten_roi_manifest.csv",index=False,encoding="utf-8-sig")
    (DEST/"README.md").write_text(
        "# 10处用户指出异常的RAW像素重新定位工具\n\n"
        "双击index.html打开离线网页，原始RAW像素160x160放大到640x640，"
        "点击真实异常的中心，不是旧H候选的红框位置。支持多次点选和可选两角矩形框选。"
        "旧算法状态图仅供辅助，不代表真实滤光片缺陷。\n\n"
        "点击后用按钮导出JSON备份和CSV（网页不联网），刷新前必须导出JSON。"
        "CSV中parent_H_ID只记录哪个原候选提供本ROI，不证明它就是疵病。"
        "点选只提供物面候选RAW位置，不产生伪造面积；框选bbox为人工近似面积，"
        "准确轮廓和区域像素数必须从后续匹配的原H掩膜或重新分割取得。\n\n"
        "用户目前不需要暗点/划痕/麻点类型分类器；后续仅做二元异常筛选、"
        "精确轮廓、面积/最大尺寸测量与大小等级着色。"
        "当前3.2um为探测器像元尺寸，未确认物面标定比例前不换算物理尺寸，"
        "也不擅自设定实际疵病等级阈值。历史文件保持原样。\n",
        encoding="utf-8"
    )
    print("10ROI_ANNOTATION_UI",DEST/"index.html")
    print("ROI_COUNT",len(items),"PNG_ASSETS",len(list(assets.glob("*.png"))))

if __name__=="__main__":main()
