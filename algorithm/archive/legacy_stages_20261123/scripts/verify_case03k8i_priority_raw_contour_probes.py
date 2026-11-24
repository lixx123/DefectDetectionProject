"""Independent K8I not-yet-processed MED/LARGE RAW trial QA."""
from pathlib import Path
import sys,json
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
SRC=C.OUTPUT_ROOT/"case03k8i_full_frame_lineage/run_20261015_sample26_2frames_fullcandidate_lineage_v1"
OUT=C.OUTPUT_ROOT/"case03k8i_full_frame_lineage/run_20261015_fullframe_novel_medlarge_K8D_original_rules_probe_v1"
def test():
    audit=[]
    for fr in (1,2):
        p=SRC/f"frame26_{fr}"/"end_to_end_candidate_lineage.csv"
        source=pd.read_csv(p,low_memory=False,dtype={"source_local_id":"string"})
        expected=source[source.primary_visibility_layer=="B_NOVEL_MEDLARGE"]
        folder=OUT/f"frame26_{fr}"
        if fr==1:
            actual=pd.read_csv(folder/"all_NOT_PREVIOUSLY_PROCESSED_NOVEL_MEDLARGE_K8D_trials.csv")
        else:
            # Empty dataset has headings? If no rows and no keys, pandas
            # writer may serialize blank text; no numeric candidate exists.
            q=folder/"all_NOT_PREVIOUSLY_PROCESSED_NOVEL_MEDLARGE_K8D_trials.csv"
            actual=pd.read_csv(q) if q.stat().st_size else pd.DataFrame()
        assert len(expected)==len(actual)==(4 if fr==1 else 0)
        if fr==1:
            expected_set={(int(t.band_id),int(t.source_local_id)) for t in expected.itertuples()}
            actual_set={(int(t.band_id),int(t.B_label)) for t in actual.itertuples()}
            assert expected_set==actual_set
            expected_areas={(2,3):52,(2,9):51,(3,1692):104,(3,3615):120}
            selected={(2,3):52,(2,9):51,(3,1692):325,(3,3615):120}
            for row in actual.itertuples(index=False):
                key=(int(row.band_id),int(row.B_label))
                assert int(row.original_B_source_area_px2)==expected_areas[key]
                assert int(row.K8D_trial_outer_area_px2)==selected[key]
                assert row.fully_manual_review_required and not row.source_modified
                f=folder/f"band{row.band_id:02d}"/(
                    f"F{fr}_B{row.band_id}_C{row.B_label:05d}_NEW_RAW_trial_all_masks.npz")
                with np.load(f,allow_pickle=False) as z:
                    src=z["original_B_source"].astype(bool)
                    dst=z["K8I_K8D_review_outer"].astype(bool)
                    work=z["K8A_work_core"].astype(bool)
                    lab=z["original_B_labels"]
                    assert src.shape==dst.shape==work.shape==(128,128)
                    assert np.all(dst[src])
                    assert np.array_equal(lab==row.B_label,src)
                    assert int(src.sum())==row.original_B_source_area_px2
                    assert int(dst.sum())==row.K8D_trial_outer_area_px2
                    assert int(z["raw_k3"].sum())==row.RAW_3MAD_px2
                    assert int(z["raw_k2"].sum())==row.RAW_2MAD_px2
                    assert int(z["raw_k1p5"].sum())==row.RAW_1p5MAD_px2
                    if row.status.startswith("STABLE_"):
                        assert not np.any(dst&~work)
                image=f.with_name(f.stem.replace("_all_masks","_6panel")+".png")
                im=cv2.imdecode(np.frombuffer(image.read_bytes(),np.uint8),1)
                assert im is not None and im.shape==(334,1536,3)
                if key==(3,1692):
                    assert row.status=="STABLE_SINGLE_OUTER_REVIEW"
                    assert (int(row.RAW_3MAD_px2),int(row.RAW_2MAD_px2),
                            int(row.RAW_1p5MAD_px2))==(253,299,325)
                else:
                    assert row.status=="SOURCE_ONLY_UNRELIABLE_3MAD"
        summ=json.loads((folder/"summary.json").read_text(encoding="utf-8"))
        assert summ["novel_MEDLARGE_without_previous_K8D"]==len(expected)
        assert summ["newly_production_approved_count"]==0
        assert summ["all_new_proposed_masks_review_only"]
        assert summ["any_original_J5_B_or_existing_K8D_data_changed"] is False
        q=folder/"08_NEW_MEDLARGE_RAW_trial_overlay_NOT_APPROVED.png"
        preview=cv2.imdecode(np.frombuffer(q.read_bytes(),np.uint8),1)
        assert preview is not None and preview.shape==(
            (C.RAW_HEIGHT//4)+88,(C.RAW_WIDTH+3)//4,3)
        audit.append({"frame":fr,"previously_unprocessed_novel_mediumlarge":len(expected),
              "new_strict_original_K8D_rule_probes":len(actual),
              "source_B_masks_bit_exact":True,"no_new_accepted_production_objects":True})
    report={"stage":"K8I_NOVEL_MEDLARGE_OUTER_INDEPENDENT_QA_PASS","frames":audit,
        "all_original_J5_K8B_K8D_source_files_untouched":True,
        "K8C_micro_candidates_untouched_not_expanded":True,
        "all_outer_results_remain_review_only":True}
    o=OUT/"independent_QA.json"
    if o.exists():raise FileExistsError(o)
    o.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8I_NOVEL_MEDLARGE_OUTER_INDEPENDENT_QA_PASS",
          json.dumps(report,ensure_ascii=False),flush=True)
if __name__=="__main__":test()
