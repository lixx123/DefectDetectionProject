"""Read-only size triage. No mask mutation and no defect rejection."""
from dataclasses import dataclass, asdict
import math

@dataclass(frozen=True)
class Settings:
    length_ratio: float = 0.10
    thickness_ratio: float = 0.80
    def validate(self):
        if not (0 < self.length_ratio <= 1 and 0 < self.thickness_ratio <= 1):
            raise ValueError('ratios must be in (0,1]')

def classify(rows, bands, settings=Settings()):
    """Returns supplemental metadata; rows and masks stay untouched.

    Project the source bounding rectangle onto the band tangent/normal.
    This is a conservative rectangle envelope, NOT an exact rotated mask box.
    Unknown geometry is REVIEW rather than silent KEEP.
    """
    settings.validate()
    result=[]
    for row in rows:
        oid=row.get('new_id',row.get('global_defect_id'))
        bid=int(row['band_id']); b=bands.get(bid)
        rec={'original_id':oid,'band_id':bid,'review_status':'NORMAL_CANDIDATE','reason':''}
        if b is None:
            rec.update(review_status='SIZE_REVIEW',reason='UNKNOWN_BAND_GEOMETRY');result.append(rec);continue
        try:
            m=(float(b['top_line_slope_y_per_x'])+float(b['bottom_line_slope_y_per_x']))/2
            norm=math.sqrt(1+m*m)
            xmin=float(b['core_x_min']);xmax=float(b['core_x_max_exclusive'])
            center=(xmin+xmax)/2
            top=float(b['top_line_y_at_x0'])+float(b['top_line_slope_y_per_x'])*center
            bottom=float(b['bottom_line_y_at_x0'])+float(b['bottom_line_slope_y_per_x'])*center
            length=(xmax-xmin)*norm;thickness=(bottom-top)/norm
            w=float(row['source_bbox_width_px']);h=float(row['source_bbox_height_px'])
            along=(w+abs(m)*h)/norm;across=(abs(m)*w+h)/norm
            if min(length,thickness,w,h)<=0 or not all(math.isfinite(v) for v in (length,thickness,along,across)):
                raise ValueError('invalid geometry')
            rw=along/length;rh=across/thickness
            reasons=[]
            if rw>=settings.length_ratio:reasons.append('LENGTH_RATIO')
            if rh>=settings.thickness_ratio:reasons.append('THICKNESS_RATIO')
            rec.update(review_status='SIZE_REVIEW' if reasons else 'NORMAL_CANDIDATE',reason='|'.join(reasons),
                       length_ratio=rw,thickness_ratio=rh,candidate_length_px=along,candidate_thickness_px=across,
                       work_length_px=length,work_thickness_px=thickness)
        except (KeyError,ValueError,TypeError,OverflowError):
            rec.update(review_status='SIZE_REVIEW',reason='INVALID_GEOMETRY')
        result.append(rec)
    return result

def attach(rows,bands,settings=Settings()):
    """Integration API: preserve all original columns and append triage metadata."""
    return [dict(row,**{'size_'+k:v for k,v in tag.items() if k!='original_id'})
            for row,tag in zip(rows,classify(rows,bands,settings))]
