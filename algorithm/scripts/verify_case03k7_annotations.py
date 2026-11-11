"""K7 independent measurements QA, without editing original data."""
from pathlib import Path
import sys,json
import pandas as pd,numpy as np,cv2
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from scripts.run_case03k7_physical_annotations import (
 RUN_DIR,PITCH,SOURCE,detector_table,STRIDE)
from src.detection.case03i_size_grade import max_feret_centers_px

def verify():
    assert RUN_DIR.exists()
    assert PITCH==3.2
    assert round(4*PITCH**2,2)==40.96
    assert max_feret_centers_px(np.asarray([[20,30]],np.float32))==1.
    summary=json.loads((RUN_DIR/"summary.json").read_text(encoding="utf-8"))
    assert not summary["object_plane_scale_calibrated"]
    assert not summary["official_J5_source_masks_changed"]
    assert summary["outline_width_preview_px"]==1
    outputs={}
    for frame in (1,2):
        j5=SOURCE[frame]
        old=pd.read_csv(j5/"global_defects.csv",encoding="utf-8-sig")
        out=RUN_DIR/f"frame26_{frame}"
        present=pd.read_csv(out/"all_J5_objects_detector_sizes_um.csv",
                            encoding="utf-8-sig")
        assert len(present)==len(old)
        assert set(old.global_defect_id)==set(present.global_defect_id)
        assert present.global_defect_id.is_unique
        assert np.array_equal(present.grade.to_numpy(),old.grade.to_numpy())
        assert np.array_equal(present.source_area_px2.to_numpy(),
                              old.source_area_px2.to_numpy())
        assert np.allclose(
            present.detector_equiv_max_feret_length_um,
            (old.source_max_feret_px.astype(float)*PITCH).round(3))
        assert np.allclose(
            present.detector_equiv_detected_area_um2,
            (old.source_area_px2.astype(float)*PITCH**2).round(3))
        assert np.allclose(
            present.detector_equiv_bbox_width_um,
            (old.source_bbox_width_px.astype(float)*PITCH).round(3))
        assert present.dimension_calibration_scope.eq(
           "DETECTOR_IMAGE_PLANE_EQUIVALENT_NOT_OBJECT_PLANE").all()
        assert present.measurement_source.eq(
           "J5_ORIGINAL_SOURCE_PIXELS_NO_INFERRED_BRIDGE").all()
        assert present.object_plane_magnification_verified.eq(False).all()
        assert not present.size_grade_was_reclassified.any()
        px1=present.loc[present.source_area_px2==1]
        assert (px1.detector_equiv_detected_area_um2==10.24).all()
        assert (px1.detector_equiv_max_feret_length_um==3.2).all()
        expected_img=[
          out/"medium_large_thin_1px.png",
          out/"medium_large_with_detector_sizes_um.png",
          out/"small_reference_thin_1px.png",
          *sorted(out.glob("large_medium_gallery_*.png"))]
        assert len(expected_img)==6
        for p in expected_img:
            b=p.read_bytes()
            im=cv2.imdecode(np.frombuffer(b,np.uint8),cv2.IMREAD_COLOR)
            assert im is not None and min(im.shape[:2])>500,p
        split=pd.read_csv(out/"medium_large_sizes_um.csv")
        small=pd.read_csv(out/"small_reference_sizes_um.csv")
        assert len(split)+len(small)==len(old)
        assert split.grade.isin(("MEDIUM","LARGE")).all()
        assert small.grade.eq("SMALL").all()
        trial=pd.read_csv(out/"K5_estimated_contour_sizes_FOR_REVIEW_ONLY.csv")
        assert trial.official_J5_mask_and_area_replaced.eq(False).all()
        assert trial.estimated_contour_not_physical_truth.eq(True).all()
        assert np.allclose(trial.trial_contour_area_detector_um2,
            (trial.trial_contour_area_px2*PITCH**2).round(3))
        record=json.loads((out/"gallery_pixel_conservation.json").read_text(encoding="utf-8"))
        assert len(record)==36
        for v in record:
            assert int(v["source_pixels_verified"])==int(
                old.set_index("global_defect_id").loc[v["global_defect_id"],"source_area_px2"])
        outputs[frame]={
            "original_J5_preserved":len(old),
            "medium_large":len(split),"small":len(small),
            "sample_gallery_exact_pixel_masks":len(record),
            "K5_trial_rows_separate":len(trial),
            "PNG_decoded":len(expected_img)}
    print("K7_DETECTOR_SCALE_AND_IMAGE_QA_PASS",json.dumps(outputs,ensure_ascii=False),flush=True)
if __name__=="__main__":verify()
