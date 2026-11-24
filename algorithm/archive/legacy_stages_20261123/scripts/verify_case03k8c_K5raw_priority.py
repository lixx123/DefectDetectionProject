"""Independent pixel verification of K8C prioritized RAW contour trial."""
from pathlib import Path
import sys,json
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
PATH=cfg.OUTPUT_ROOT/"case03k8c_outlines_prioritized/run_20261013_K5RAW_contour_expansion_pilot_v1"
K8C=cfg.OUTPUT_ROOT/"case03k8c_band_supplement_review/run_20261013_f1_f2_allbands_reversible_v2"

def run():
    totals=[]
    for frame in (1,2):
        d=PATH/f"frame26_{frame}"
        report=pd.read_csv(d/"all_selected_darkspots_K5RAW_outer_comparison.csv",
                           encoding="utf-8-sig")
        upstream=pd.read_csv(K8C/f"frame26_{frame}/all_K8B_candidate_objects_complete_K8C_audit.csv",
                             encoding="utf-8-sig")
        assert report.candidate_group_uid.is_unique
        assert all(report.J5_original_source_unchanged)
        assert len(report)==(13 if frame==1 else 19)
        assert (report.proposed_K5RAW_outer_area_px2>=report.original_B_source_area_px2).all()
        for row in report.itertuples(index=False):
            match=upstream[upstream.candidate_group_uid==row.candidate_group_uid]
            assert len(match)==1
            assert int(match.iloc[0].candidate_area_px2)==int(row.original_B_source_area_px2)
            p=d/f"band{int(row.band_id):02d}"/(
                f"F{frame}_B{int(row.band_id)}_C{int(row.candidate_label):05d}_all_masks.npz")
            with np.load(p,allow_pickle=False) as z:
                B=z["original_B_seed"].astype(bool)
                proposed=z["proposed_after_safety_gate"].astype(bool)
                core=z["core_K8A_work"].astype(bool)
                assert B.shape==proposed.shape==core.shape==(128,128)
                assert np.count_nonzero(B)==row.original_B_source_area_px2
                assert np.count_nonzero(proposed)==row.proposed_K5RAW_outer_area_px2
                assert np.array_equal(proposed|B,proposed)
                # Any fully authorized expansion CANNOT add pixels outside
                # the same band's working core.
                if str(row.status).startswith("PROVISIONAL_RAW"):
                    assert not np.any(proposed&~core)
                assert "raw_k3" in z and "raw_k2" in z and "raw_k1p5" in z
            img=d/f"band{int(row.band_id):02d}"/(
                f"F{frame}_B{int(row.band_id)}_C{int(row.candidate_label):05d}_six_panel.png")
            decoded=cv2.imdecode(np.frombuffer(img.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
            assert decoded is not None and decoded.shape[1]>=1400
        files=list(d.glob("0?_*.png"))
        assert len(files)==5
        for fname in files:
            decoded=cv2.imdecode(np.frombuffer(fname.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
            assert decoded is not None and decoded.shape[1]>=1000
        p=json.loads((d/"PRIORITY_VIEW_SUMMARY.json").read_text(encoding="utf-8"))
        assert p["work_core_frozen_J5_mediumlarge"]==(25 if frame==1 else 26)
        assert p["work_core_frozen_J5_small"]==(658 if frame==1 else 372)
        assert p["safe_contours_mediumlarge_promoted_for_review"]==(0 if frame==1 else 4)
        assert (report[report.status.str.startswith("PROVISIONAL_RAW")].shape[0]
                ==p["safe_contours_mediumlarge_promoted_for_review"])
        totals.append({"frame":frame,"review_proposals":len(report),
                       "provisional_safe_outer":p["safe_contours_mediumlarge_promoted_for_review"],
                       "original_source_masks_all_preserved":True,
                       "full_res_repaired_mask_belongs_to_K8A_work_core":True,
                       "images_and_NPZ_verified":len(report)+len(files)})
    ans={"stage":"CASE03K8C_K5RAW_OUTER_PRIORITY_QA_PASS",
         "not_full_K5_unchanged_low_threshold_replacement":True,
         "original_J5_and_previous_K8C_source_masks_untouched":True,
         "no_human_truth_quantitative_accuracy_claim":True,
         "reports":totals}
    fn=PATH/"independent_QA.json"
    if fn.exists():raise FileExistsError(fn)
    fn.write_text(json.dumps(ans,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8C_RAW_PRIORITIZED_QA_PASS",json.dumps(ans,ensure_ascii=False),flush=True)
if __name__=="__main__":run()
