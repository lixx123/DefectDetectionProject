"""K8I independent count, source and visibility reconciliation.

No rewriting any frozen source. Fails hard for unlabeled, orphaned or
user-unapproved candidate inadvertently presented as confirmed.
"""
from pathlib import Path
from collections import Counter
import json,sys,hashlib
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k8i_lineage_rules import LAYERS,parse_ids,j5_layer,b_layer,source_key
from scripts.run_case03k8i_full_frame_lineage import B,K,D,E,F,OUT,LAYERS_TO_IMAGES,ALL_B

def readpng(path):
    img=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if img is None:raise AssertionError("cannot decode image "+str(path))
    return img

def check_frame(frame):
    folder=OUT/f"frame26_{frame}"
    df=pd.read_csv(folder/"end_to_end_candidate_lineage.csv",encoding="utf-8-sig",
                   keep_default_na=False,dtype={'source_local_id':'string'})
    groups=pd.read_csv(folder/"K8E_review_group_register_all.csv",encoding="utf-8-sig",
                       keep_default_na=False)
    src_j5=pd.read_csv(B/f"frame26_{frame}/original_J5_object_center_workband_classification.csv",
                       encoding="utf-8-sig")
    src_c=pd.read_csv(K/f"frame26_{frame}/all_K8B_candidate_objects_complete_K8C_audit.csv",
                      encoding="utf-8-sig")
    assert len(df)==len(src_j5)+len(src_c)
    assert df.candidate_source_uid.nunique()==len(df)
    j=df[df.stage=="J5"];b=df[df.stage=="K8B"]
    assert len(j)==len(src_j5)==(15604 if frame==1 else 4440)
    assert len(b)==len(src_c)==(16766 if frame==1 else 3892)
    assert set(j.source_local_id)==set(src_j5.global_defect_id)
    assert df.original_source_pixels_preserved.eq(True).all()
    assert df.original_defect_ID_preserved.eq(True).all()
    assert df.not_an_independent_physical_defect_count.eq(True).all()
    assert df.primary_visibility_layer.isin(LAYERS).all()
    assert (df.primary_visibility_image!="").all()
    assert (b.secondary_all_B_reference_image==ALL_B).all()
    assert df.crosschannel_J5_B_association.eq(
       "NOT_EVALUATED_DO_NOT_ASSUME_DEDUPLICATION").all()
    assert not j.is_user_confirmed.any()
    # Rebuild original J5 source and grade by ID, including NONWORK;
    # do not count the 15,604/4,440 J5 source candidates as all WORK.
    jj=j.merge(src_j5,left_on="source_local_id",right_on="global_defect_id",
               validate="one_to_one")
    assert len(jj)==len(j)
    assert (jj.source_area_px2_x==jj.source_area_px2_y).all()
    assert (jj.size_grade==jj.grade).all()
    assert np.allclose(jj.source_max_Feret_px,jj.source_max_feret_px,
                       rtol=0,atol=.0001)
    assert (jj.primary_visibility_layer==[
         j5_layer(x,g) for x,g in zip(jj.K8A_region_code_by_original_J5_center,
                                      jj.grade)]).all()
    assert (jj.primary_visibility_layer=="J5_WORK_MEDLARGE").sum()==(25 if frame==1 else 26)
    assert (jj.primary_visibility_layer=="J5_WORK_SMALL").sum()==(658 if frame==1 else 372)
    assert (jj.primary_visibility_layer=="J5_OUTSIDE_WORK").sum()==(
          15604-683 if frame==1 else 4440-398)
    # Every original K8C source Band component exactly once with consistent
    # B key, source size, classification and full-res global bbox.
    b_for_join=b.copy()
    b_for_join['source_local_id']=b_for_join['source_local_id'].astype(int)
    bb=b_for_join.merge(src_c,left_on=["band_id","source_local_id"],
       right_on=["band_id","band_component_label"],how="outer",indicator=True,
       validate="one_to_one")
    # CSV B label may be a string, normalize before join when pandas infers.
    assert (bb._merge=="both").all()
    assert len(bb)==len(src_c)
    assert (bb.source_area_px2==bb.candidate_area_px2).all()
    assert bb.primary_visibility_layer.isin(LAYERS).all()
    assert (bb.source_bbox_x0==bb.bbox_local_x).all()
    assert (bb.source_bbox_y0==bb.candidate_global_y0).all()
    assert (bb.source_bbox_y1_exclusive==bb.candidate_global_y1_exclusive).all()
    assert bb.source_max_Feret_px.ge(1).all()
    assert (bb.primary_visibility_layer==[
        b_layer(klass,bool(novel),grade,tuple(str(group).split(';')) if group else (),
                {"K8E_F2_B2_G006","K8E_F2_B2_G009"} if frame==2 else set())
        for klass,novel,grade,group in zip(bb.classification,
                          bb.is_independent_of_fixed_H,bb.size_grade,bb.K8E_group_ids)]).all()
    assert len(groups)==(13 if frame==1 else 18)
    assert groups.group_id.nunique()==len(groups)
    assert groups.current_human_status.eq("USER_CONFIRMED").sum()==(0 if frame==1 else 2)
    expected_confirmed={626,658,1148,1161,1186} if frame==2 else set()
    assert set(b.loc[b.is_user_confirmed,"source_local_id"].astype(int))==expected_confirmed
    assert all((folder/path).exists() for path in df.primary_visibility_image.unique())
    summ=json.loads((folder/"render_visibility_reconciliation.json").read_text(encoding="utf-8"))
    assert summ["full_source_lineage_rows"]==len(df)
    assert summ["unrouted_source_ids"]==0 and summ["source_modified_pixels"]==0
    assert summ["K8D_processed_source_count"]==(13 if frame==1 else 19)
    assert sum(summ["layer_counts"].values())==len(df)
    assert dict(Counter(df.primary_visibility_layer))=={
        name:n for name,n in summ["layer_counts"].items() if n}
    assert summ["crosschannel_J5_K8B_official_dedup_performed"] is False
    assert summ["original_source_data_files_modified"] is False
    k8d=pd.read_csv(D/f"frame26_{frame}/all_K8D_original_vs_outer_review.csv")
    reviewed={(int(z.band_id),int(z.candidate_label)) for z in k8d.itertuples()}
    trial=set((int(x.band_id),int(x.source_local_id)) for x in b[b.K8D_outer_processed].itertuples())
    assert trial==reviewed
    for grp in groups.itertuples(index=False):
        origin=E/f"frame26_{frame}/group_detail"/(grp.group_id+"_EXACT_GROUP_MASK.npz")
        assert origin.exists()
        with np.load(origin,allow_pickle=False) as z:
            assert int((z["review_outer"]>0).sum())==grp.raw_outer_trial_union_area_px2
        attached=set(parse_ids(grp.selected_source_B_labels)) | set(
                     parse_ids(grp.embedded_source_B_labels))
        for label in attached:
            ref=b[(b.band_id==grp.band_id)&(b.source_local_id.astype(int)==label)]
            assert len(ref)==1
            assert grp.group_id in str(ref.K8E_group_ids.iloc[0]).split(";")
    if frame==1:
        for label in [614,1273,1562,1902]:
            q=b[(b.band_id==2)&(b.source_local_id.astype(int)==label)]
            assert len(q)==1
            assert q.iloc[0].primary_visibility_layer=="B_K8E_GROUP_PENDING"
            assert q.iloc[0].is_user_confirmed==False
    else:
        for gid in ("K8E_F2_B2_G006","K8E_F2_B2_G009"):
            assert len(groups[(groups.group_id==gid)&
                              (groups.current_human_status=="USER_CONFIRMED")])==1
    for name in summ["render"]["image_files"]:
        p=folder/name
        image=readpng(p)
        scale=4 if "1to4" in name else 8
        assert image.shape[:2]==(
          (C.RAW_HEIGHT+scale-1)//scale+88,
          (C.RAW_WIDTH+scale-1)//scale)
    assert summ["render"]["source_pixel_reference_8x"]["ALL_B"]==sum(
         int(readpng(B/f"frame26_{frame}"/
         f"band_{bid:02d}_B_hysteresis_mask_cropped.png").astype(bool).sum())
         for bid in sorted(src_c.band_id.unique()))
    result={"frame":frame,"J5_all":len(j),"B_all":len(b),
        "K8E_groups":len(groups),"K8D_selected":len(trial),
        "all_J5_and_B_source_ids_exact":True,
        "all_original_B_pixel_counts_in_full_reference":True,
        "all_sources_placed_in_one_reviewable_layer":True,
        "all_existing_visual_layers_valid_png":True,
        "firstframe_band2_B614_1273_1562_1902_visible":frame==1,
        "frame2_two_user_approved_K8E_groups_preserved":frame==2,
        "original_detection_masks_and_sources_unchanged":True}
    print("K8I_FRAME_PIXEL_AND_SOURCE_QA_PASS",json.dumps(result,ensure_ascii=False),flush=True)
    return result

def main():
    results=[check_frame(frame) for frame in (1,2)]
    report={"stage":"K8I_INDEPENDENT_FULL_CANDIDATE_LINEAGE_QA_PASS",
            "crosschannel_J5_B_dedup_not_yet_done":True,
            "not_all_B_have_K8D_RAW_outer":True,
            "physical_true_defect_count_NOT_claimed":True,
            "results":results}
    dest=OUT/"independent_QA.json"
    if dest.exists():raise FileExistsError(dest)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8I_INDEPENDENT_FULL_CANDIDATE_LINEAGE_QA_PASS",flush=True)

if __name__=="__main__":main()
