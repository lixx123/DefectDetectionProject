"""Split compact RAW-supported lobes from size-review parents, without deletion.

Only original source pixels are assigned to children. Parent minus children is
an explicit review remainder; the original parent is an immutable audit record.
No coordinates, frame names or object IDs enter the decision rule.
"""
from dataclasses import dataclass, asdict
import time
import cv2
import numpy as np
from src.detection.case03i_size_grade import SizeGradeConfig, grade_size, max_feret_centers_px


@dataclass(frozen=True)
class EdgeSpotSettings:
    inside_px: int = 192
    outside_px: int = 16
    background_block_px: int = 512
    high_sigma: float = 5.0
    low_sigma: float = 2.5
    noise_floor_dn: float = 5.0
    min_seed_source_px: int = 4
    max_width_fraction: float = 0.25
    min_child_area_px: int = 40
    min_source_fill: float = 0.45
    max_child_aspect: float = 2.0

    def validate(self):
        if not (self.inside_px > 0 and self.outside_px >= 0 and self.background_block_px >= 64
                and self.high_sigma > self.low_sigma > 0 and self.noise_floor_dn > 0
                and self.min_seed_source_px > 0 and 0 < self.max_width_fraction < .5
                and self.min_child_area_px > 0 and 0 < self.min_source_fill <= 1
                and self.max_child_aspect >= 1):
            raise ValueError('invalid edge spot settings')


def _background(strip, block):
    # Robust per-distance profiles, interpolated along the band. Dark compact
    # defects cannot define the profile unless they occupy half a sample block.
    width = strip.shape[1]
    centers = np.unique(np.r_[np.arange(0, width, block // 2), width-1])
    profiles = []
    for c in centers:
        profiles.append(np.median(strip[:, max(0,c-block//2):min(width,c+block//2)], axis=1))
    profiles = np.stack(profiles, axis=1)
    x = np.arange(width)
    bg = np.stack([np.interp(x, centers, row) for row in profiles]).astype(np.float32)
    residual = bg - strip
    bias = np.median(residual, axis=1, keepdims=True)
    sigma = 1.4826 * np.median(np.abs(residual-bias), axis=1, keepdims=True)
    return residual-bias, sigma


def split_parent(raw, source, bbox, band, settings=EdgeSpotSettings(), grade=SizeGradeConfig()):
    settings.validate()
    start = time.perf_counter()
    x0,y0,x1,y1 = map(int,bbox)
    source = np.asarray(source, dtype=bool)
    if source.shape != (y1-y0,x1-x0):
        raise ValueError('source/bbox mismatch')
    claimed = np.zeros_like(source)
    children, audit = [], []
    if band is None:
        return children, source.copy(), dict(reason='UNKNOWN_GEOMETRY',seconds=time.perf_counter()-start)
    left = max(0, int(band['core_x_min']), x0)
    right = min(raw.shape[1],int(band['core_x_max_exclusive']),x1)
    if right-left < settings.background_block_px:
        return children, source.copy(), dict(reason='INSUFFICIENT_BACKGROUND_SPAN',seconds=time.perf_counter()-start)
    for edge,sign in [('top',1),('bottom',-1)]:
        slope=float(band[edge+'_line_slope_y_per_x']);intercept=float(band[edge+'_line_y_at_x0'])
        xs=np.arange(left,right,dtype=np.float32)
        mid=(left+right)/2
        thickness=(float(band['bottom_line_y_at_x0'])+float(band['bottom_line_slope_y_per_x'])*mid
                   -float(band['top_line_y_at_x0'])-float(band['top_line_slope_y_per_x'])*mid)
        depth=min(settings.inside_px,max(1,int(thickness/2)))
        offsets=np.arange(-settings.outside_px,depth+1,dtype=np.float32)
        mx=np.broadcast_to(xs,(len(offsets),len(xs))).copy()
        my=intercept+slope*mx+sign*offsets[:,None]
        # Read only a narrow bounding strip, not a converted full RAW frame.
        ya=max(0,int(np.floor(my.min()))-1);yb=min(raw.shape[0],int(np.ceil(my.max()))+2)
        if yb<=y0 or ya>=y1:
            continue
        patch=np.asarray(raw[ya:yb,left:right],dtype=np.float32)
        strip=cv2.remap(patch,mx-left,my-ya,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
        residual,sigma=_background(strip,settings.background_block_px)
        sigma=np.maximum(sigma,settings.noise_floor_dn)
        # Half-up nearest sampling preserves a one-to-one row translation.
        # Banker's rounding at n+.5 duplicates alternate rows and loses others.
        yi=np.floor(my+0.5).astype(np.int32);xi=mx.astype(np.int32)
        valid=(yi>=y0)&(yi<y1)&(yi>=0)&(yi<raw.shape[0])
        src=np.zeros(valid.shape,bool);src[valid]=source[yi[valid]-y0,xi[valid]-x0]
        support=(residual>=settings.low_sigma*sigma)&valid
        seeds=(residual>=settings.high_sigma*sigma)&src
        n,labels,stats,_=cv2.connectedComponentsWithStats(support.astype(np.uint8),8)
        active=np.unique(labels[seeds]);active=active[active>0]
        for label in active:
            xx,yy,w,h,area=map(int,stats[label]);q=labels[yy:yy+h,xx:xx+w]==label
            entry=dict(edge=edge,label=int(label),raw_support_area=area,span_px=w)
            qx=xi[yy:yy+h,xx:xx+w][q];qy=yi[yy:yy+h,xx:xx+w][q]
            entry['proposal_bbox']=[int(qx.min()),int(qy.min()),int(qx.max())+1,int(qy.max())+1]
            seed_count=int((q&seeds[yy:yy+h,xx:xx+w]).sum())
            entry['seed_source_pixels']=seed_count
            if seed_count<settings.min_seed_source_px:
                entry['reason']='WEAK_SOURCE_ANCHOR';audit.append(entry);continue
            if xx==0 or xx+w==len(xs) or yy==0 or yy+h==len(offsets):
                entry['reason']='OPEN_AT_STRIP_BOUNDARY';audit.append(entry);continue
            if w>=settings.background_block_px*settings.max_width_fraction:
                entry['reason']='NONLOCAL_OR_BACKGROUND_CONTAMINATION';audit.append(entry);continue
            selected=q&src[yy:yy+h,xx:xx+w]
            gx=xi[yy:yy+h,xx:xx+w][selected];gy=yi[yy:yy+h,xx:xx+w][selected]
            fresh=~claimed[gy-y0,gx-x0];gx=gx[fresh];gy=gy[fresh]
            if not len(gx):continue
            ax,ay,bx,by=int(gx.min()),int(gy.min()),int(gx.max())+1,int(gy.max())+1
            mask=np.zeros((by-ay,bx-ax),bool);mask[gy-ay,gx-ax]=True
            # This route claims compact spots only. Thin scratches/fragments
            # remain visible in the review remainder, never deleted as noise.
            if (mask.sum()<settings.min_child_area_px or mask.mean()<settings.min_source_fill
                    or max(mask.shape)/min(mask.shape)>settings.max_child_aspect):
                entry['reason']='NONCOMPACT_RETAINED_IN_PARENT';audit.append(entry);continue
            py,px=np.nonzero(mask);feret=max_feret_centers_px(np.c_[px,py]);size,trigger=grade_size(int(mask.sum()),feret,grade)
            if size=='SMALL':
                entry['reason']='SMALL_RETAINED_IN_PARENT';audit.append(entry);continue
            claimed[gy-y0,gx-x0]=True
            children.append(dict(bbox=[ax,ay,bx,by],mask=mask,area_px=int(mask.sum()),feret_px=feret,
                                 grade=size,grade_trigger=trigger,edge=edge,seed_source_px=seed_count,
                                 status='AUTO_CANDIDATE',measurement_scope='ORIGINAL_SOURCE_SUBSET'))
            entry['reason']='SPLIT_CHILD';entry['child_index']=len(children);audit.append(entry)
    remainder=source&~claimed
    assert np.array_equal(claimed|remainder,source) and not np.any(claimed&remainder)
    return children,remainder,dict(settings=asdict(settings),seconds=time.perf_counter()-start,
                                  children=len(children),remaining_pixels=int(remainder.sum()),proposals=audit)
