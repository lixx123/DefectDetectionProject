"""Audit exact RAW locations from 10-ROI manual exports, WITHOUT re-training.

Pair point and polygon within same annotated area to avoid double counting.
Report 170/230DN source H pixel occupancy, precise existing candidate IDs and
three-state Case03D decision at the clicked coordinate. Never infer polygon
as final physical defect boundary, or assume one H component = one object.
"""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
import cv2
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.thresholding import load_packed_mask
from src.detection.candidate_contour_export import exact_candidate_submask

DL=Path(r"C:\Users\lixia\Downloads")
CSV=DL/"case03d_true_target_10roi_locations.csv"
JSON=DL/"case03d_true_target_10roi_backup.json"
RUN=ROOT/"outputs/case03d_autodetect/run_20261009_autodetect_final"
MASKDIR=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1"
MANIFEST=ROOT/"outputs/case03d_manual_review_analysis/run_20261010_092200/ten_roi_true_target_click_annotation/ten_roi_manifest.csv"
DEST=ROOT/"outputs/case03d_true_target_analysis/run_20261010_manual_10roi_matching"
STATUS_CODES={0:"no_H_threshold_candidate",1:"noise_like_retained",2:"uncertain_review",3:"detected_provisional"}
SCOPE_DISPUTE="H_sample26_0452065"


def fingerprint(p:Path)->dict:
    z=p.stat()
    h=hashlib.sha256()
    with p.open("rb") as f:
        while x:=f.read(2**20):h.update(x)
    return {"path":str(p),"length_bytes":z.st_size,"sha256":h.hexdigest()}


def load_validated()->tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    rows=pd.read_csv(CSV,encoding="utf-8-sig",keep_default_na=False,dtype=str)
    backup=json.loads(JSON.read_text(encoding="utf-8-sig"))
    if backup.get("schema")!=1 or backup.get("source")!="case03d_10roi_true_target_click_annotation":
        raise ValueError("wrong JSON annotation source")
    if backup.get("raw_image_shape_wh")!=[11276,9200] or backup.get("source_ROI_size_px")!=160:
        raise ValueError("wrong RAW size or ROI coordinate system")
    if backup.get("parent_H_ID_is_not_target_ID") is not True:
        raise ValueError("parent H id not explicitly independent of target")
    if len(rows)!=22 or set(rows.annotation_kind)!={"point","poly"}:
        raise ValueError("unexpected CSV annotations")
    groups=rows.groupby("source_parent_H_candidate_id")
    if len(groups)!=10 or groups.size().sum()!=22:
        raise ValueError("wrong annotated ROI population")
    manifest=pd.read_csv(MANIFEST,dtype=str,keep_default_na=False)
    if set(groups.groups)!=set(manifest.candidate_id):
        raise ValueError("annotated source ROI IDs fail known 10-case manifest")
    expected=[]
    for item in manifest.to_dict("records"):
        parent=item["candidate_id"]
        entry=backup["annotations"].get(parent)
        if entry is None:
            raise ValueError("missing JSON parent ROI")
        if (rows.loc[rows.source_parent_H_candidate_id==parent,"new_roi_note"]!=entry.get("note","")).any():
            raise ValueError("mismatched user note JSON/CSV")
        for ix,t in enumerate(entry["targets"],start=1):
            if t["kind"] not in ("point","poly"):
                raise ValueError("unsupported annotation")
            coords=[[int(item["roi_x0"])+int(x),int(item["roi_y0"])+int(y)] for x,y in t["points"]]
            sub=rows[(rows.source_parent_H_candidate_id==parent)&
                     (rows.target_index_in_roi==str(ix))]
            if len(sub)!=1:
                raise AssertionError(f"missing export target {parent}/{ix}")
            record=sub.iloc[0]
            if record.annotation_kind!=t["kind"] or json.loads(record.vertices_RAW_global_xy_JSON)!=coords:
                raise AssertionError("JSON and CSV geometry disagree")
            # Source coordinates must actually belong to the 160px ROI,
            # even when near the RAW frame outer boundary.
            if any(not(int(item["roi_x0"])<=x<int(item["roi_x0"])+160 and
                       int(item["roi_y0"])<=y<int(item["roi_y0"])+160) for x,y in coords):
                raise ValueError("annotated point outside raw crop")
            expected.append((parent,ix))
    if len(expected)!=len(rows):raise AssertionError("JSON/CSV enumeration mismatch")
    features=pd.read_csv(RUN/"candidate_decisions_full.csv",
        usecols=["candidate_id","area_px","bbox_x","bbox_y","bbox_w","bbox_h",
                 "centroid_x","centroid_y","peak_response_dn","triage_status"],
        dtype={"candidate_id":str},low_memory=False)
    if features.candidate_id.duplicated().any() or len(features)!=88043:
        raise ValueError("wrong H candidate population")
    return rows,manifest,features


def calc_candidate_overlap(df:pd.DataFrame,H:np.ndarray,region:np.ndarray,
                           *,origin:tuple[int,int])->list[dict]:
    """Map exact original H-connected components to a human polygon region."""
    y0,x0=origin
    hh,ww=region.shape
    intersect=df.loc[
        (df.bbox_x<x0+ww)&(df.bbox_x+df.bbox_w>x0)&
        (df.bbox_y<y0+hh)&(df.bbox_y+df.bbox_h>y0)
    ]
    records=[]
    all_hits=np.zeros_like(region,dtype=np.int16)
    for row in intersect.to_dict("records"):
        bx,by,bw,bh=(int(row[k]) for k in ("bbox_x","bbox_y","bbox_w","bbox_h"))
        xa=max(x0,bx);ya=max(y0,by)
        xb=min(x0+ww,bx+bw);yb=min(y0+hh,by+bh)
        if xb<=xa or yb<=ya:continue
        # exact mask protects against false matches from bbox intersections
        mask,_=exact_candidate_submask(H,row)
        poly=region[ya-y0:yb-y0,xa-x0:xb-x0]
        hit=mask[ya-by:yb-by,xa-bx:xb-bx].astype(bool)&poly
        count=int(hit.sum())
        if count:
            all_hits[ya-y0:yb-y0,xa-x0:xb-x0]+=hit.astype(np.int16)
            records.append({
                "candidate_id":row["candidate_id"],
                "triage_status":row["triage_status"],
                "candidate_full_H_area_px":int(row["area_px"]),
                "polygon_intersect_H_pixels":count,
                "candidate_peak_blackhat_dn":int(row["peak_response_dn"]),
                "centroid_x":float(row["centroid_x"]),
                "centroid_y":float(row["centroid_y"]),
            })
    # ROI H pixels must each be described by exactly one global component.
    if not np.array_equal(all_hits>0,region&H[y0:y0+hh,x0:x0+ww]):
        raise AssertionError("H pixels inside annotated region not exhausted by candidate mappings")
    if (all_hits>1).any():
        raise AssertionError("candidate H pixels counted twice")
    return sorted(records,key=lambda v:(-v["polygon_intersect_H_pixels"],v["candidate_id"]))


def find_candidate_at_point(df:pd.DataFrame,H:np.ndarray,x:int,y:int)->dict|None:
    rows=df.loc[(df.bbox_x<=x)&(df.bbox_x+df.bbox_w>x)&
        (df.bbox_y<=y)&(df.bbox_y+df.bbox_h>y)]
    hits=[]
    for rec in rows.to_dict("records"):
        mask,(bx,by,bw,bh)=exact_candidate_submask(H,rec)
        if mask[y-by,x-bx]:
            hits.append(rec)
    if H[y,x] and len(hits)!=1:
        raise AssertionError(f"selected pixel has {len(hits)} candidate IDs")
    if not H[y,x] and hits:
        raise AssertionError("point outside H yet maps to candidate")
    return hits[0] if hits else None


def draw_overlay(raw:np.ndarray,H:np.ndarray,S:np.ndarray,status:np.ndarray,
                 anns:list[dict],ox:int,oy:int,source:dict)->np.ndarray:
    sub=np.asarray(raw[oy:oy+160,ox:ox+160],dtype=np.float32)
    lo,hi=np.percentile(sub,[1,99.5]);hi=max(float(lo)+1,float(hi))
    g=np.uint8(np.rint(np.clip((sub-lo)/(hi-lo),0,1)*255))
    left=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
    right=left.copy()
    s=S[oy:oy+160,ox:ox+160]
    h=H[oy:oy+160,ox:ox+160]
    st=status[oy:oy+160,ox:ox+160]
    right[s]=(13,236,253)
    right[h&~s]=(254,205,30)
    # Annotation outlines on both RAW and existing H response, not pixel fill
    for item in anns:
        coords=np.asarray(json.loads(item["vertices_RAW_global_xy_JSON"]),dtype=np.int32)
        coords=coords-np.array([[ox,oy]],dtype=np.int32)
        if item["annotation_kind"]=="point":
            x,y=[int(v) for v in coords[0]]
            for image in (left,right):
                cv2.drawMarker(image,(x,y),(33,108,250),cv2.MARKER_CROSS,9,1)
        else:
            for image in (left,right):
                cv2.polylines(image,[coords.reshape(-1,1,2)],True,
                              (72,238,48),1,cv2.LINE_AA)
    bx=int(source["bbox_x"])-ox;by=int(source["bbox_y"])-oy
    for img in (left,right):
        cv2.rectangle(img,(bx,by),(bx+int(source["bbox_w"])-1,
            by+int(source["bbox_h"])-1),(21,74,231),1)
    output=np.full((213,334,3),250,np.uint8)
    output[35:195,0:160]=left
    output[35:195,174:334]=right
    cv2.putText(output,"RAW + MANUAL",(2,17),cv2.FONT_HERSHEY_SIMPLEX,.40,(36,48,65),1,cv2.LINE_AA)
    cv2.putText(output,"S/H + MANUAL",(174,17),cv2.FONT_HERSHEY_SIMPLEX,.40,(36,48,65),1,cv2.LINE_AA)
    cv2.putText(output,str(source["candidate_id"])[-13:],(4,209),
                cv2.FONT_HERSHEY_SIMPLEX,.39,(48,60,65),1,cv2.LINE_AA)
    return output


def main():
    if DEST.exists():raise FileExistsError("do not overwrite prior audit")
    DEST.mkdir(parents=True)
    rows,manifest,features=load_validated()
    protected=[CSV,JSON,MANIFEST,RUN/"candidate_decisions_full.csv"]
    before=[fingerprint(p) for p in protected]
    H=load_packed_mask(MASKDIR/"fused_H_TL170_TH230.npz")
    S=load_packed_mask(MASKDIR/"fused_S_TL230_TH230.npz")
    with np.load(RUN/"candidate_status_map_lossless.npz",allow_pickle=False) as z:
        status=z["class_map"]
    if not(H.shape==S.shape==status.shape==(9200,11276) and np.array_equal(status>0,H)):
        raise AssertionError("source pixel class map not equal original H")
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    if raw.shape!=H.shape:raise AssertionError("RAW/mask mismatch")
    results=[];figures=[];point_summaries=[]
    for meta in manifest.to_dict("records"):
        src=meta["candidate_id"]
        one=rows[rows.source_parent_H_candidate_id==src].sort_values(
            "target_index_in_roi",key=lambda x:x.astype(int))
        ox,oy=int(meta["roi_x0"]),int(meta["roi_y0"])
        fig=draw_overlay(raw,H,S,status,one.to_dict("records"),ox,oy,meta)
        figures.append(fig)
        for row in one.to_dict("records"):
            all_points=json.loads(row["vertices_RAW_global_xy_JSON"])
            x,y=int(row["raw_x"]),int(row["raw_y"])
            hstate=int(status[y,x])
            item={
                "source_parent_H_candidate_id":src,
                "source_parent_H_label":row["source_h_manual_label"],
                "user_new_roi_note":row["new_roi_note"],
                "annotation_number":int(row["target_index_in_roi"]),
                "annotation_kind":row["annotation_kind"],
                "clicked_or_estimated_x":x,"clicked_or_estimated_y":y,
                "clicked_point_H_status":STATUS_CODES[hstate],
                "clicked_point_in_S230":bool(S[y,x]),
                "clicked_point_in_H170_230":bool(H[y,x]),
                "target_verified_anomaly":False if src==SCOPE_DISPUTE else None,
                "annotation_conflict":src==SCOPE_DISPUTE,
                "current_is_algorithmic_segmentation_not_physical_ground_truth":True,
            }
            # Point x/y is directly clicked; polygon x/y is a bbox mid-point
            # rounded and need not lie in the polygon nor on actual target.
            if row["annotation_kind"]=="point":
                matched=find_candidate_at_point(features,H,x,y)
                item["exact_H_component_ID_at_clicked_pixel"]=(
                    matched["candidate_id"] if matched else "")
                item["exact_H_component_status_at_clicked_pixel"]=(
                    matched["triage_status"] if matched else "")
                item["matched_H_component_area_px"]=(
                    int(matched["area_px"]) if matched else "")
                point_summaries.append(item)
                item.update({
                    "manual_polygon_shoelace_area_px2":"",
                    "rasterized_polygon_pixel_area":"",
                    "original_H_pixel_coverage_fraction":"",
                    "H_overlap_pixel_count":"",
                    "S230_overlap_pixel_count":"",
                    "polygon_detected_pixel_count":"",
                    "polygon_uncertain_pixel_count":"",
                    "polygon_noise_like_pixel_count":"",
                    "number_H_components_touching_polygon":"",
                    "top_matching_H_component_ID":"",
                    "top_matching_H_component_status":"",
                    "top_matching_H_component_overlap_px":"",
                    "all_H_component_matches_JSON":"[]",
                    "H_recall_proxy_NOT_VALID":True
                })
            else:
                contour=np.asarray(all_points,dtype=np.int32).reshape(-1,1,2)
                pts=np.asarray(all_points,dtype=np.int32)
                mini=np.zeros((160,160),dtype=np.uint8)
                local=pts-np.array([ox,oy])
                cv2.fillPoly(mini,[local.reshape(-1,1,2)],color=1)
                region=mini.astype(bool)
                if not region.any():raise AssertionError("poly raster empty")
                actual=H[oy:oy+160,ox:ox+160]
                selected=status[oy:oy+160,ox:ox+160]
                strong=S[oy:oy+160,ox:ox+160]
                matches=calc_candidate_overlap(features,H,region,origin=(oy,ox))
                n_h=int(np.count_nonzero(actual&region))
                if sum(o["polygon_intersect_H_pixels"] for o in matches)!=n_h:
                    raise AssertionError("poly H-match conservation failure")
                item.update({
                    "exact_H_component_ID_at_clicked_pixel":"",
                    "exact_H_component_status_at_clicked_pixel":"",
                    "matched_H_component_area_px":"",
                    "manual_polygon_shoelace_area_px2":float(row["manual_approx_area_px2"]),
                    "rasterized_polygon_pixel_area":int(region.sum()),
                    "original_H_pixel_coverage_fraction":round(n_h/int(region.sum()),5),
                    "H_overlap_pixel_count":n_h,
                    "S230_overlap_pixel_count":int(np.count_nonzero(strong&region)),
                    "polygon_detected_pixel_count":int(np.count_nonzero((selected==3)&region)),
                    "polygon_uncertain_pixel_count":int(np.count_nonzero((selected==2)&region)),
                    "polygon_noise_like_pixel_count":int(np.count_nonzero((selected==1)&region)),
                    "number_H_components_touching_polygon":len(matches),
                    "top_matching_H_component_ID":matches[0]["candidate_id"] if matches else "",
                    "top_matching_H_component_status":matches[0]["triage_status"] if matches else "",
                    "top_matching_H_component_overlap_px":matches[0]["polygon_intersect_H_pixels"] if matches else 0,
                    "all_H_component_matches_JSON":json.dumps(matches,ensure_ascii=False),
                    "H_recall_proxy_NOT_VALID":True
                })
            results.append(item)
    fig=np.full((5*231,2*349,3),245,dtype=np.uint8)
    for i,img in enumerate(figures):
        x=(i%2)*349;y=(i//2)*231
        fig[y:y+img.shape[0],x:x+img.shape[1]]=img
    ok,encoded=cv2.imencode(".png",fig)
    if not ok:raise IOError("montage encoding")
    (DEST/"10roi_manual_polygons_vs_H_segmentation.png").write_bytes(encoded.tobytes())
    audit=pd.DataFrame(results)
    audit.to_csv(DEST/"22_annotations_exact_H_crosscheck.csv",index=False,
                 encoding="utf-8-sig")
    pts=pd.DataFrame(point_summaries)
    pts.to_csv(DEST/"11_clicked_points_class_status.csv",index=False,
               encoding="utf-8-sig")
    polys=audit[audit.annotation_kind=="poly"].copy()
    polys.to_csv(DEST/"11_polygon_vs_actual_H_components.csv",index=False,
                 encoding="utf-8-sig")
    # One physical target per polygon, with one extra polygon in the
    # 2-spots ROI; point pins are not counted a second time.
    if len(polys)!=11 or len(pts)!=11:
        raise AssertionError("expected 11 target polygons and 11 point pins")
    conflicted=polys[polys.annotation_conflict.astype(bool)]
    if len(conflicted)!=1 or conflicted.iloc[0].source_parent_H_candidate_id!=SCOPE_DISPUTE:
        raise AssertionError("missing user explicit no-anomaly contradiction")
    status_counts=pts.clicked_point_H_status.value_counts().to_dict()
    source_counts=polys.top_matching_H_component_status.value_counts().to_dict()
    weak=polys.sort_values("original_H_pixel_coverage_fraction").loc[:,
        ["source_parent_H_candidate_id","annotation_number",
         "original_H_pixel_coverage_fraction",
         "top_matching_H_component_ID","top_matching_H_component_status",
         "H_overlap_pixel_count","rasterized_polygon_pixel_area"]].to_dict("records")
    summary={
      "status":"AUDIT_FINISHED_NO_AUTOMATIC_RELABELLING",
      "raw_source":str(CSV),"json_source":str(JSON),
      "csv_json_consistent_and_geometry_verified":True,
      "annotated_raw_ROIs":10,"user_annotation_rows":len(rows),
      "clicked_point_marks":len(pts),"hand_drawn_polygon_marks":len(polys),
      "distinct_user_polygon_regions":11,
      "physical_truth_reliable_target_count":"NOT_YET_ESTABLISHED",
      "confirmed_source_note_conflict":{
          "parent_candidate_id":SCOPE_DISPUTE,
          "new_user_note":"无异常",
          "action":"do not treat its one point and one polygon as positive ground truth"
      },
      "point_pixel_status_counts":{k:int(status_counts.get(k,0)) for k in STATUS_CODES.values()},
      "polygon_dominant_H_status_counts":{k:int(source_counts.get(k,0)) for k in
          ["detected_provisional","uncertain_review","noise_like_retained",""]},
      "polygon_coverage_sorted_ascending":weak,
      "detector_pixel_pitch_um":float(cfg.PIXEL_SIZE_UM),
      "object_plane_pixel_size_um":"NOT_CALIBRATED",
      "size_grade_thresholds":"NOT_DEFINED",
      "no_algorithm_or_human_labels_changed":True,
      "not_full_image_detection_recall":True
    }
    (DEST/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),
                                     encoding="utf-8")
    after=[fingerprint(p) for p in protected]
    if after!=before:raise AssertionError("source CSV/JSON/H metadata was modified")
    (DEST/"source_manifest.json").write_text(
        json.dumps({"inputs_before":before,"inputs_after":after,
                    "source_files_unchanged":True},ensure_ascii=False,indent=2),
        encoding="utf-8"
    )
    print("TARGET_AUDIT_DIR",DEST)
    print("POINT_STATUS_COUNTS",status_counts)
    print("POLYGON_TOP_STATUS_COUNTS",source_counts)
    print("TARGET_AUDIT_SUMMARY",json.dumps(summary,ensure_ascii=True))


if __name__=="__main__":main()
