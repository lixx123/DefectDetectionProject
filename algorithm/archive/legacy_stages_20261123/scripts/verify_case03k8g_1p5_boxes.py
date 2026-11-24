"""K8G independent image integrity, area/length, 1.5x and labels QA."""
from pathlib import Path
import sys,json,hashlib,math
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k8g_display_boxes import overlap_area,expand_bbox_xyxy,label_lines
O=C.OUTPUT_ROOT/"case03k8g_display_zoom_labels/run_20261015_26_1_2_boxes_1p5x_1px_size_v2"
K=C.OUTPUT_ROOT/"case03k8f_confirmed_group_register/run_20261014_F26_2_two_user_approved_G006_G009_v2"

def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run():
    results=[]
    for frame in (1,2):
        src=K/f"frame26_{frame}"/"workband_unified_candidate_review_register.csv"
        dest=O/f"frame26_{frame}"
        assert checksum(src)==checksum(dest/"frozen_K8F_work_review_register_UNCHANGED.csv")
        register=pd.read_csv(src,encoding="utf-8-sig")
        details=pd.read_csv(dest/"per_object_1p5_display_geometry_and_UNCHANGED_sizes.csv",
                            encoding="utf-8-sig")
        assert details.downsample_preview_stride.isin([4,8]).all()
        assert len(details)==(50 if frame==1 else 56)
        assert details.outline_width_DISPLAY_px.eq(1).all()
        assert details.measurement_uses_enlarged_bbox.eq(False).all()
        assert details.work_candidate_review_ID.nunique()==len(details)//2
        visible=register[register.size_grade.isin(["LARGE","MEDIUM"])]
        assert details.work_candidate_review_ID.nunique()==len(visible)
        assert set(details.work_candidate_review_ID)==set(visible.work_candidate_review_ID)
        s=details.merge(visible,on="work_candidate_review_ID",validate="many_to_one")
        assert (s.area_detector_px2_SOURCE_UNCHANGED==s.area_detector_px2).all()
        assert (s.size_grade_original==s.size_grade).all()
        assert np.allclose(s.max_feret_detector_px_SOURCE_UNCHANGED,s.max_length_detector_px,
                           rtol=0,atol=.00001)
        assert np.allclose(s.max_length_image_plane_um_SOURCE_UNCHANGED,
                           s.max_length_detector_image_um,rtol=0,atol=.00001)
        assert np.allclose(s.area_image_plane_um2_SOURCE_UNCHANGED,
                           s.area_detector_image_um2,rtol=0,atol=.00001)
        labelstats=[]
        for stride in (8,4):
            sub=s[s.downsample_preview_stride==stride]
            boxes=[];labels=[]
            for row in sub.itertuples(index=False):
                old=json.loads(row.old_display_bbox_RAW_xyxy_exclusive)
                new=json.loads(row.new_1p5_DISPLAY_bbox_RAW_xyxy_exclusive)
                assert np.allclose(new,expand_bbox_xyxy(old,
                       (C.RAW_WIDTH,C.RAW_HEIGHT),1.5),atol=1e-7)
                for a,b in ((0,2),(1,3)):
                    owidth=old[b]-old[a]
                    nwidth=new[b]-new[a]
                    if old[a]>owidth*.25 and old[b]<(C.RAW_WIDTH if a==0 else C.RAW_HEIGHT)-owidth*.25:
                        assert math.isclose(nwidth/owidth,1.5,abs_tol=1e-9)
                    else:assert nwidth<=1.5*owidth+1e-8
                    assert math.isclose((old[a]+old[b])/2,
                        (new[a]+new[b])/2,abs_tol=1e-8) if (
                        old[a]>owidth*.25 and old[b]<(C.RAW_WIDTH if a==0 else C.RAW_HEIGHT)-owidth*.25) else True
                boxes.append(json.loads(row.new_bbox_DISPLAY_xyxy_inclusive))
                labels.append(json.loads(row.label_display_xyxy_exclusive))
                assert ("px²" in row.label_text) and ("μm" in row.label_text)
            # Pixel boxes are inclusive at right/bottom; label rects half-open.
            ownhits=sum(overlap_area(lb,(b[0],b[1],b[2]+1,b[3]+1))>0
                          for b,lb in zip(boxes,labels))
            otherhits=sum(overlap_area(lb,(bb[0],bb[1],bb[2]+1,bb[3]+1))>0
                          for i,lb in enumerate(labels) for j,bb in enumerate(boxes) if i!=j)
            labelhits=sum(overlap_area(lb,l2)>0
                          for i,lb in enumerate(labels) for l2 in labels[i+1:])
            labelstats.append({"stride":stride,"own_box_hit":ownhits,
                "other_box_hit":otherhits,"label_collision_pairs":labelhits})
            pic=(dest/("01_MED_LARGE_boxes_1p5x_1px_with_area_length_overview_1to8.png"
                 if stride==8 else
                 "02_MED_LARGE_boxes_1p5x_1px_with_area_length_detail_1to4.png"))
            im=cv2.imdecode(np.frombuffer(pic.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
            assert im is not None
            assert im.shape[:2]==(
               math.ceil(C.RAW_HEIGHT/stride)+94,math.ceil(C.RAW_WIDTH/stride))
            print("K8G_RENDER_LABEL_INTERSECTIONS",frame,stride,
                  labelstats[-1],flush=True)
        if frame==2:
            f=dest/"03_G006_G009_1p5box_vs_exact_mask_three_panel.png"
            img=cv2.imdecode(np.frombuffer(f.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
            assert img is not None and img.shape==(948,1152,3)
        else:
            assert not (dest/"03_G006_G009_1p5box_vs_exact_mask_three_panel.png").exists()
        count=register.source.eq("K8F_USER_APPROVED_K8E_OUTER").sum()
        assert count==(0 if frame==1 else 2)
        summary=json.loads((dest/"summary.json").read_text(encoding="utf-8"))
        assert summary["original_source_detection_IDs_areas_feret_grades_modified"] is False
        assert summary["display_box_scale_factor"]==1.5
        assert summary["display_box_line_width_px"]==1
        assert summary["source_K8F_unified_review_count"]==len(register)
        results.append({"frame":frame,"visible_medium_large":len(visible),
                        "source_K8F_candidate_rows_preserved":len(register),
                        "all_labels_include_original_area_and_detector_length":True,
                        "all_source_areas_lengths_grades_unchanged":True,
                        "geometry_scale_factor_exact_except_RAW_border":True,
                        "label_quality":labelstats})
    out={"stage":"CASE03_K8G_DISPLAY_ONLY_PIXEL_QA_PASS",
        "physical_size_scale":"3.2um/px detector IMAGE PLANE only",
        "original_K8F_ledger_SHA256_unchanged":True,
        "no_source_detection_changes":True,"results":results}
    (O/"independent_QA.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),
                                        encoding="utf-8")
    print("K8G_QA_PASS",json.dumps(out,ensure_ascii=False),flush=True)

if __name__=="__main__":run()
