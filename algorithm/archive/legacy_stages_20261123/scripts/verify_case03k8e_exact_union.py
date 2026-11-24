"""Independent K8E review-group and original source-mask conservation audit."""
from pathlib import Path
import sys,json,cv2
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k8e_group_hypothesis import union_global
E=C.OUTPUT_ROOT/"case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1"
D=C.OUTPUT_ROOT/"case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3"
B=C.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"

def audit():
    results=[]
    for frame in (1,2):
        out=E/f"frame26_{frame}"
        df=pd.read_csv(out/"K8E_unique_group_union_measurements.csv",
                       encoding="utf-8-sig").fillna({"embedded_B_labels_TO_REVIEW":"",
                                                    "selected_B_labels":""})
        members=pd.read_csv(out/"K8E_source_member_traceability.csv",
                           encoding="utf-8-sig")
        orig=pd.read_csv(D/f"frame26_{frame}/all_K8D_original_vs_outer_review.csv")
        expected_original={(int(x.band_id),int(x.candidate_label))
                           for x in orig.itertuples(index=False)}
        used=[]
        groups_count=0
        for obj in df.itertuples(index=False):
            groups_count+=1
            path=out/"group_detail"/(obj.group_id+"_EXACT_GROUP_MASK.npz")
            with np.load(path,allow_pickle=False) as z:
                mask=z["review_outer"].astype(bool)
                roi=tuple(int(v) for v in z["roi_xyxy"])
                source_selected=list(map(int,z["source_component_labels"]))
                embedded=list(map(int,z["embedded_B_candidate_labels"]))
                ref_grid=z["source_B_label_grid"].astype(np.int32)
            actual_labels=[int(s) for s in str(obj.selected_B_labels).split(";")]
            assert source_selected==actual_labels
            assert mask.shape==(roi[3]-roi[1],roi[2]-roi[0])
            assert int(mask.sum())==obj.unique_outer_union_px2
            assert not obj.official_source_B_J5_IDs_merged
            assert not obj.can_be_used_as_certified_defect_area
            assert not obj.raw_J5_K5_K8B_K8C_K8D_input_modified
            assert obj.group_id.startswith(f"K8E_F{frame}_B{int(obj.band_id)}_")
            olditems=[]
            for label in source_selected:
                matches=orig[(orig.band_id==obj.band_id)&(orig.candidate_label==label)]
                assert len(matches)==1
                p=D/f"frame26_{frame}"/f"band{int(obj.band_id):02d}"/(
                    f"F{frame}_B{int(obj.band_id)}_C{label:05d}_K8D_all_masks.npz")
                with np.load(p,allow_pickle=False) as z:
                    original_B=z["original_B_source"].astype(bool)
                    outer=z["K8D_full_outer"].astype(bool)
                    box=tuple(int(v) for v in z["raw_global_roi_xyxy"])
                assert np.all(outer[original_B])
                olditems.append({"box":box,"mask":outer})
                used.append((int(obj.band_id),label))
                # exact original 128px B seeds must still be in union
                sub=mask[box[1]-roi[1]:box[3]-roi[1],
                         box[0]-roi[0]:box[2]-roi[0]]
                assert sub.shape==original_B.shape
                assert np.all(sub[original_B])
                assert np.all(ref_grid[box[1]-roi[1]:box[3]-roi[1],
                                      box[0]-roi[0]:box[2]-roi[0]][original_B]==label)
            rebuilt_roi,rebuilt=union_global(olditems)
            assert roi==rebuilt_roi
            assert np.array_equal(rebuilt,mask)
            assert int(mask.sum())<=int(obj.original_K8D_masks_sum_px2)
            assert int(obj.original_K8D_masks_sum_px2-mask.sum())==int(
                obj.duplicate_pixels_removed_from_area_sum)
            assert embedded==([int(float(x)) for x in str(obj.embedded_B_labels_TO_REVIEW).split(";")
                              if str(x).strip()])
            for label in embedded:
                # Embedded B source labels must be present in original B
                # label grid in selected candidates' RAW crops.
                assert np.any(ref_grid==label)
                e=json.loads(obj.embedded_source_membership_evidence)
                assert any(int(z["B_label"])==label and z["coverage"]>=.8
                           for z in e)
            srcmember=members[(members.group_id==obj.group_id)&
                              (members.role=="K8D_SELECTED_PROPOSAL")]
            assert set(srcmember.source_B_label)==set(source_selected)
            preview=out/"group_detail"/(obj.group_id+"_RAW_sources_exact_union.png")
            img=cv2.imdecode(np.frombuffer(preview.read_bytes(),np.uint8),1)
            assert img is not None and img.shape[1]==1056
        assert len(used)==len(set(used))==len(expected_original)
        assert set(used)==expected_original
        assert len(df)==(13 if frame==1 else 18)
        assert df.official_source_B_J5_IDs_merged.eq(False).all()
        assert sum(df.duplicate_pixels_removed_from_area_sum)==(0 if frame==1 else 369)
        if frame==2:
            z=df[(df.band_id==2)&df.selected_B_labels.astype(str).str.contains("1161")]
            assert len(z)==1
            v=z.iloc[0]
            assert set(map(int,v.selected_B_labels.split(";")))=={1148,1161}
            assert v.unique_outer_union_px2==370
            assert v.original_K8D_masks_sum_px2==739
            assert v.duplicate_pixels_removed_from_area_sum==369
            assert v.review_status=="MUTUAL_CONTOUR_NEAR_IDENTICAL_REVIEW"
            assert int(v.embedded_B_labels_TO_REVIEW)==1186
            z=df[(df.band_id==2)&(df.selected_B_labels.astype(str)=="626")]
            assert len(z)==1
            assert z.iloc[0].unique_outer_union_px2==348
            assert int(z.iloc[0].embedded_B_labels_TO_REVIEW)==658
            assert z.iloc[0].review_status=="EMBEDDED_B_SOURCE_REVIEW"
            z=df[(df.band_id==2)&(df.selected_B_labels.astype(str)=="1483")]
            assert len(z)==1 and z.iloc[0].unique_outer_union_px2==12
            assert not bool(z.iloc[0].provisional_main_MEDLARGE_eligible)
        summary=json.loads((out/"summary.json").read_text(encoding="utf-8"))
        assert summary["K8D_selected_proposals"]==len(used)
        assert summary["K8E_display_groups"]==len(df)
        assert summary["per_group_repeated_pixels_removed"]==sum(
               df.duplicate_pixels_removed_from_area_sum)
        assert summary["all_original_B_J5_and_prior_K8D_data_unmodified"]
        for p in out.glob("0?_*.png"):
            a=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),1)
            assert a is not None and a.shape[1]>1000
        source_j5=pd.read_csv(
            B/f"frame26_{frame}/original_J5_object_center_workband_classification.csv")
        assert len(source_j5)==(15604 if frame==1 else 4440)
        results.append({
            "frame":frame,"original_K8D_rows":len(used),"groups":len(df),
            "saved_union_matches_rebuilt_pixel_for_pixel":True,
            "double_counted_pixels_safely_removed":int(sum(df.duplicate_pixels_removed_from_area_sum)),
            "entire_original_B_and_J5_source_integrity_preserved":True,
            "member_external_full_seed_labels_still_review_only":True})
    status={
        "stage":"K8E_INDEPENDENT_PIXEL_EXACT_QA_PASS",
        "source_area_unit":"detector pixel squared, not object-plane micrometer squared",
        "all_official_source_masks_unchanged":True,
        "no_authenticated_defect_count":True,
        "results":results}
    p=E/"independent_QA.json"
    if p.exists():raise FileExistsError(p)
    p.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8E_INDEPENDENT_PIXEL_EXACT_QA_PASS",json.dumps(status,ensure_ascii=False),flush=True)

if __name__=="__main__":audit()
