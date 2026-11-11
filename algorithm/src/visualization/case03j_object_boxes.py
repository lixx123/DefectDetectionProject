"""Case03-J3 grouped-object outer contour + ONE bounding box per object.

The box spans the full associated *display* geometry (source segmentation
PLUS separately audited inferred bridge pixels); no per-fragment boxes.
Numerical measured area/length remain on original detected pixels only.
An edge-touching box is explicitly marked ROI_CLIPPED, never presented as
the entire physical defect or a certified size.
"""
from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np
from src.detection.case03i_size_grade import GRADE_COLORS_BGR
from scripts.run_case03g_joint_noise_refinement import gray


@dataclass(frozen=True)
class BoxStyle:
    draw_small_boxes:bool=False
    draw_small_contours:bool=True
    draw_all_object_boxes:bool=False
    frame_thickness:int=2
    contour_thickness:int=1
    zoom:int=3


def measure_visual_bbox(combined_ids:np.ndarray,original_ids:np.ndarray,
                        objects:list[dict],roi_xyxy:tuple[int,int,int,int],
                        )->list[dict]:
    if combined_ids.shape!=original_ids.shape or combined_ids.ndim!=2:
        raise ValueError("object rasters must have matching 2D shapes")
    x0,y0,x1,y1=(int(v) for v in roi_xyxy)
    if combined_ids.shape!=(y1-y0,x1-x0):
        raise ValueError("ROI geometry mismatch")
    H,W=combined_ids.shape
    boxes=[]
    for n,o in enumerate(objects,1):
        yy,xx=np.where(combined_ids==n)
        if yy.size==0:raise AssertionError("missing grouped object raster")
        oy,ox=np.where(original_ids==n)
        if oy.size==0:raise AssertionError("missing source detected geometry")
        bx,by,ex,ey=(int(xx.min()),int(yy.min()),
                     int(xx.max()),int(yy.max()))
        sx,sy,tx,ty=(int(ox.min()),int(oy.min()),
                     int(ox.max()),int(oy.max()))
        # The union bbox must cover all original source pixels; never shrink
        # because inferred geometry was used.
        if not (bx<=sx<=tx<=ex and by<=sy<=ty<=ey):
            raise AssertionError("group bbox did not cover original mask")
        touches=bx==0 or by==0 or ex==W-1 or ey==H-1
        boxes.append({
            "object_id":str(o["object_id"]),
            "window_id":str(o["window_id"]),
            "local_object_index":n,
            "size_grade":str(o["size_grade"]),
            "member_count":int(o["member_count"]),
            "roi_x0":x0,"roi_y0":y0,"roi_x1":x1,"roi_y1":y1,
            "display_bbox_x_global":x0+bx,
            "display_bbox_y_global":y0+by,
            "display_bbox_width_px":ex-bx+1,
            "display_bbox_height_px":ey-by+1,
            "display_bbox_xmax_inclusive":x0+ex,
            "display_bbox_ymax_inclusive":y0+ey,
            "source_bbox_x_global":x0+sx,
            "source_bbox_y_global":y0+sy,
            "source_bbox_width_px":tx-sx+1,
            "source_bbox_height_px":ty-sy+1,
            "touches_roi_boundary":bool(touches),
            "bbox_may_be_truncated":bool(touches),
            "bbox_includes_inferred_bridge_geometry":True,
            "area_px2_original":int(o["original_area_px2"]),
            "feret_px_original":float(o["original_max_feret_px"]),
            "inferred_bridge_pixels_excluded_from_measurement":int(
                o["inferred_bridge_pixels"]),
            "provisional_size_not_quality_grade":True,
            "frame_global_scan_complete":False,
        })
    return boxes


def _draw_labels_and_contours(img:np.ndarray,combined:np.ndarray,
                              boxes:list[dict],style:BoxStyle,
                              x0:int,y0:int)->np.ndarray:
    H,W=combined.shape
    out=img.copy()
    # Fit inside ROI. When a box touches ROI edge it MUST remain at the
    # edge, not be padded or suggest an outside measurement.
    for record in boxes:
        idx=int(record["local_object_index"])
        level=record["size_grade"]
        is_small=level=="SMALL"
        color=GRADE_COLORS_BGR[level]
        bmask=np.uint8(combined==idx)
        show_contour=not is_small or style.draw_small_contours
        show_box=(not is_small or style.draw_all_object_boxes or
                  style.draw_small_boxes)
        if show_contour:
            contours,_=cv2.findContours(
                bmask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(out,contours,-1,color,
                             style.contour_thickness,cv2.LINE_8)
        if not show_box:continue
        x=int(record["display_bbox_x_global"]-x0)
        y=int(record["display_bbox_y_global"]-y0)
        xmax=int(record["display_bbox_xmax_inclusive"]-x0)
        ymax=int(record["display_bbox_ymax_inclusive"]-y0)
        cv2.rectangle(out,(x,y),(xmax,ymax),color,style.frame_thickness,
                      lineType=cv2.LINE_8)
        # Labels share object ID, never former local-region ID.
        oid=str(record["object_id"]).rsplit("C",1)[-1]
        text=f"D{oid} {level[0]}"
        if record["bbox_may_be_truncated"]:
            text+="*"
        # Place label near top border, but inside canvas even when y=0.
        text_x=max(1,min(W-80,x))
        text_y=max(13,min(H-2,y-4 if y>=16 else ymax+14))
        cv2.putText(out,text,(text_x,text_y),
                    cv2.FONT_HERSHEY_SIMPLEX,.35,
                    (15,15,15),2,cv2.LINE_AA)
        cv2.putText(out,text,(text_x,text_y),
                    cv2.FONT_HERSHEY_SIMPLEX,.35,
                    color,1,cv2.LINE_AA)
    return out


def render_grouped_box_comparison(raw:np.ndarray,original_ids:np.ndarray,
                                  combined_ids:np.ndarray,
                                  bridge_ids:np.ndarray,
                                  boxes:list[dict],rect:tuple[int,int,int,int],
                                  title:str,
                                  style:BoxStyle=BoxStyle())->np.ndarray:
    if (raw.shape!=original_ids.shape or
        raw.shape!=combined_ids.shape or raw.shape!=bridge_ids.shape or
        raw.dtype!=np.uint16):
        raise ValueError("RAW or object mask mismatch")
    x0,y0,x1,y1=rect
    source=gray(raw)
    contour=_draw_labels_and_contours(source,combined_ids,boxes,
                       BoxStyle(draw_small_boxes=False,
                                draw_small_contours=True,
                                frame_thickness=style.frame_thickness,
                                contour_thickness=style.contour_thickness),
                       x0,y0)
    marked=_draw_labels_and_contours(source,combined_ids,boxes,style,x0,y0)
    provenance=marked.copy()
    provenance[(bridge_ids>0)]=(235,220,75)
    # Edge-truncated object still gets its single enclosing rectangle, but
    # user must see that box reaches the ROI boundary.
    images=[
        ("Original RAW",source),
        ("Complete associated contour",contour),
        ("One box per object",marked),
        ("CYAN inferred bridges",provenance)
    ]
    result=[]
    for label,im in images:
        img=cv2.resize(im,None,fx=style.zoom,fy=style.zoom,
                       interpolation=cv2.INTER_NEAREST)
        img=cv2.copyMakeBorder(img,82,0,0,0,cv2.BORDER_CONSTANT,
                              value=(26,26,26))
        cv2.putText(img,f"{title} / {label}",(11,26),
                    cv2.FONT_HERSHEY_SIMPLEX,.60,
                    (242,242,242),1,cv2.LINE_AA)
        cv2.putText(img,"Single bbox / linked object; *=ROI CLIPPED",
                    (11,47),cv2.FONT_HERSHEY_SIMPLEX,.42,
                    (217,217,217),1,cv2.LINE_AA)
        cv2.putText(img,"Detector pixels used for area; inferred bridges not measured",
                    (11,70),cv2.FONT_HERSHEY_SIMPLEX,.35,
                    (207,207,207),1,cv2.LINE_AA)
        result.append(img)
    return np.hstack(result)
