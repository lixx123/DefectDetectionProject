"""K8-B final independent audit: typed masks/threshold source and border risk.

IMPORTANT: Edge distance and area flags are AUDIT ONLY. No trial mask
deletion, no changes to J5, K5, source RAW or previous run outputs.
"""
from pathlib import Path
import json,sys
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
OUT=cfg.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
K8A=cfg.OUTPUT_ROOT/"case03k8a_auto_workband_masks/run_20261013_26twoframes_variableband_v2"
FUSED={
 1:cfg.OUTPUT_ROOT/"case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy",
 2:cfg.OUTPUT_ROOT/"case03k6_frame2_fused_blackhat/run_20261012_frame26_2_frozen_kernels_v1/frame26_2_fused_blackhat_exact.npy"}

def load(p):
    a=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if a is None or a.ndim!=2:raise ValueError(p)
    return a

def verify():
    summ=json.loads((OUT/"summary.json").read_text(encoding="utf-8"))
    assert summ["stage"]=="K8B_TWO_FRAME_EXPERIMENT_FINISHED_REVIEW_REQUIRED"
    result=[]
    for frame in (1,2):
        folder=OUT/f"frame26_{frame}"
        stats=pd.read_csv(folder/"perband_comparison_and_thresholds.csv")
        audit=json.loads((folder/"summary.json").read_text(encoding="utf-8"))
        ids=load(K8A/f"frame26_{frame}/band_id_fullres.png")
        region=load(K8A/f"frame26_{frame}/region_type_fullres.png")
        assert np.array_equal(ids>0,region==2)
        assert len(stats)==len(set(np.unique(ids))-{0})==4
        bh=np.load(FUSED[frame],mmap_mode="r",allow_pickle=False)
        original_centerclass=pd.read_csv(
            folder/"original_J5_object_center_workband_classification.csv")
        assert len(original_centerclass)==audit["original_J5_candidates_all_regions"]
        assert original_centerclass.K8A_region_code_by_original_J5_center.isin([0,1,2,3]).all()
        assert len(list(folder.glob("band_??_4panel_RAW_BH_A_B.png")))==4
        entries=[]
        for row in stats.itertuples():
            bid=int(row.band_id)
            y0,y1=int(row.band_crop_y0_inclusive),int(row.band_crop_y1_exclusive)
            A=load(folder/f"band_{bid:02d}_A_hysteresis_mask_cropped.png")>0
            B=load(folder/f"band_{bid:02d}_B_hysteresis_mask_cropped.png")>0
            core=ids[y0:y1,:]==bid
            assert A.shape==B.shape==core.shape
            assert not np.any(A&~core) and not np.any(B&~core)
            assert int(A.sum())==int(row.A_fixed_hysteresis_candidate_pixels)
            assert int(B.sum())==int(row.B_adaptive_hysteresis_candidate_pixels)
            assert int(np.count_nonzero(B&~A))==int(row.B_added_vs_A_candidate_pixels)
            assert int(np.count_nonzero(A&~B))==int(row.B_lost_vs_A_candidate_pixels)==0
            assert not np.any(A&(bh[y0:y1,:]<170))
            assert not np.any(B&(bh[y0:y1,:]<row.band_trial_low_dn))
            assert int(row.same_original_blackhat_max_diff_dn)==0
            # Field of support of up-to31px BlackHat closing reaches ~30px.
            # Edge flags are by distance to confirmed K8A WORK_CORE limit.
            # This is NOT a classifier or approved filter.
            D=cv2.distanceTransform(core.astype(np.uint8),cv2.DIST_L2,3)
            n,label,components,centroids=cv2.connectedComponentsWithStats(
                 B.astype(np.uint8),connectivity=8)
            near_area=(B&(D<32))
            ids_edge=np.unique(label[near_area])
            ids_edge=ids_edge[ids_edge>0]
            areas=components[1:,cv2.CC_STAT_AREA]
            sizes=components[ids_edge,cv2.CC_STAT_AREA] if len(ids_edge)>0 else np.empty(0,int)
            records={
              "frame":frame,"band_id":bid,
              "B_seeded_components":n-1,
              "B_components_1_to_2_px":int(np.sum(areas<=2)),
              "B_components_ge3_px":int(np.sum(areas>=3)),
              "B_components_ge10_px":int(np.sum(areas>=10)),
              "B_candidate_pixels_within32px_from_K8A_core_border":int(near_area.sum()),
              "B_components_touching32px_core_border":int(len(ids_edge)),
              "B_touching32px_edge_components_ge3":int(np.sum(sizes>=3)),
              "B_edge_risk_not_automatically_deleted":True
            }
            entries.append(records)
            print("K8B_EDGE_REVIEW",records,flush=True)
        count=pd.DataFrame(entries)
        csv=folder/"trial_candidate_size_and_edge_risk_audit.csv"
        if csv.exists():raise FileExistsError(csv)
        count.to_csv(csv,index=False,encoding="utf-8-sig")
        assert int(stats.A_fixed_hysteresis_candidate_pixels.sum())==audit[
            "A_fixed_hysteresis_candidate_pixels"]
        assert int(stats.B_adaptive_hysteresis_candidate_pixels.sum())==audit[
            "B_bandwise_adaptive_candidate_pixels"]
        assert audit["recomputed_original_BlackHat_maxdiff_DN"]==0
        names=["A_fixed_170_230_workband_overview.png",
            "B_robustZ_perband_workband_overview.png","B_new_vs_A_fixed_overview.png"]
        for f in names:
            im=cv2.imdecode(np.frombuffer((folder/f).read_bytes(),np.uint8),1)
            assert im is not None and min(im.shape[:2])>=1000
        gallery=folder/"band02_candidate_review_atlas"
        assert len(list(gallery.glob("*_RAW_B_candidate.png")))==2
        manual=pd.read_csv(gallery/"band2_candidate_raw_contrast_manual_review.csv")
        assert len(manual)==24
        assert manual.manual_confirm_defect.fillna("").eq("").all()
        result.append({"frame":frame,
                       "work_bands_count":len(stats),
                       "A_fixed_candidate_count":int(stats.A_fixed_hysteresis_candidate_components.sum()),
                       "B_trial_candidate_count":int(stats.B_adaptive_hysteresis_candidate_components.sum()),
                       "original_J5_objects_not_modified":len(original_centerclass),
                       "bands_all_exact_blackhat_recompute_0DN":True,
                       "source_pixel_masks_bitexact_validated":True,
                       "B2_RAW_microcandidate_manual_review_rows":len(manual),
                       "edge_audit":entries})
    answer={"stage":"CASE03K8B_QA_PASS",
            "frames":[1,2],
            "different_waveband_thresholds_preliminary":True,
            "5_waveband_geometry_supported_by_K8A_unit_test":True,
            "no_claim_precisions_or_recall":True,
            "no_perband_H_GH_J5_full_rebuild_performed":True,
            "no_original_data_or_source_J5_modified":True,
            "frame_results":result}
    path=OUT/"independent_trial_QA.json"
    if path.exists():raise FileExistsError(path)
    path.write_text(json.dumps(answer,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8B_INDEPENDENT_QA_PASS",json.dumps({
       "frame_stats":[{k:v for k,v in row.items() if k!="edge_audit"} for row in result],
       "no_J5_mutation":True},ensure_ascii=False),flush=True)
if __name__=="__main__":verify()
