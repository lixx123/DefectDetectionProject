"""Case03-K8H display-only fix: reinstate F1 Band02 K8D review channel.

Addresses K8F/K8G omission (only approved second-frame K8E entries were
carried forward). Draw TWO REVIEW ZONES, not two certified defects:
Zone A covers three elongated RAW trial envelopes (K8D 614/1273/1562)
with radius/noncompact safety flags; Zone B covers B1902 stable RAW
envelope, still unconfirmed. H pixels and J5/K8E raw outputs unchanged.
"""
from pathlib import Path
import sys,json,math,shutil
import cv2,numpy as np,pandas as pd
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k8g_display_boxes import expand_bbox_xyxy,bbox_to_display_px,overlap_area
from scripts.run_case03k8g_1p5_display_boxes import background,write_lossless

D=C.OUTPUT_ROOT/"case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3"
E=C.OUTPUT_ROOT/"case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1"
G=C.OUTPUT_ROOT/"case03k8g_display_zoom_labels/run_20261015_26_1_2_boxes_1p5x_1px_size_v2"
OUT=C.OUTPUT_ROOT/"case03k8h_f1_band02_review_overlay/run_20261015_f1_b2_K8D_unreviewed_restore_v1"
SRC=D/"frame26_1"
IMAGE=(C.RAW_WIDTH,C.RAW_HEIGHT)
FRAME=1
ZONES={"A":{"labels":[614,1273,1562],"label":"B02 复核区A：条状暗区","reason":"3条RAW外轮廓均被K8D安全门控暂缓"},
       "B":{"labels":[1902],"label":"B02 复核区B：点状暗斑","reason":"K8D RAW稳定，但未人工确认"}}
ORANGE=(26,170,240)  # BGR
FONT="C:/Windows/Fonts/msyh.ttc"

def read_mask(label):
    p=SRC/"band02"/f"F1_B2_C{label:05d}_K8D_all_masks.npz"
    with np.load(p,allow_pickle=False) as z:
        box=tuple(map(int,z["raw_global_roi_xyxy"]))
        outer=z["K8D_full_outer"].astype(bool)
        src=z["original_B_source"].astype(bool)
    assert np.all(outer[src])
    return {"label":label,"box":box,"outer":outer,"src":src}

def pixelbbox(o):
    ys,xs=np.where(o["outer"])
    a=o["box"]
    return (int(a[0]+xs.min()),int(a[1]+ys.min()),
            int(a[0]+xs.max())+1,int(a[1]+ys.max())+1)

def zones_and_audit():
    data=pd.read_csv(SRC/"all_K8D_original_vs_outer_review.csv",encoding="utf-8-sig")
    source=[]
    zone_defs=[]
    for key,spec in ZONES.items():
        members=[]
        for label in spec["labels"]:
            r=data[(data.band_id==2)&(data.candidate_label==label)]
            assert len(r)==1
            rec=r.iloc[0]
            m=read_mask(label)
            assert int(m["src"].sum())==rec.source_area_px2
            assert int(m["outer"].sum())==rec.K8D_review_outer_px2
            if key=="A":assert rec.status=="CENSORED_FULL_OUTER_REVIEW"
            else:assert rec.status=="STABLE_GROUP_OUTER_REVIEW"
            m["pixelbbox"]=pixelbbox(m)
            members.append(m)
            source.append({"review_zone":key,"band_id":2,"candidate_B_label":label,
               "K8D_status":rec.status,
               "original_B_H_pixel_area_px2":int(rec.source_area_px2),
               "K8D_trial_RAW_outer_pixel_area_px2":int(rec.K8D_review_outer_px2),
               "trial_RAW_outer_length_IMAGE_um":float(rec.K8D_length_detector_um_PROVISIONAL),
               "K8D_unresolved_safety_reasons":str(rec.rejection_reasons) if pd.notna(rec.rejection_reasons) else "",
               "original_J5_detection_membership":False,
               "user_confirmed_this_firstframe":False,
               "can_use_as_final_defect_area":False,
               "old_source_masks_modified":False,
               "raw_trial_bbox_global_xyxy":json.dumps(m["pixelbbox"])})
        x0=min(m["pixelbbox"][0] for m in members)
        y0=min(m["pixelbbox"][1] for m in members)
        x1=max(m["pixelbbox"][2] for m in members)
        y1=max(m["pixelbbox"][3] for m in members)
        original=(x0,y0,x1,y1)
        enlarged=expand_bbox_xyxy(original,IMAGE,1.5)
        zone_defs.append({"key":key,"label":spec["label"],
              "members":members,"source_mask_bbox_global_xyxy":original,
              "enlarged_1p5_review_display_bbox_xyxy":enlarged,
              "not_physical_defect_group":True,
              "manual_confirmed":False,
              "reason":spec["reason"]})
    return zone_defs,source

def arrange_review_labels(labelrects,existing,rects,display_size):
    W,H=display_size
    labels=[]
    for i,(bw,bh) in enumerate(labelrects):
        x0,y0,x1,y1=rects[i]
        trials=[]
        for delta in (4,8,20,40,75,120,170,250):
            for x,y in [
                 (x0,y0-bh-delta),(x0,y1+delta),
                 (x1+delta,y0),(x0-bw-delta,y0),
                 ((x0+x1-bw)//2,y0-bh-delta),
                 ((x0+x1-bw)//2,y1+delta),
                 (x1+delta,y1-bh),
                 (x0-bw-delta,y1-bh)]:
                xx=max(0,min(W-bw,int(x)));yy=max(0,min(H-bh,int(y)))
                rect=(xx,yy,xx+bw,yy+bh)
                coll_other=sum(overlap_area(rect,z) for z in existing)
                coll_new=sum(overlap_area(rect,z) for z in labels)
                coll_boxes=sum(overlap_area(rect,z) for z in rects)
                dist=abs(xx-x0)+abs(yy-(y0-bh-4))
                trials.append((1e7*coll_new+1e6*coll_other+1e5*coll_boxes+dist,
                               rect,coll_new,coll_other,coll_boxes))
        best=min(trials,key=lambda a:a[0])
        labels.append(best[1])
    return labels

def render_zone_overlay(zones,source,stride):
    original=G/"frame26_1"/(
       "01_MED_LARGE_boxes_1p5x_1px_with_area_length_overview_1to8.png" if stride==8
       else "02_MED_LARGE_boxes_1p5x_1px_with_area_length_detail_1to4.png")
    picture=cv2.imdecode(np.frombuffer(original.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    assert picture is not None
    H,W=picture.shape[:2]
    assert H==math.ceil(C.RAW_HEIGHT/stride)+94 and W==math.ceil(C.RAW_WIDTH/stride)
    nohdr=picture[94:].copy()
    coords=[bbox_to_display_px(z["enlarged_1p5_review_display_bbox_xyxy"],
                               IMAGE,(W,H-94),stride) for z in zones]
    for box in coords:
        cv2.rectangle(nohdr,(box[0],box[1]),(box[2],box[3]),ORANGE,1,cv2.LINE_8)
    pil=Image.fromarray(cv2.cvtColor(nohdr,cv2.COLOR_BGR2RGB))
    drawer=ImageDraw.Draw(pil)
    f1=ImageFont.truetype(FONT,15 if stride==4 else 12)
    f2=ImageFont.truetype(FONT,13 if stride==4 else 11)
    lines=[
         ("B02-A 条状暗区 | B614/1273/1562","未审批外轮廓；原B+RAW面积见审计表"),
         ("B02-B 点状暗斑 | B1902","原B=56px²，RAW提案=398px²（未审批）")
    ]
    sizes=[]
    for title,subtitle in lines:
        a=drawer.textbbox((0,0),title,font=f1)
        b=drawer.textbbox((0,0),subtitle,font=f2)
        sizes.append((max(a[2]-a[0],b[2]-b[0])+14,
                     (a[3]-a[1])+(b[3]-b[1])+13))
    mark=pd.read_csv(G/"frame26_1"/"per_object_1p5_display_geometry_and_UNCHANGED_sizes.csv",
                     encoding="utf-8-sig")
    past=mark[mark.downsample_preview_stride==stride]
    obstacles=[tuple(json.loads(s)) for s in past.label_display_xyxy_exclusive]
    box_obstacles=[tuple(json.loads(s)) for s in past.new_bbox_DISPLAY_xyxy_inclusive]
    obstacles.extend([(x0,y0,x1+1,y1+1) for x0,y0,x1,y1 in box_obstacles])
    loc=arrange_review_labels(sizes,obstacles,
        [(x0,y0,x1+1,y1+1) for x0,y0,x1,y1 in coords],(W,H-94))
    for (title,subtitle),position in zip(lines,loc):
        x0,y0,x1,y1=position
        drawer.rectangle([x0,y0,x1-1,y1-1],fill=(23,25,30))
        drawer.line([(x0+3,y0+2),(x0+3,y1-3)],fill=(245,171,34),width=2)
        a=drawer.textbbox((0,0),title,font=f1)
        b=drawer.textbbox((0,0),subtitle,font=f2)
        drawer.text((x0+9,y0+3-a[1]),title,fill=(248,248,248),font=f1)
        drawer.text((x0+9,y0+7+(a[3]-a[1])-b[1]),
                    subtitle,fill=(226,228,228),font=f2)
    backgroundhdr=Image.new("RGB",(W,94),(26,26,26))
    draw=ImageDraw.Draw(backgroundhdr)
    hfont=ImageFont.truetype(FONT,19 if stride==4 else 16)
    sfont=ImageFont.truetype(FONT,14 if stride==4 else 12)
    draw.text((9,9),"26号第一帧｜原K8G中大 + K8D Band02补充复核层",
              font=hfont,fill=(240,240,239))
    draw.text((9,43),"橙色：2处复核区域（共4个K8D外围提案，未确认为2处独立疵病）",
              font=sfont,fill=(235,218,194))
    draw.text((9,68),"原J5红/黄框与原A/L完全不变；橙色仅显示1.5倍复核框，B02-A需重新检查RAW边界。",
              font=sfont,fill=(226,225,225))
    result=np.vstack([cv2.cvtColor(np.asarray(backgroundhdr),cv2.COLOR_RGB2BGR),
                      cv2.cvtColor(np.asarray(pil),cv2.COLOR_RGB2BGR)])
    name=("01_F1_B02_review_reinstated_plus_J5_1to8.png" if stride==8
          else "02_F1_B02_review_reinstated_plus_J5_1to4.png")
    write_lossless(OUT/name,result)
    return name,coords,loc

def native_review_atlas(zones):
    from PIL import Image
    raw=np.memmap(C.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
                  shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
    cards=[]
    for zone in zones:
        box=zone["source_mask_bbox_global_xyxy"]
        x0,y0,x1,y1=box
        margin=60
        x0=max(0,x0-margin);y0=max(0,y0-margin)
        x1=min(C.RAW_WIDTH,x1+margin);y1=min(C.RAW_HEIGHT,y1+margin)
        tile=np.asarray(raw[y0:y1,x0:x1],np.float32)
        lo,hi=np.percentile(tile,[1,99.5])
        gray=np.uint8(np.clip((tile-lo)/max(hi-lo,1)*255,0,255))
        vis=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
        reviewed=vis.copy()
        for member in zone["members"]:
            mask=member["outer"]
            contours,_=cv2.findContours(np.uint8(mask),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            colors={614:(45,65,245),1273:(200,65,240),1562:(34,219,231),1902:(30,185,245)}
            for curve in contours:
                pts=curve.reshape(-1,2).astype(np.int32)
                pts[:,0]+=member["box"][0]-x0
                pts[:,1]+=member["box"][1]-y0
                cv2.polylines(reviewed,[pts.reshape(-1,1,2)],True,
                              colors[member["label"]],1,cv2.LINE_8)
        W,H=600,370
        imgs=[cv2.resize(im,(W,H),interpolation=cv2.INTER_NEAREST) for im in (vis,reviewed)]
        out=np.hstack(imgs)
        top=np.full((92,W*2,3),25,np.uint8)
        pil=Image.fromarray(cv2.cvtColor(top,cv2.COLOR_BGR2RGB))
        draw=ImageDraw.Draw(pil)
        font=ImageFont.truetype(FONT,19)
        small=ImageFont.truetype(FONT,15)
        draw.text((12,9),"第一帧Band02复核区"+zone["key"]+"：左原RAW，右K8D各源RAW外轮廓提案",
                  font=font,fill=(235,235,235))
        draw.text((12,46),zone["reason"]+"；面积/轮廓仍待人工确认",
                  font=small,fill=(231,219,202))
        cards.append(np.vstack([cv2.cvtColor(np.asarray(pil),cv2.COLOR_RGB2BGR),out]))
    write_lossless(OUT/"03_B02_two_REVIEW_ZONES_RAW_vs_trial_contours.png",
                   np.vstack(cards))

def main():
    if OUT.exists():raise FileExistsError(OUT)
    OUT.mkdir(parents=True)
    zones,rawrows=zones_and_audit()
    pd.DataFrame(rawrows).to_csv(OUT/"B02_four_original_K8D_source_candidates.csv",
                                index=False,encoding="utf-8-sig")
    imgs=[]
    display=[]
    for stride in (8,4):
        name,rects,positions=render_zone_overlay(zones,rawrows,stride)
        imgs.append(name)
        display.extend([{"review_zone":z["key"],"stride":stride,
            "enlarged_display_RAW_xyxy":json.dumps(z["enlarged_1p5_review_display_bbox_xyxy"]),
            "rendered_frame_display_rectangle_inclusive":json.dumps(rect),
            "label_position_display_xyxy_exclusive":json.dumps(pos),
            "source_K8D_candidate_labels":json.dumps(ZONES[z["key"]]["labels"]),
            "visual_only_not_J5_official_defect":True,
            "manual_confirmation_pending":True}
            for z,rect,pos in zip(zones,rects,positions)])
    pd.DataFrame(display).to_csv(OUT/"B02_two_review_zone_1p5_DISPLAY_geometry.csv",
                                  index=False,encoding="utf-8-sig")
    native_review_atlas(zones)
    for z in zones:
        for i in ZONES[z["key"]]["labels"]:
            reference=E/"frame26_1"/"group_detail"/(
                f"K8E_F1_B2_G{ {614:1,1273:2,1562:3,1902:4}[i]:03d}_RAW_sources_exact_union.png")
            if not reference.exists():raise IOError(reference)
            shutil.copyfile(reference,OUT/f"K8D_B02_C{i}_K8E_review_reference.png")
    summary={
      "stage":"CASE03_K8H_FIRSTFRAME_BAND02_REVIEW_ONLY_DISPLAY",
      "root_cause":"K8F only forwarded explicit human approved second frame G006/G009; K8G filtered only K8F register MEDIUM/LARGE",
      "does_not_change_detection_method_or_source":True,
      "K8D_raw_trial_candidates_reintroduced":4,
      "review_zones":2,
      "zones_not_certified_physical_defect_groups":True,
      "zone_A_elongeted_trials":[614,1273,1562],
      "zone_B_stable_but_not_user_approved":1902,
      "original_K8G_J5_labels_and_areas_untouched":True,
      "no_J5_K8B_K8C_K8D_K8E_K8F_K8G_original_results_modified":True,
      "sources":str(SRC),"images":imgs+["03_B02_two_REVIEW_ZONES_RAW_vs_trial_contours.png"]}
    (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),
                                    encoding="utf-8")
    print("K8H_FIRSTFRAME_B02_REVIEW_IMAGE_READY",json.dumps(summary,ensure_ascii=False),
          flush=True)

if __name__=="__main__":main()
