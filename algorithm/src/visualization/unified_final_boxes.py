"""Rectangles and legible two-line labels; masks never drawn on final images."""
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from config import user_config as C
from src.detection.case03k8g_display_boxes import expand_bbox_xyxy,arrange_labels,overlap_area

def gray(raw):
    x=np.asarray(raw,np.float32);lo,hi=np.percentile(x,[1,99.5])
    return np.uint8(np.clip((x-lo)/max(hi-lo,1)*255,0,255))

def font(size):
    for path in ('C:/Windows/Fonts/arial.ttf','C:/Windows/Fonts/segoeui.ttf'):
        if Path(path).exists():return ImageFont.truetype(path,size)
    return ImageFont.load_default(size=size)

def render(raw,records,dest):
    cfg=C.UNIFIED_FINAL;stride=cfg['display_stride'];h,w=raw.shape
    # Area averaging avoids decimation phase dependence of small targets.
    small=cv2.resize(np.asarray(raw,np.float32),((w+stride-1)//stride,(h+stride-1)//stride),interpolation=cv2.INTER_AREA)
    background=gray(small);image=Image.fromarray(background).convert('RGB')
    draw=ImageDraw.Draw(image);f=font(cfg['display_font_px']);boxes=[];labels=[];sizes=[]
    for z in records:
        b=expand_bbox_xyxy(z['bbox'],(w,h),cfg['display_box_scale'])
        boxes.append(tuple(int(v//stride) for v in b))
        lines=(z['final_ID'],f"A={z['area']} px²  L={z['length']:.1f} px")
        labels.append(lines)
        sizes.append((max(int(draw.textlength(t,font=f)) for t in lines)+4,2*(cfg['display_font_px']+4)))
    placement=arrange_labels(boxes,sizes,image.size,padding=5)
    audit=[]
    for i,(z,b,lines,p) in enumerate(zip(records,boxes,labels,placement)):
        color=(70,230,100) if z['approved'] else ((245,80,60) if z['grade']=='LARGE' else (245,210,30))
        draw.rectangle(b,outline=color,width=1)
        for j,t in enumerate(lines):
            draw.text((p[0]+2,p[1]+j*(cfg['display_font_px']+4)),t,font=f,fill=color,stroke_width=1,stroke_fill=(20,20,20))
        audit.append({'final_ID':z['final_ID'],'display_box':str(b),'label_box':str(p),'label_area':z['area'],'label_length':z['length'],
                      'box_overlap_pixels':sum(overlap_area(p,q) for q in boxes),
                      'label_overlap_pixels':sum(overlap_area(p,q) for q in placement[:i]),'mask_contour_drawn':False})
    image.save(dest)
    return audit

def comparison(raw,old_objects,new_objects,box,path):
    """Same native RAW coordinates in all panels; contours only in audit output."""
    x0,y0,x1,y1=box;g=gray(raw[y0:y1,x0:x1]);panels=[]
    for title,objects in [('RAW',[]),('BEFORE',old_objects),('AFTER',new_objects)]:
        im=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
        for z in objects:
            a,b,c,d=z['bbox'];mask=np.uint8(z['mask'])
            cs,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            for contour in cs:
                cv2.drawContours(im,[contour+np.array([a-x0,b-y0],np.int32)],-1,(30,220,255),1)
        im=cv2.resize(im,None,fx=3,fy=3,interpolation=cv2.INTER_NEAREST)
        header=np.full((35,im.shape[1],3),25,np.uint8);cv2.putText(header,title,(8,25),0,.65,(240,240,240),1)
        panels.append(np.vstack([header,im]))
    ok,buf=cv2.imencode('.png',np.hstack(panels));assert ok
    path.write_bytes(buf.tobytes())
