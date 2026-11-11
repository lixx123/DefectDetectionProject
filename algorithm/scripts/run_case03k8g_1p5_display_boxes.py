"""Case03-K8G: native RAW identical-position box-only displays (1.5x, 1px).

READ-ONLY visual revision of K8F. All area/length/grades are sourced from
the saved original J5 WORK review register or K8E verified binary masks,
not estimated from expanded display rectangles.
"""
from pathlib import Path
from dataclasses import asdict
import json,shutil,sys
import cv2,numpy as np,pandas as pd
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k8g_display_boxes import (
    DisplayBoxConfig,expand_bbox_xyxy,bbox_to_display_px,arrange_labels,
    label_lines,font_sizes_for_stride,shortened_id)
from scripts.run_case03g_joint_noise_refinement import save_png

K8F=C.OUTPUT_ROOT/"case03k8f_confirmed_group_register/run_20261014_F26_2_two_user_approved_G006_G009_v2"
K8B=C.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
K8E=C.OUTPUT_ROOT/"case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1"
OUTPUT=C.OUTPUT_ROOT/"case03k8g_display_zoom_labels/run_20261015_26_1_2_boxes_1p5x_1px_size_v2"
PITCH=float(C.PIXEL_SIZE_UM)
FONT_PATH="C:/Windows/Fonts/msyh.ttc"
CFG=DisplayBoxConfig()

COLORS={"LARGE":(45,52,241),"MEDIUM":(28,219,243)}
NEW_COLOR=(230,224,30)

def write_lossless(path,arr):
    # No unicode-path issues and never modify archived output.
    path.parent.mkdir(parents=True,exist_ok=True)
    ok,enc=cv2.imencode(".png",arr)
    if not ok:raise IOError(str(path))
    path.write_bytes(enc.tobytes())
    decoded=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if decoded is None or not np.array_equal(arr,decoded):
        raise AssertionError(f"png verification failed {path}")
    return path

def background(frame,stride):
    raw=np.memmap(C.DATA_ROOT/f"26 ({frame}).raw",dtype=">u2",
                  mode="r",shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
    gray=np.asarray(raw[::stride,::stride],np.float32)
    lo,hi=np.percentile(gray,[1,99.5])
    result=np.uint8(np.clip((gray-lo)/max(1.,hi-lo)*255,0,255))
    return cv2.cvtColor(result,cv2.COLOR_GRAY2BGR)

def read_and_check_records(frame):
    data=pd.read_csv(K8F/f"frame26_{frame}"/"workband_unified_candidate_review_register.csv",
                     encoding="utf-8-sig")
    J5=pd.read_csv(K8B/f"frame26_{frame}"/"original_J5_object_center_workband_classification.csv",
                   encoding="utf-8-sig")
    J5=J5[J5.K8A_region_code_by_original_J5_center==2].copy()
    old=data[data.source=="FROZEN_J5_WORK"].copy()
    assert set(old.source_J5_global_defect_id)==set(J5.global_defect_id)
    assert len(old)==len(J5)==(683 if frame==1 else 398)
    newer=data[data.source=="K8F_USER_APPROVED_K8E_OUTER"].copy()
    assert len(newer)==(0 if frame==1 else 2)
    assert (data.source_masks_untouched==True).all()
    # Source J5 display geometry from exact same fields as previous K8F
    # red/yellow rectangles. Do NOT substitute true pixel bbox here.
    old=old.merge(J5[["global_defect_id","display_bbox_x_global",
                      "display_bbox_y_global","display_bbox_xmax_inclusive",
                      "display_bbox_ymax_inclusive","source_area_px2",
                      "source_max_feret_px","grade"]],
       left_on="source_J5_global_defect_id",right_on="global_defect_id",
       how="left",validate="one_to_one")
    assert (old.area_detector_px2==old.source_area_px2).all()
    assert (old.size_grade==old.grade).all()
    assert np.allclose(old.max_length_detector_px,old.source_max_feret_px,
                       atol=.0001)
    records=[]
    for src in (old,newer):
        for record in src.to_dict("records"):
            if record["size_grade"] not in ("MEDIUM","LARGE"):continue
            if record["source"]=="FROZEN_J5_WORK":
                x0=float(record["display_bbox_x_global"])
                y0=float(record["display_bbox_y_global"])
                x1=float(record["display_bbox_xmax_inclusive"])+1
                y1=float(record["display_bbox_ymax_inclusive"])+1
                record["is_human_confirmed"]=False
            else:
                x0=float(record["bbox_x0_global"])
                y0=float(record["bbox_y0_global"])
                x1=float(record["bbox_x1_exclusive_global"])
                y1=float(record["bbox_y1_exclusive_global"])
                record["is_human_confirmed"]=True
                gid=record["supplement_K8E_group_id"]
                with np.load(K8E/f"frame26_{frame}"/"group_detail"/(
                    gid+"_EXACT_GROUP_MASK.npz"),allow_pickle=False) as z:
                    m=z["review_outer"].astype(bool)
                    assert int(m.sum())==record["area_detector_px2"]
                assert np.isclose(record["area_detector_image_um2"],
                      int(m.sum())*PITCH**2,rtol=0,atol=.0001)
            assert 0<=x0<x1<=C.RAW_WIDTH and 0<=y0<y1<=C.RAW_HEIGHT
            record["old_display_bbox_raw_xyxy"]=(x0,y0,x1,y1)
            record["enlarged_display_bbox_raw_xyxy"]=expand_bbox_xyxy(
                (x0,y0,x1,y1),(C.RAW_WIDTH,C.RAW_HEIGHT),1.5)
            records.append(record)
    assert len(records)==(25 if frame==1 else 28)
    return data,records

def render_overlay(frame,stride,records,outdir):
    cfg=DisplayBoxConfig(display_stride_px=stride)
    cfg.validate()
    bg=background(frame,stride)
    H,W=bg.shape[:2]
    bbox_list=[bbox_to_display_px(obj["enlarged_display_bbox_raw_xyxy"],
                 (C.RAW_WIDTH,C.RAW_HEIGHT),(W,H),stride) for obj in records]
    # A single pixel rectangle only. No contour under the defect!
    for obj,box in zip(records,bbox_list):
        color=NEW_COLOR if obj["is_human_confirmed"] else COLORS[obj["size_grade"]]
        cv2.rectangle(bg,(box[0],box[1]),(box[2],box[3]),
                      color,1,cv2.LINE_8)
    fsize=font_sizes_for_stride(stride)
    f_main=ImageFont.truetype(FONT_PATH,fsize["main"])
    f_sub=ImageFont.truetype(FONT_PATH,fsize["subtitle"])
    pil=Image.fromarray(cv2.cvtColor(bg,cv2.COLOR_BGR2RGB))
    draw=ImageDraw.Draw(pil)
    textrows=[]
    dims=[]
    for obj in records:
        line1,line2=label_lines(obj)
        a=draw.textbbox((0,0),line1,font=f_main)
        b=draw.textbbox((0,0),line2,font=f_sub)
        tw=max(a[2]-a[0],b[2]-b[0])+13
        th=(a[3]-a[1])+(b[3]-b[1])+11
        textrows.append((line1,line2))
        dims.append((tw,th))
    locations=arrange_labels(bbox_list,dims,(W,H),padding=cfg.label_gap_px)
    overlays=[]
    for obj,box,label,lines in zip(records,bbox_list,locations,textrows):
        color=NEW_COLOR if obj["is_human_confirmed"] else COLORS[obj["size_grade"]]
        color_rgb=(int(color[2]),int(color[1]),int(color[0]))
        x0,y0,x1,y1=label
        draw.rectangle([x0,y0,x1-1,y1-1],fill=(18,23,27))
        draw.line([(x0+2,y0+2),(x0+2,y1-4)],fill=color_rgb,width=2)
        a=draw.textbbox((0,0),lines[0],font=f_main)
        b=draw.textbbox((0,0),lines[1],font=f_sub)
        first_top=y0+3-a[1]
        second_top=y0+7+(a[3]-a[1])-b[1]
        draw.text((x0+8,first_top),lines[0],fill=(246,246,244),font=f_main)
        draw.text((x0+8,second_top),lines[1],fill=(225,226,225),font=f_sub)
        orig=obj["old_display_bbox_raw_xyxy"]
        enlarged=obj["enlarged_display_bbox_raw_xyxy"]
        overlays.append({
          "frame":frame,
          "work_candidate_review_ID":obj["work_candidate_review_ID"],
          "existing_J5_source_ID":str(obj["source_J5_global_defect_id"]) if
              obj["source"]=="FROZEN_J5_WORK" else "",
          "new_confirmed_K8E_group_ID":str(obj["supplement_K8E_group_id"]) if
              obj["is_human_confirmed"] else "",
          "size_grade_original":obj["size_grade"],
          "area_detector_px2_SOURCE_UNCHANGED":int(obj["area_detector_px2"]),
          "max_feret_detector_px_SOURCE_UNCHANGED":float(obj["max_length_detector_px"]),
          "area_image_plane_um2_SOURCE_UNCHANGED":float(obj["area_detector_image_um2"]),
          "max_length_image_plane_um_SOURCE_UNCHANGED":float(obj["max_length_detector_image_um"]),
          "human_confirmed_darkspot":obj["is_human_confirmed"],
          "old_display_bbox_RAW_xyxy_exclusive":json.dumps(orig),
          "new_1p5_DISPLAY_bbox_RAW_xyxy_exclusive":json.dumps(enlarged),
          "old_bbox_width_px":round(orig[2]-orig[0],4),
          "new_bbox_width_px":round(enlarged[2]-enlarged[0],4),
          "old_bbox_height_px":round(orig[3]-orig[1],4),
          "new_bbox_height_px":round(enlarged[3]-enlarged[1],4),
          "old_bbox_center_RAW":[(orig[0]+orig[2])/2,(orig[1]+orig[3])/2],
          "new_bbox_center_RAW":[(enlarged[0]+enlarged[2])/2,(enlarged[1]+enlarged[3])/2],
          "outline_width_DISPLAY_px":1,
          "downsample_preview_stride":stride,
          "new_bbox_DISPLAY_xyxy_inclusive":json.dumps(box),
          "measurement_uses_enlarged_bbox":False,
          "label_display_xyxy_exclusive":json.dumps(label),
          "label_text":" | ".join(lines)
        })
    vis=cv2.cvtColor(np.asarray(pil),cv2.COLOR_RGB2BGR)
    name="02_MED_LARGE_boxes_1p5x_1px_with_area_length_detail_1to4.png" if stride==4 else (
         "01_MED_LARGE_boxes_1p5x_1px_with_area_length_overview_1to8.png")
    banner=np.full((94,W,3),26,np.uint8)
    pilbanner=Image.fromarray(cv2.cvtColor(banner,cv2.COLOR_BGR2RGB))
    head=ImageDraw.Draw(pilbanner)
    titlefont=ImageFont.truetype(FONT_PATH,19 if stride==4 else 16)
    subfont=ImageFont.truetype(FONT_PATH,15 if stride==4 else 12)
    head.text((12,8),f"26号第{frame}帧｜工作区中、大疵病｜显示框扩大1.5倍，线宽1像素",
              fill=(236,237,237),font=titlefont)
    head.text((12,43),f"红：原J5大 | 黄：原J5中 | 青：人工确认新增暗斑 | {len(records)}处中大显示框",
              fill=(213,222,226),font=subfont)
    head.text((12,69),"A=原候选轮廓面积(px²)；L=最大Feret长度(μm，探测器像面当量)。框只供显示，不参与测量。",
              fill=(212,212,212),font=subfont)
    final=np.vstack([cv2.cvtColor(np.asarray(pilbanner),cv2.COLOR_RGB2BGR),vis])
    write_lossless(outdir/name,final)
    return overlays,name

def create_two_target_sheet(frame,records,outdir):
    if frame!=2:return None
    targets=[x for x in records if x["is_human_confirmed"]]
    assert len(targets)==2
    raw=np.memmap(C.DATA_ROOT/f"26 ({frame}).raw",mode="r",
                  dtype=">u2",shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
    fontsize=16
    font=ImageFont.truetype(FONT_PATH,fontsize)
    cells=[]
    for obj in sorted(targets,key=lambda t:t["supplement_K8E_group_id"]):
        gid=obj["supplement_K8E_group_id"]
        with np.load(K8E/"frame26_2"/"group_detail"/(
            gid+"_EXACT_GROUP_MASK.npz"),allow_pickle=False) as z:
            native=z["review_outer"].astype(bool)
            bounds=tuple(map(int,z["roi_xyxy"]))
        patch=np.asarray(raw[bounds[1]:bounds[3],bounds[0]:bounds[2]],np.float32)
        lo,hi=np.percentile(patch,[1,99.5])
        u8=np.uint8(np.clip((patch-lo)/max(1.,hi-lo)*255,0,255))
        base=cv2.cvtColor(u8,cv2.COLOR_GRAY2BGR)
        # Native contour, only in its dedicated reference panel, not main
        cnt,_=cv2.findContours(np.uint8(native),cv2.RETR_EXTERNAL,
                                cv2.CHAIN_APPROX_SIMPLE)
        contour=base.copy()
        cv2.drawContours(contour,cnt,-1,(0,225,248),1,cv2.LINE_8)
        boxview=base.copy()
        new=obj["enlarged_display_bbox_raw_xyxy"]
        pt0=(round(new[0]-bounds[0]),round(new[1]-bounds[1]))
        pt1=(round(new[2]-bounds[0]-1),round(new[3]-bounds[1]-1))
        cv2.rectangle(boxview,pt0,pt1,NEW_COLOR,1,cv2.LINE_8)
        row=[]
        for title,im in [("原RAW（无标注）",base),("1.5倍细框（显示）",boxview),
                          ("真实轮廓（测量）",contour)]:
            pic=cv2.resize(im,(384,384),interpolation=cv2.INTER_NEAREST)
            pil=Image.fromarray(cv2.cvtColor(pic,cv2.COLOR_BGR2RGB))
            # title only above, not within actual RAW patch
            strip=Image.new("RGB",(384,90),(24,25,27))
            draw=ImageDraw.Draw(strip)
            draw.text((12,7),title,fill=(238,238,238),font=font)
            draw.text((12,35),
                f"{gid.split('_')[-1]} | A={int(obj['area_detector_px2'])} px²",
                fill=(220,220,220),font=font)
            draw.text((12,60),
                f"L={float(obj['max_length_detector_image_um']):.1f} μm(像面)",
                fill=(220,220,220),font=font)
            assembled=Image.new("RGB",(384,474))
            assembled.paste(strip,(0,0));assembled.paste(pil,(0,90))
            row.append(cv2.cvtColor(np.asarray(assembled),cv2.COLOR_RGB2BGR))
        cells.append(np.hstack(row))
    total=np.vstack(cells)
    filename="03_G006_G009_1p5box_vs_exact_mask_three_panel.png"
    write_lossless(outdir/filename,total)
    return filename

def main():
    if OUTPUT.exists():raise FileExistsError("Refusing overwrite "+str(OUTPUT))
    OUTPUT.mkdir(parents=True)
    frames=[]
    for frame in (1,2):
        output=OUTPUT/f"frame26_{frame}"
        output.mkdir()
        register,records=read_and_check_records(frame)
        displays=[]
        images=[]
        for stride in (8,4):
            entries,filename=render_overlay(frame,stride,records,output)
            displays.extend(entries);images.append(filename)
            print("K8G_RENDER_COMPLETE",frame,stride,filename,len(entries),flush=True)
        detail=create_two_target_sheet(frame,records,output)
        if detail:images.append(detail)
        src=K8F/f"frame26_{frame}"/"04_SMALL_existing_and_K8C_reference.png"
        if src.exists():
            file="04_SMALL_unchanged_reference.png"
            shutil.copyfile(src,output/file)
            assert cv2.imdecode(np.frombuffer((output/file).read_bytes(),np.uint8),1) is not None
            images.append(file)
        df=pd.DataFrame(displays)
        df.to_csv(output/"per_object_1p5_display_geometry_and_UNCHANGED_sizes.csv",
                  encoding="utf-8-sig",index=False)
        # The exact K8F 400/683 source review register is retained unchanged.
        source=K8F/f"frame26_{frame}"/"workband_unified_candidate_review_register.csv"
        shutil.copyfile(source,output/"frozen_K8F_work_review_register_UNCHANGED.csv")
        summ={
          "frame":frame,"display_medium_large_count":len(records),
          "source_K8F_unified_review_count":len(register),
          "source_J5_unverified_count":int((register.source=="FROZEN_J5_WORK").sum()),
          "source_human_approved_new_count":int(
              (register.source=="K8F_USER_APPROVED_K8E_OUTER").sum()),
          "original_source_detection_IDs_areas_feret_grades_modified":False,
          "display_box_scale_factor":1.5,"display_box_line_width_px":1,
          "label_measurement_basis":"ORIGINAL_J5_SOURCE_OR_CONFIRMED_K8E_EXACT_MASK_NOT_DRAWN_BBOX",
          "unit":"detector IMAGE PLANE um/um2 using 3.2um per px; object plane NOT calibrated",
          "all_small_candidates_in_separate_reference_only":True,
          "source_REGISTER_not_overwritten":True,
          "images":images
        }
        (output/"summary.json").write_text(json.dumps(summ,ensure_ascii=False,indent=2),
                                          encoding="utf-8")
        frames.append(summ)
    (OUTPUT/"summary.json").write_text(json.dumps({
        "stage":"CASE03_K8G_DISPLAY_ONLY","frames":frames,
        "parameters":asdict(CFG),"unchanged_source_K8F":str(K8F),
        "original_object_sizes_and_J5_source_untouched":True
        },ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8G_FINAL_DISPLAY_DONE",json.dumps(
        [{"frame":v["frame"],"boxes":v["display_medium_large_count"]} for v in frames],
         ensure_ascii=False),flush=True)

if __name__=="__main__":main()
