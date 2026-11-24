"""Read-only QA of J4 in-progress / completed full-frame tile artifacts.

Check only COMMITTED tile_status/*.json. Current active tile without
committed status is ignored. Does not rewrite/change user's data.
"""
from __future__ import annotations
from pathlib import Path
import json,sys
import numpy as np, cv2, pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.run_case03j4_fullscan import tiles
from config import user_config as cfg

def verify(run_id:str)->dict:
    out=cfg.OUTPUT_ROOT/"case03j4_fullframe"/run_id
    expected={r["tile_id"]:r for r in tiles((cfg.RAW_HEIGHT,cfg.RAW_WIDTH),
                                              cfg.CASE03J4_CORE_SIZE_PX)}
    statusfiles=sorted((out/"tile_status").glob("*.json"))
    object_count=0
    clipped_count=0
    image_count=0
    total_original=0
    total_bridge=0
    for f in statusfiles:
        data=json.loads(f.read_text(encoding="utf-8"))
        tid=f.stem
        assert tid in expected and data["stage"]=="J4_TILE_COMPLETE"
        assert data["core_xyxy"]==expected[tid]["core_xyxy"]
        p=out/"tile_masks"/(tid+".npz")
        with np.load(p,allow_pickle=False) as z:
            rect=[int(v) for v in z["core_xyxy"]]
            source=z["source_detected_uint8"]>0
            lab=z["source_region_label_i32"]
            grouped=z["grouped_source_only_i32"]
            infer=z["inferred_bridge_i32"]
            visual=z["continuous_display_i32"]
            assert rect==data["core_xyxy"]
            assert source.shape==(rect[3]-rect[1],rect[2]-rect[0])
            assert np.array_equal(source,lab>0)
            assert np.array_equal(source,grouped>0)
            assert np.array_equal(visual>0,source|(infer>0))
            assert not np.any(source & (infer>0))
            assert int(source.sum())==data["final_source_core_pixels"]
            assert int(np.count_nonzero(infer))==data["inferred_bridge_pixels"]
        objfile=out/"tile_objects"/(tid+".csv")
        if data["tile_objects"]:
            assert objfile.exists()
            obs=pd.read_csv(objfile,encoding="utf-8-sig")
            assert len(obs)==data["tile_objects"]
            assert obs["tile_id"].eq(tid).all()
            assert (~obs["unique_global_object_id_assigned"]).all()
            assert (~obs["cross_tile_reconciled"]).all()
            assert all(obs["display_bbox_x_global"]>=rect[0])
            assert all(obs["display_bbox_y_global"]>=rect[1])
            assert all(obs["display_bbox_xmax_inclusive"]<rect[2])
            assert all(obs["display_bbox_ymax_inclusive"]<rect[3])
            image=out/"tiles_marked"/(tid+"_fourpanel.png")
            if image.exists():
                decoded=cv2.imdecode(np.frombuffer(image.read_bytes(),np.uint8),
                                    cv2.IMREAD_COLOR)
                assert decoded is not None and decoded.shape[1]==4*source.shape[1]
                image_count+=1
            object_count+=len(obs)
            clipped_count+=int(obs["bbox_may_be_truncated"].sum())
        else:
            assert not objfile.exists()
        total_original+=int(source.sum())
        total_bridge+=int(np.count_nonzero(infer))
    failure=out/"failed_tile.json"
    summary={
        "committed_tiles":len(statusfiles),
        "expected_tiles":len(expected),
        "source_pixels":total_original,
        "inferred_bridge_pixels":total_bridge,
        "unmerged_local_objects":object_count,
        "edge_truncated_objects":clipped_count,
        "decoded_nonempty_tile_figures":image_count,
        "failed_tile_exists":failure.exists(),
        "all_committed_tiles_QA_pass":True,
        "whole_image_done":len(statusfiles)==len(expected),
    }
    print("J4_PARTIAL_QA",json.dumps(summary,ensure_ascii=False),flush=True)
    return summary

if __name__=="__main__":
    verify("run_20261012_frame26_1_full_j4_v1")
