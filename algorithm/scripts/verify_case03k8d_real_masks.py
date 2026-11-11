"""Independent K8D real RAW regression and source-pixel audit.

Checks original archived K8C/K8B source labels, K8D 3-floor masks and
no-lost-pixel invariants; asserts known regressions 1148,626,1161,1483.
"""
from pathlib import Path
import json,sys
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
OUT=C.OUTPUT_ROOT/"case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3"
UP=C.OUTPUT_ROOT/"case03k8c_outlines_prioritized/run_20261013_K5RAW_contour_expansion_pilot_v1"
B=C.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
EXPECTED={
  1148:(48,369,317),
  626:(34,348,273),
  1161:(64,370,314),
  1483:(12,12,0)
}
def audit():
    report=[]
    for frame in (1,2):
        directory=OUT/f"frame26_{frame}"
        rows=pd.read_csv(directory/"all_K8D_original_vs_outer_review.csv",
                         encoding="utf-8-sig")
        old=pd.read_csv(UP/f"frame26_{frame}/all_selected_darkspots_K5RAW_outer_comparison.csv",
                        encoding="utf-8-sig")
        assert len(rows)==len(old)==(13 if frame==1 else 19)
        assert rows.uid.is_unique
        assert rows.no_automatic_ID_merge.all()
        assert rows.source_B_and_J5_masks_unchanged.all()
        assert rows.physical_object_plane_calibration_confirmed.eq(False).all()
        assert (rows.K8D_review_outer_px2>=rows.source_area_px2).all()
        for obj in rows.itertuples(index=False):
            upstream=old[(old.band_id==obj.band_id)&(
                  old.candidate_label==obj.candidate_label)]
            assert len(upstream)==1
            assert obj.source_area_px2==int(upstream.original_B_source_area_px2.iloc[0])
            name=f"F{frame}_B{obj.band_id}_C{obj.candidate_label:05d}"
            path=directory/f"band{obj.band_id:02d}"/(name+"_K8D_all_masks.npz")
            with np.load(path,allow_pickle=False) as x:
                seed=x["original_B_source"].astype(bool)
                full=x["K8D_full_outer"].astype(bool)
                core=x["work_core"].astype(bool)
                labelgrid=x["B_label_grid_in_roi"]
                b3=x["raw_k3"].astype(bool)
                b2=x["raw_k2"].astype(bool)
                b15=x["raw_k1p5"].astype(bool)
            oldnpz=UP/f"frame26_{frame}"/f"band{obj.band_id:02d}"/(
                name+"_all_masks.npz")
            with np.load(oldnpz,allow_pickle=False) as x:
                assert np.array_equal(seed,x["original_B_seed"].astype(bool))
                assert np.array_equal(b3,x["raw_k3"].astype(bool))
                assert np.array_equal(b2,x["raw_k2"].astype(bool))
                assert np.array_equal(b15,x["raw_k1p5"].astype(bool))
                assert np.array_equal(core,x["core_K8A_work"].astype(bool))
            assert int(seed.sum())==obj.source_area_px2
            assert int(full.sum())==obj.K8D_review_outer_px2
            assert np.array_equal(seed|full,full)
            assert np.array_equal(labelgrid==obj.candidate_label,seed)
            if obj.status.startswith("STABLE_"):
                assert not np.any(full&~core)
            if obj.status.startswith("SOURCE_ONLY_"):
                assert np.array_equal(full,seed)
            if obj.status.startswith(("AMBIGUOUS_","CENSORED_")):
                assert obj.no_automatic_ID_merge
            plot=directory/f"band{obj.band_id:02d}"/(name+"_K8D_six_panel.png")
            im=cv2.imdecode(np.frombuffer(plot.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
            assert im is not None and im.shape==(334,1536,3)
        if frame==2:
            b2=rows[rows.band_id==2].set_index("candidate_label")
            for label,(source,review,b3min) in EXPECTED.items():
                r=b2.loc[label]
                assert int(r.source_area_px2)==source
                assert int(r.K8D_review_outer_px2)==review
                assert int(r.RAW_k3_px2)>=b3min
                if label!=1483:
                    assert r.status.startswith(("STABLE_","AMBIGUOUS_"))
                else:
                    assert r.status=="SOURCE_ONLY_UNRELIABLE_3MAD"
                    assert int(r.RAW_k1p5_px2)==1746
        summ=json.loads((directory/"summary.json").read_text(encoding="utf-8"))
        assert summ["objects_processed"]==len(rows)
        assert not summ["original_J5_K5_untouched"] is False
        assert summ["frozen_J5_work_mediumlarge"]==(25 if frame==1 else 26)
        assert summ["contours_expanded"]==int((rows.K8D_review_outer_px2>rows.source_area_px2).sum())
        assert summ["stable_mediumlarge_overlays"]+summ["ambiguous_complete_overlays"]<=int(
            (rows.K8D_review_outer_px2>rows.source_area_px2).sum())
        for image in directory.glob("0?_*.png"):
            im=cv2.imdecode(np.frombuffer(image.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
            assert im is not None and im.shape[1]>1000
        groups=pd.read_csv(directory/"deduplicated_review_groups_NO_official_merge.csv")
        assert groups.physical_IDs_merged.eq(False).all()
        report.append({
           "frame":frame,"source_objects":len(rows),
           "expanded":int(summ["contours_expanded"]),
           "stable_mediumlarge_overlays":summ["stable_mediumlarge_overlays"],
           "ambiguous_full_review_overlays":summ["ambiguous_complete_overlays"],
           "source_masks_match_previous_archives":True,
           "regressions_1148_626_1161_and_guard1483_checked":frame==2})
    state={"stage":"K8D_REAL_PIXEL_EXACT_QA_PASS",
          "frames":report,"old_source_data_modified":False,
          "previously_small_final_contour_cases_fixed":True,
          "physical_object_contour_human_validation_still_required":True}
    file=OUT/"independent_QA.json"
    if file.exists():raise FileExistsError(file)
    file.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8D_REAL_PIXEL_EXACT_QA_PASS",json.dumps(state,ensure_ascii=False),flush=True)

if __name__=="__main__":audit()
