"""Case03-K8I: two-frame full-resolution candidate lineage and layered display.

Read existing immutable J5/K8B/K8C/K8D/K8E/K8F artifacts. Process every
work-band B connected component and all original J5 objects, not merely the
32 K8D hand-reviewed candidates. This does NOT run new RAW contours for all
components or claim independent defects. All existing source masks untouched.
"""
from pathlib import Path
from collections import Counter,defaultdict
from dataclasses import asdict
import sys,json,hashlib,math
import cv2,numpy as np,pandas as pd
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k8i_lineage_rules import (
    LAYERS,parse_ids,b_layer,j5_layer,source_key,validate_lineage,audit_layer_counts)
from src.detection.case03i_size_grade import SizeGradeConfig,max_feret_centers_px,grade_size
from src.detection.case03k8g_display_boxes import (
    expand_bbox_xyxy,bbox_to_display_px,arrange_labels)
from scripts.run_case03k8g_1p5_display_boxes import background,write_lossless
A=C.OUTPUT_ROOT/"case03k8a_auto_workband_masks/run_20261013_26twoframes_variableband_v2"
B=C.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
K=C.OUTPUT_ROOT/"case03k8c_band_supplement_review/run_20261013_f1_f2_allbands_reversible_v2"
D=C.OUTPUT_ROOT/"case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3"
E=C.OUTPUT_ROOT/"case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1"
F=C.OUTPUT_ROOT/"case03k8f_confirmed_group_register/run_20261014_F26_2_two_user_approved_G006_G009_v2"
OUT=C.OUTPUT_ROOT/"case03k8i_full_frame_lineage/run_20261015_sample26_2frames_fullcandidate_lineage_v1"
CONF=SizeGradeConfig()
FONT="C:/Windows/Fonts/msyh.ttc"
PITCH=float(C.PIXEL_SIZE_UM)
PALETTE={
 "J5_WORK_MEDLARGE":(42,54,244),"J5_WORK_SMALL":(44,222,67),
 "J5_OUTSIDE_WORK":(180,120,180),"B_FIXED_H_REFERENCE":(185,148,88),
 "B_NOVEL_MICRO":(112,138,215),"B_NOVEL_SMALL":(61,225,112),
 "B_NOVEL_MEDLARGE":(36,146,245),
 "B_K8E_GROUP_PENDING":(32,175,246),
 "B_K8E_GROUP_CONFIRMED":(235,219,38),
 "B_K8E_MULTIGROUP_CONFLICT":(40,75,250)}
MAIN="01_MAIN_J5_plus_confirmed_plus_unapproved_MEDLARGE_1to4.png"
REVIEW="02_ALL_K8E_PENDING_AND_CONFLICT_GROUPS_1to4.png"
SMALL="03_ALL_SMALL_J5_AND_NOVEL_B_1to4.png"
MICRO="04_K8C_MICRO_SUGGEST_HIDE_NOT_DELETED_1to4.png"
FIXED="05_K8B_FIXED_H_OVERLAP_REFERENCE_1to8.png"
OUTSIDE="06_J5_OUTSIDE_WORK_REVIEW_REFERENCE_1to8.png"
ALL_B="07_ALL_K8B_B_SOURCE_PIXELS_reference_1to8.png"
LAYERS_TO_IMAGES={
 "J5_WORK_MEDLARGE":MAIN,"J5_WORK_SMALL":SMALL,
 "J5_OUTSIDE_WORK":OUTSIDE,
 "B_FIXED_H_REFERENCE":FIXED,"B_NOVEL_MICRO":MICRO,
 "B_NOVEL_SMALL":SMALL,"B_NOVEL_MEDLARGE":MAIN,
 "B_K8E_GROUP_PENDING":REVIEW,
 "B_K8E_GROUP_CONFIRMED":MAIN,
 "B_K8E_MULTIGROUP_CONFLICT":REVIEW,
}
EXTERNAL_APPROVED={"K8E_F2_B2_G006","K8E_F2_B2_G009"}
def decode(path):
    im=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if im is None:raise IOError(path)
    return im

def msg(img,title,sub,stride):
    h,w=img.shape[:2]
    banner=Image.new("RGB",(w,88),(25,25,25))
    painter=ImageDraw.Draw(banner)
    a=ImageFont.truetype(FONT,18 if stride==4 else 15)
    b=ImageFont.truetype(FONT,14 if stride==4 else 12)
    painter.text((9,8),title,fill=(246,246,245),font=a)
    painter.text((9,42),sub,fill=(221,225,221),font=b)
    painter.text((9,66),"整图候选是试验提案；未确认者保留复核。3.2μm仅探测器像面当量。",fill=(213,216,216),font=b)
    return np.vstack((cv2.cvtColor(np.asarray(banner),cv2.COLOR_RGB2BGR),img))

def routes_and_sources(frame):
    frameout=OUT/f"frame26_{frame}"
    frameout.mkdir()
    original_J5=pd.read_csv(B/f"frame26_{frame}/original_J5_object_center_workband_classification.csv",
                            encoding="utf-8-sig")
    candidates=pd.read_csv(K/f"frame26_{frame}/all_K8B_candidate_objects_complete_K8C_audit.csv",
                            encoding="utf-8-sig")
    j5_expected=15604 if frame==1 else 4440
    assert len(original_J5)==j5_expected
    bmeta=json.loads((B/f"frame26_{frame}/summary.json").read_text(encoding="utf-8"))
    k8a_meta=json.loads((A/f"frame26_{frame}/audit.json").read_text(encoding="utf-8"))
    band_specs=bmeta["ROI_crops"]
    bandset={int(s["band_id"]) for s in band_specs}
    assert bandset=={int(b["band_id"]) for b in k8a_meta["bands"]}
    assert len(bandset)==k8a_meta["bands_detected_automatic"]
    assert set(map(int,candidates.band_id.unique()))==bandset
    oldgroups=pd.read_csv(E/f"frame26_{frame}/K8E_unique_group_union_measurements.csv",
                           encoding="utf-8-sig")
    approved=EXTERNAL_APPROVED if frame==2 else set()
    assert set(oldgroups.group_id).issuperset(approved)
    k8d_rows=pd.read_csv(D/f"frame26_{frame}/all_K8D_original_vs_outer_review.csv",
                         encoding="utf-8-sig")
    assert len(k8d_rows)==(13 if frame==1 else 19)
    # selected K8D label cross-references must be exactly included in K8E.
    link=defaultdict(set)
    association_role=defaultdict(set)
    for g in oldgroups.itertuples(index=False):
        gid=str(g.group_id)
        sel=parse_ids(g.selected_B_labels)
        emb=parse_ids(g.embedded_B_labels_TO_REVIEW)
        assert sel and set(sel).isdisjoint(emb)
        for label in sel:
            key=(int(g.band_id),label);link[key].add(gid);association_role[key].add("K8D_SELECTED")
        for label in emb:
            key=(int(g.band_id),label);link[key].add(gid);association_role[key].add("B_EMBEDDED_REVIEW_ONLY")
    historical={(int(x.band_id),int(x.candidate_label)) for x in k8d_rows.itertuples(index=False)}
    proposed=set()
    for g in oldgroups.itertuples(index=False):
        proposed|={(int(g.band_id),x) for x in parse_ids(g.selected_B_labels)}
    assert historical==proposed
    # Source of user approval checked against frozen K8F, NEVER from K8E's
    # empty human_confirm fields alone.
    recorded=pd.read_csv(F/f"frame26_{frame}/workband_unified_candidate_review_register.csv",
                         encoding="utf-8-sig")
    accepted=set(recorded.loc[recorded.source=="K8F_USER_APPROVED_K8E_OUTER",
                              "supplement_K8E_group_id"])
    assert accepted==approved

    rows=[];groups_out=[];band_images={}
    for o in original_J5.itertuples(index=False):
        typ=j5_layer(o.K8A_region_code_by_original_J5_center,str(o.grade))
        rec={"candidate_source_uid":source_key("J5",frame,0,o.global_defect_id),
             "stage":"J5","frame":frame,"band_id":int(o.K8A_workband_id_by_original_J5_center),
             "source_local_id":str(o.global_defect_id),
             "primary_visibility_layer":typ,
             "primary_visibility_image":LAYERS_TO_IMAGES[typ],
             "secondary_all_B_reference_image":"",
             "source_area_px2":int(o.source_area_px2),
             "source_max_Feret_px":round(float(o.source_max_feret_px),4),
             "size_grade":str(o.grade),"source_bbox_x0":int(o.source_bbox_x_global),
             "source_bbox_y0":int(o.source_bbox_y_global),
             "source_bbox_x1_exclusive":int(o.source_bbox_x_global+o.source_bbox_width_px),
             "source_bbox_y1_exclusive":int(o.source_bbox_y_global+o.source_bbox_height_px),
             "source_center_x":float(o.center_x_global),"source_center_y":float(o.center_y_global),
             "display_bbox_x0":int(o.display_bbox_x_global),
             "display_bbox_y0":int(o.display_bbox_y_global),
             "display_bbox_x1_exclusive":int(o.display_bbox_xmax_inclusive)+1,
             "display_bbox_y1_exclusive":int(o.display_bbox_ymax_inclusive)+1,
             "source_classification":"J5_FROZEN_FIXED_H",
             "K8E_group_ids":"","K8D_outer_processed":False,
             "K8C_noise_review_classification":"",
             "crosschannel_J5_B_association":"NOT_EVALUATED_DO_NOT_ASSUME_DEDUPLICATION",
             "user_confirmation_state":"NOT_REVIEWED",
             "is_user_confirmed":False,
             "original_source_pixels_preserved":True,
             "original_defect_ID_preserved":True,
             "not_an_independent_physical_defect_count":True,
             "reason_for_visibility":("J5_WORK_SOURCE_SIZE" if typ!="J5_OUTSIDE_WORK"
                else "J5_CENTER_OUTSIDE_WORK_STILL_IN_OUTSIDE_REFERENCE")}
        rows.append(rec)
    for spec in band_specs:
        band=int(spec["band_id"])
        y0=int(spec["ROI_global_xyxy"][1]);y1=int(spec["ROI_global_xyxy"][3])
        bm=decode(B/f"frame26_{frame}/band_{band:02d}_B_hysteresis_mask_cropped.png")
        assert bm.shape==(y1-y0,C.RAW_WIDTH)
        assert set(np.unique(bm)).issubset({0,255})
        n,labels,stats,centers=cv2.connectedComponentsWithStats(np.uint8(bm>0),8)
        part=candidates[candidates.band_id==band]
        assert len(part)==n-1
        assert set(part.band_component_label)==set(range(1,n))
        look={}
        source_lut=np.zeros(n,np.uint8)
        # codes mapped below to pure color pixel layers.
        for obj in part.itertuples(index=False):
            lid=int(obj.band_component_label)
            x,y,w,h,area=[int(v) for v in stats[lid,:5]]
            assert area==int(obj.candidate_area_px2),(
                "K8C source connected component area changed",frame,band,lid)
            assert (x,y,w,h)==(int(obj.bbox_local_x),int(obj.bbox_local_y),
                               int(obj.bbox_width_px),int(obj.bbox_height_px))
            groups=sorted(link.get((band,lid),set()))
            # The perimeter upper bound limits expensive exact Feret geometry
            # to candidates that could plausibly be MEDIUM or LARGE.
            high=math.hypot(w-1,h-1)
            if area>=CONF.medium_area_min_px2 or high>=CONF.medium_length_min_px:
                cropped=labels[y:y+h,x:x+w]==lid
                yy,xx=np.nonzero(cropped)
                feret=max_feret_centers_px(np.column_stack([xx,yy]))
            else:feret=1.
            grade,_=grade_size(area,feret,CONF)
            novel=bool(obj.is_independent_of_fixed_H)
            route=b_layer(str(obj.classification),novel,grade,groups,approved)
            if (band,lid) in historical:assert groups
            confirmed=route=="B_K8E_GROUP_CONFIRMED"
            if confirmed:assert groups[0] in approved
            uid=source_key("K8B",frame,band,lid)
            rec={"candidate_source_uid":uid,"stage":"K8B","frame":frame,"band_id":band,
                 "source_local_id":str(lid),"primary_visibility_layer":route,
                 "primary_visibility_image":LAYERS_TO_IMAGES[route],
                 "secondary_all_B_reference_image":ALL_B,
                 "source_area_px2":area,"source_max_Feret_px":round(float(feret),4),
                 "size_grade":grade,
                 "source_bbox_x0":x,"source_bbox_y0":y+y0,
                 "source_bbox_x1_exclusive":x+w,"source_bbox_y1_exclusive":y+y0+h,
                 "source_center_x":float(centers[lid,0]),
                 "source_center_y":float(centers[lid,1])+y0,
                 "display_bbox_x0":x,"display_bbox_y0":y+y0,
                 "display_bbox_x1_exclusive":x+w,"display_bbox_y1_exclusive":y+y0+h,
                 "source_classification":"K8B_ADAPTIVE_H_EXPERIMENT",
                 "K8E_group_ids":";".join(groups),
                 "K8D_outer_processed":(band,lid) in historical,
                 "K8C_noise_review_classification":str(obj.classification),
                 "crosschannel_J5_B_association":"NOT_EVALUATED_DO_NOT_ASSUME_DEDUPLICATION",
                 "user_confirmation_state":("USER_CONFIRMED_VIA_GROUP" if confirmed
                      else "PENDING_REVIEW"),
                 "is_user_confirmed":confirmed,
                 "original_source_pixels_preserved":True,
                 "original_defect_ID_preserved":True,
                 "not_an_independent_physical_defect_count":True,
                 "reason_for_visibility":(f"K8E_{';'.join(groups)}" if groups else
                     "K8C_MICRO_SUGGESTION_RETAIN" if route=="B_NOVEL_MICRO"
                     else "K8B_A_FIXED_BRANCH_REFERENCE" if route=="B_FIXED_H_REFERENCE"
                     else "K8B_NOVEL_TRIAL_SIZE_REVIEW")}
            rows.append(rec)
            look[lid]=rec
        band_images[band]={"labels":labels,"band_y0":y0,"n":n,
                           "perlabel":look,"source_mask_pixels":int(np.count_nonzero(bm))}
        print("K8I_BAND_LINEAGE",frame,band,n-1,flush=True)
    audit=validate_lineage(rows)
    expected_B=len(candidates)
    assert len(rows)==j5_expected+expected_B
    observed={(int(x["band_id"]),int(x["source_local_id"]))
               for x in rows if x["stage"]=="K8B"}
    assert len(observed)==expected_B
    for g in oldgroups.to_dict("records"):
        groupid=str(g["group_id"])
        approved_grp=groupid in approved
        groups_out.append({
            "group_id":groupid,"frame":frame,"band_id":int(g["band_id"]),
            "selected_source_B_labels":";".join(map(str,parse_ids(g["selected_B_labels"]))),
            "embedded_source_B_labels":";".join(map(str,parse_ids(g["embedded_B_labels_TO_REVIEW"]))),
            "raw_outer_trial_union_area_px2":int(g["unique_outer_union_px2"]),
            "raw_outer_trial_length_image_um":float(g["union_length_detector_um_PROVISIONAL"]),
            "raw_outer_size_grade_PROVISIONAL":str(g["trial_size_grade"]),
            "source_K8E_review_status":str(g["review_status"]),
            "current_human_status":"USER_CONFIRMED" if approved_grp else "PENDING_REVIEW",
            "display_in_MEDLARGE_main":bool(g["trial_size_grade"] in ("MEDIUM","LARGE")),
            "is_production_defect":False,
            "original_source_B_and_J5_IDs_unchanged":True,
            "has_unresolved_cross_channel_J5_overlap":True,
            "source_exact_mask":str(E/f"frame26_{frame}/group_detail"/(
                    groupid+"_EXACT_GROUP_MASK.npz"))})
    pd.DataFrame(rows).to_csv(frameout/"end_to_end_candidate_lineage.csv",
                              encoding="utf-8-sig",index=False)
    pd.DataFrame(groups_out).to_csv(frameout/"K8E_review_group_register_all.csv",
                                    encoding="utf-8-sig",index=False)
    return rows,groups_out,band_images,{"j5":j5_expected,"B":expected_B,
                "nwork_J5":int((original_J5.K8A_region_code_by_original_J5_center==2).sum()),
                "original_j5":original_J5,"sources":audit}

def put_title(base,title,sub,stride,path):
    write_lossless(path,msg(base,title,sub,stride))

def draw_box(canvas,bbox,stride,color):
    W,H=canvas.shape[1],canvas.shape[0]
    r=expand_bbox_xyxy(bbox,(C.RAW_WIDTH,C.RAW_HEIGHT),1.5)
    x,y,xx,yy=bbox_to_display_px(r,(C.RAW_WIDTH,C.RAW_HEIGHT),(W,H),stride)
    cv2.rectangle(canvas,(x,y),(xx,yy),color,1,cv2.LINE_8)
    return (x,y,xx,yy)

def draw_pending_or_new(img,stride,rows,groups,frame):
    annotations=[]
    approved=set(EXTERNAL_APPROVED if frame==2 else [])
    # The original J5 MED/LARGE rectangles are frozen; never infer a raw
    # contour from their 1.5x DISPLAY bbox.
    for item in rows:
        if item["stage"]=="J5" and item["primary_visibility_layer"]=="J5_WORK_MEDLARGE":
            a=[item[k] for k in ("display_bbox_x0","display_bbox_y0",
                 "display_bbox_x1_exclusive","display_bbox_y1_exclusive")]
            b=draw_box(img,a,stride,(38,46,241) if item["size_grade"]=="LARGE"
                       else (29,210,237))
            annotations.append((b, f"{item['source_local_id']} "
                 f"A={item['source_area_px2']}px² "
                 f"L={item['source_max_Feret_px']*PITCH:.1f}μm(像面)","J5"))
    # Every K8E group is visible in the K8I review image regardless of
    # whether it has been human-approved; MED/LARGE also visible on MAIN.
    for g in groups:
        gid=g["group_id"]
        path=E/f"frame26_{frame}/group_detail"/(
            gid+"_EXACT_GROUP_MASK.npz")
        with np.load(path,allow_pickle=False) as z:
            r=z["roi_xyxy"];mask=z["review_outer"].astype(bool)
            y,x=np.where(mask)
            assert int(mask.sum())==g["raw_outer_trial_union_area_px2"]
            rect=(int(r[0])+int(x.min()),int(r[1])+int(y.min()),
                  int(r[0])+int(x.max())+1,int(r[1])+int(y.max())+1)
        g["bbox"]=rect
        if g["display_in_MEDLARGE_main"]:
            approved_group=gid in approved
            color=(230,209,35) if approved_group else (31,165,243)
            draw=draw_box(img,rect,stride,color)
            short=gid.split("_")[-1]
            status="确认" if approved_group else "待复核RAW试验"
            annotations.append((draw,f"{short} {status} "
                f"A={g['raw_outer_trial_union_area_px2']}px² "
                f"L={g['raw_outer_trial_length_image_um']:.1f}μm(像面)","GROUP"))
    # Novel B candidates which have never received K8D RAW outer trials:
    for item in rows:
        if item["primary_visibility_layer"]!="B_NOVEL_MEDLARGE":continue
        a=[item[k] for k in ("source_bbox_x0","source_bbox_y0",
                              "source_bbox_x1_exclusive","source_bbox_y1_exclusive")]
        b=draw_box(img,a,stride,(31,165,243))
        annotations.append((b,
            f"B{item['band_id']}-C{item['source_local_id']} 待复核B源"
            f" A={item['source_area_px2']}px² "
            f"L={item['source_max_Feret_px']*PITCH:.1f}μm(像面)","B"))
    # Labels outside boxes, 1 px bbox lines; text within dark background.
    pil=Image.fromarray(cv2.cvtColor(img,cv2.COLOR_BGR2RGB))
    draw=ImageDraw.Draw(pil)
    f=ImageFont.truetype(FONT,12)
    dims=[]
    for _,name,_ in annotations:
        bb=draw.textbbox((0,0),name,font=f)
        dims.append((max(bb[2]-bb[0]+9,20),18))
    pos=arrange_labels([a[0] for a in annotations],dims,(img.shape[1],img.shape[0]))
    for (_,name,kind),p in zip(annotations,pos):
        x0,y0,x1,y1=p
        draw.rectangle((x0,y0,x1-1,y1-1),fill=(20,23,27))
        fill=(255,223,152) if kind!="J5" else (236,236,236)
        draw.text((x0+4,y0),name,font=f,fill=fill)
    return cv2.cvtColor(np.asarray(pil),cv2.COLOR_RGB2BGR),len(annotations)

def draw_band_b_pixels(imgs,band_images,scale):
    # Every K8B source pixel receives a reference-layer dot on 1:8 or 1:4
    # map. Pixel occupancy is NOT a measurement mask or grade.
    keys=sorted(imgs)
    painted=Counter()
    for band,source in sorted(band_images.items()):
        labels=source["labels"];y0=source["band_y0"]
        n=source["n"]
        lut=np.zeros(n,np.uint8)
        route_index={key:i+1 for i,key in enumerate(keys)}
        for label,rec in source["perlabel"].items():
            lut[label]=route_index.get(rec["primary_visibility_layer"],0)
        yy,xx=np.nonzero(labels)
        ids=labels[yy,xx]
        codes=lut[ids]
        Y=np.minimum(imgs["ALL_B"].shape[0]-1,(yy+y0)//scale)
        X=np.minimum(imgs["ALL_B"].shape[1]-1,xx//scale)
        imgs["ALL_B"][Y,X]=(40,195,255)
        painted["ALL_B"]+=len(yy)
        for layer in ("B_FIXED_H_REFERENCE","B_NOVEL_MICRO","B_NOVEL_SMALL"):
            if layer not in imgs:continue
            code=route_index[layer]
            take=codes==code
            if take.any():
                imgs[layer][Y[take],X[take]]=PALETTE[layer]
                painted[layer]+=int(take.sum())
    return dict(painted)

def render(frame,rows,groups,band_images,summary):
    folder=OUT/f"frame26_{frame}"
    base4=background(frame,4)
    base8=background(frame,8)
    # 1:4 full-resolution-derived; keep displays in 8-bit view only.
    main=base4.copy()
    main,annotated=draw_pending_or_new(main,4,rows,groups,frame)
    title=f"F26({frame}) K8I 整图：J5中大＋已确认＋所有K8E中大待复核＋未修复的B中大"
    mainpath=folder/MAIN
    put_title(main,title,f"细框1px，面积和Feret均取原分割源或RAW提案；橙色=待复核 | {annotated}个框",4,mainpath)
    # Render ALL pending K8E review groups separately, including SMALL.
    review=base4.copy()
    for g in groups:
        rect=g["bbox"]
        color=(80,83,241) if g["current_human_status"]=="PENDING_REVIEW" else (40,215,55)
        box=draw_box(review,rect,4,color)
        cv2.putText(review,g["group_id"].split("_")[-1],
                    (box[0],max(10,box[1]-5)),
                    cv2.FONT_HERSHEY_SIMPLEX,.36,color,1)
    put_title(review,f"F26({frame}) K8E全量{len(groups)}组RAW复核图",
              "橙红=尚未人工确认，绿色=用户已确认；不等于正式物理疵病合并",4,folder/REVIEW)
    small=base4.copy();micro=base4.copy()
    fixed=base8.copy();joutside=base8.copy();fullb=base8.copy()
    # Existing J5 source center dot for each SMALL / nonwork candidate.
    for item in rows:
        if item["stage"]!="J5":continue
        layer=item["primary_visibility_layer"]
        if layer=="J5_WORK_SMALL":canvas=small;step=4
        elif layer=="J5_OUTSIDE_WORK":canvas=joutside;step=8
        else:continue
        cx=int(round(item["source_center_x"]/step))
        cy=int(round(item["source_center_y"]/step))
        cx=max(0,min(canvas.shape[1]-1,cx))
        cy=max(0,min(canvas.shape[0]-1,cy))
        canvas[cy,cx]=PALETTE[layer]
    # K8B pixels are mapped without discarding any connected label. Convert
    # to full-RAW global 1:4 and 1:8 indices, not cropped coordinates.
    map4={"B_NOVEL_SMALL":small,"B_NOVEL_MICRO":micro,"ALL_B":base4.copy()}
    map8={"B_FIXED_H_REFERENCE":fixed,"ALL_B":fullb}
    pixel4=draw_band_b_pixels(map4,band_images,4)
    pixel8=draw_band_b_pixels(map8,band_images,8)
    put_title(small,f"F26({frame}) J5工作区小候选+K8B新增小候选",
              "所有原B源/原J5小候选位置仍在CSV；此图为可视化，不做新面积计量",4,folder/SMALL)
    put_title(micro,f"F26({frame}) K8C建议隐藏微点——全部保留，未自动删除",
              "这是人工复核图：微点并非经真值确认的噪声，也不能视为已经排除",4,folder/MICRO)
    put_title(fixed,f"F26({frame}) K8B与固定H阈值重合候选参考",
              "Fixed-H重合不代表与J5同一真实疵病，也没有自动ID归并",8,folder/FIXED)
    put_title(joutside,f"F26({frame}) 全图J5非工作区/遮光/边界候选参考",
              "全部源对象中心保持显示参考位置；未擅自删除非工作区原J5",8,folder/OUTSIDE)
    put_title(fullb,f"F26({frame}) 所有K8B分波段H候选原始源像素参考",
              "无论人工确认、暗核审核、建议隐藏或关联状态，原始B源像素一律覆盖",8,folder/ALL_B)
    return {"main_bbox_count":annotated,"source_pixel_reference_4x":pixel4,
            "source_pixel_reference_8x":pixel8,"image_files":
              [MAIN,REVIEW,SMALL,MICRO,FIXED,OUTSIDE,ALL_B]}

def execute_frame(frame):
    rows,groups,bands,summary=routes_and_sources(frame)
    renderstats=render(frame,rows,groups,bands,summary)
    layercounts=audit_layer_counts(rows)
    # All expected references exist, and the corresponding CSV layer is exact.
    folder=OUT/f"frame26_{frame}"
    missing=[name for name in renderstats["image_files"]
             if not (folder/name).is_file()]
    if missing:raise AssertionError("Render missing "+str(missing))
    nB=sum(x["n"]-1 for x in bands.values())
    assert nB==summary["B"]
    assert sum(x["source_mask_pixels"] for x in bands.values())==renderstats[
         "source_pixel_reference_8x"]["ALL_B"]
    assert nB+summary["j5"]==len(rows)
    confirmed_B=[x for x in rows if x["stage"]=="K8B" and x["is_user_confirmed"]]
    assert (set((x["band_id"],int(x["source_local_id"])) for x in confirmed_B)
          ==({(2,626),(2,658),(2,1148),(2,1161),(2,1186)} if frame==2 else set()))
    assert len(groups)==(13 if frame==1 else 18)
    assert all((x["primary_visibility_image"] in renderstats["image_files"]) for x in rows)
    report={
      "frame":frame,"source_J5_all_regions":summary["j5"],
      "source_J5_work":summary["nwork_J5"],
      "source_K8B_adaptive_full_band":summary["B"],
      "all_band_ids_detected_from_K8A":list(sorted(bands)),
      "full_source_lineage_rows":len(rows),
      "unrouted_source_ids":0,"source_modified_pixels":0,
      "K8D_processed_source_count":sum(1 for x in rows if x["K8D_outer_processed"]),
      "K8E_group_count":len(groups),
      "approved_K8E_group_count":sum(g["current_human_status"]=="USER_CONFIRMED" for g in groups),
      "K8B_confirmed_source_B_labels_mapped":len(confirmed_B),
      "layer_counts":layercounts,"render":renderstats,
      "original_source_data_files_modified":False,
      "crosschannel_J5_K8B_official_dedup_performed":False,
      "all_unconfirmed_K8B_candidate_still_visible_in_layers":True,
      "no_regulatory_defect_count_derived":True}
    (folder/"render_visibility_reconciliation.json").write_text(
         json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8I_FRAME_COMPLETE",json.dumps({
       "frame":frame,"J5_all":summary["j5"],"B_all":summary["B"],
       "groups":len(groups),"main_bbox":renderstats["main_bbox_count"],
       "unrouted":0},ensure_ascii=False),flush=True)
    return report

def main():
    if OUT.exists():raise FileExistsError("Refuse overwrite "+str(OUT))
    OUT.mkdir(parents=True)
    results=[execute_frame(f) for f in (1,2)]
    (OUT/"summary.json").write_text(json.dumps({
        "stage":"CASE03_K8I_FULL_FRAME_LINEAGE_AND_VISIBILITY",
        "results":results,"num_frames":2,
        "full_traced_sources":sum(x["full_source_lineage_rows"] for x in results),
        "all_source_files_read_only":True,
        "K8D_entire_adaptive_B_reprocessing_done":False,
        "no_new_detection_parameter_or_grade_threshold_change":True,
        "scope":"J5 all image + K8B all workband B components; K8D/K8E selected trial provenance"},
        ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8I_COMPLETE",OUT,flush=True)
if __name__=="__main__":main()
