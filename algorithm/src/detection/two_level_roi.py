"""Geometry-only scheduling. Original J4 core/halo algorithms remain untouched.

The legal source ROI is the conservative original-grid envelope of the
expanded geometric ROI, not a CORE mask used to zero algorithm inputs.
Missing response pixels are UINT16_MAX (not plausible background zeros).
"""
import math
import time
import numpy as np
from config import user_config as C
from src.detection.blackhat import black_hat_uint16
from src.detection.case03k8a_band_locator import BandLocatorConfig


UNCOMPUTED_RESPONSE_U16=np.iinfo(np.uint16).max


def require_computed_response(response:np.ndarray,context:str)->None:
    """Fail closed if any consumer reaches ROI Black-Hat that was not computed.

    The configured source is effective 12-bit, so 65535 is reserved as an
    impossible response sentinel and must never enter thresholding.
    """
    if np.any(np.asarray(response)==UNCOMPUTED_RESPONSE_U16):
        raise RuntimeError(f'Uncomputed BlackHat sentinel consumed by {context}')


def halo_requirements():
    p=C.TWO_LEVEL_ROI;s=p['gaussian_support_sigmas']
    smooth=math.ceil(s*p['residual_smoothing_sigma_px'])
    return {
        'BH_close_two_operations':2*(max(C.BLACKHAT_KERNEL_SIZES_PX)//2),
        'Gaussian22_median_and_smoothing':p['median_radius_px']+math.ceil(s*p['seeded_gaussian_sigma_px'])+smooth,
        'Closing61_median_and_smoothing':p['median_radius_px']+2*(p['seeded_closing_kernel_px']//2)+smooth,
        'F_raw_ring':C.CASE03F_RING_OUTER_RADIUS_PX,
        'G_protection':C.CASE03G_PROTECT_STRUCTURE_RADIUS_PX,
        'H_DoG':math.ceil(s*C.CASE03H_DOG_LARGE_SIGMA_PX),
        'J1_J2_gap_and_DoG':math.ceil(max(C.CASE03J_MAX_LINK_GAP_PX,C.CASE03J2_CONTEXT_MAX_GAP_PX)+s*C.CASE03H_DOG_LARGE_SIGMA_PX+C.CASE03J2_BRIDGE_HALF_WIDTH_PX),
        'J4_existing_window_halo':C.CASE03J4_HALO_PX,
        'K8D_raw_context':p['K8D_raw_window_px']//2,
        'final_RAW_background_context':C.UNIFIED_FINAL['recovery_background_outer_px']+4,
        'configured_minimum':p['minimum_algorithm_halo_px'],
    }


def intersects(a,b):
    return a[0]<b[2] and b[0]<a[2] and a[1]<b[3] and b[1]<a[3]


def area(rect):
    x,y,a,b=rect;return (a-x)*(b-y)


def build_plan(shape,loc,force_full=False):
    from scripts.run_case03j4_fullscan import tiles,halo_rect
    h,w=shape;p=C.TWO_LEVEL_ROI;bc=BandLocatorConfig()
    requirements=halo_requirements();radius=math.ceil(max(requirements.values()))
    margin=radius+p['review_margin_px'];reasons=[];rects=[];outer=[]
    bands=loc.get('bands',[])
    if not p['min_band_count']<=len(bands)<=p['max_band_count']:
        reasons.append('UNTRUSTED_BAND_COUNT_OR_NO_BANDS')
    if loc.get('status')=='MANUAL_REVIEW_NO_BANDS':reasons.append('MANUAL_REVIEW_NO_BANDS')
    for b in bands:
        if b.get('validation_flags'):reasons.extend(b['validation_flags'])
        for edge in ('top','bottom'):
            q=b.get(edge+'_edge_quality',{})
            if (not q.get('linear_model_used') or q.get('edge_samples',0)<min(10,(bc.x_column_sample_count+1)//2)
                or q.get('edge_median_residual_px',float('inf')) is None
                or q.get('edge_p90_residual_px',float('inf')) is None
                or not np.isfinite([q.get('edge_median_residual_px',float('inf')),q.get('edge_p90_residual_px',float('inf'))]).all()
                or q.get('edge_median_residual_px',float('inf'))>bc.max_edge_median_residual_px
                or q.get('edge_p90_residual_px',float('inf'))>bc.max_edge_p90_residual_px):
                reasons.append('UNTRUSTED_EDGE_FIT')
        try:
            top=np.array([b['top_line_y_at_x0'],b['top_line_y_at_x0']+b['top_line_slope_y_per_x']*(w-1)])
            bottom=np.array([b['bottom_line_y_at_x0'],b['bottom_line_y_at_x0']+b['bottom_line_slope_y_per_x']*(w-1)])
            if not (np.isfinite([top,bottom]).all() and (bottom>top+2*bc.boundary_review_margin_px).all()
                    and top.min()>=0 and bottom.max()<h):
                reasons.append('UNTRUSTED_WORK_EDGE_GEOMETRY');continue
            outer.append((top,bottom))
            rects.append([0,max(0,math.floor(top.min())-margin),w,min(h,math.ceil(bottom.max())+margin+1)])
        except (KeyError,TypeError,ValueError):reasons.append('MALFORMED_GEOMETRY')
    if outer:
        fraction=sum(float(np.mean(b-a)) for a,b in outer)/h
        if not p['min_work_fraction']<=fraction<=p['max_work_fraction']:reasons.append('WORK_AREA_ABNORMAL')
        ordered=sorted(outer,key=lambda v:float(v[0].mean()))
        if any(np.any(a[1]>=b[0]) for a,b in zip(ordered,ordered[1:])):reasons.append('OVERLAPPING_BANDS')
    if not rects:reasons.append('EMPTY_ROI')
    grid=tiles(shape,C.CASE03J4_CORE_SIZE_PX)
    fallback=bool(reasons)
    if fallback or force_full:rects=[[0,0,w,h]]
    task=[t for t in grid if any(intersects(t['core_xyxy'],r) for r in rects)]
    return {'roi_mode':'FULL_FRAME_FALLBACK' if fallback else 'FULL_FRAME_BASELINE' if force_full else 'K8A_WORK_ROI',
            'fallback_reasons':sorted(set(reasons)), 'algorithm_halo_px':radius,'halo_requirements':requirements,
            'review_margin_px':p['review_margin_px'],'detection_rectangles':rects,
            'legal_source_definition':'UNION_OF_ORIGINAL_GRID_CORES_INTERSECTING_EXPANDED_GEOMETRY',
            'tiles':task,'full_tiles':len(grid),'skipped_tiles':len(grid)-len(task),
            'legal_source_pixels':sum(area(t['core_xyxy']) for t in task),
            'response_rectangles':[halo_rect(t['core_xyxy'],shape,C.CASE03J4_HALO_PX) for t in task],
            'J4_RAW_window_pixels_with_repeats':sum(area(halo_rect(t['core_xyxy'],shape,C.CASE03J4_HALO_PX)) for t in task)}


def compute_fused(raw,path,rectangles=None):
    """Same morphology as full baseline; consume full RAW halo, never ROI padding."""
    h,w=raw.shape;p=C.TWO_LEVEL_ROI;step=p['blackhat_chunk_px']
    halo=halo_requirements()['BH_close_two_operations']+p['blackhat_extra_guard_px']
    fused=np.lib.format.open_memmap(path,mode='w+',dtype=np.uint16,shape=raw.shape)
    fused[:]=UNCOMPUTED_RESPONSE_U16
    rectangles=[[0,0,w,h]] if rectangles is None else rectangles
    start=time.perf_counter();inputs=outputs=chunks=0
    for y in range(0,h,step):
        for x in range(0,w,step):
            core=[x,y,min(w,x+step),min(h,y+step)]
            if not any(intersects(core,r) for r in rectangles):continue
            a=max(0,x-halo);b=max(0,y-halo);c=min(w,core[2]+halo);d=min(h,core[3]+halo)
            tile=np.asarray(raw[b:d,a:c],np.uint16);response=np.zeros(tile.shape,np.uint16)
            for k in C.BLACKHAT_KERNEL_SIZES_PX:
                np.maximum(response,black_hat_uint16(tile,k,'ellipse'),out=response)
            fused[y:core[3],x:core[2]]=response[y-b:core[3]-b,x-a:core[2]-a]
            chunks+=1;inputs+=tile.size;outputs+=area(core)
    fused.flush()
    return fused,{'blackhat_input_pixels_with_repeats':inputs,'blackhat_kernel_pixel_evaluations':inputs*len(C.BLACKHAT_KERNEL_SIZES_PX),
                  'blackhat_output_pixels':outputs,'blackhat_chunks':chunks,'blackhat_seconds':time.perf_counter()-start,
                  'blackhat_extra_RAW_halo':halo,'uncomputed_value':int(UNCOMPUTED_RESPONSE_U16)}
