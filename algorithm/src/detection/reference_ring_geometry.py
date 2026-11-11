"""Case03-C rectangular RAW background reference: one source of truth.

The eligible region is the clipped rectangular annulus around the *exact H*
candidate bounding box, excluding the bounding box and every H candidate
pixel. The sampled pixels reproduce the original deterministic linspace cap.
No pixels are considered *used for statistics* when reference_valid=False.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class ReferenceSelection:
    x0: int
    y0: int
    x1: int
    y1: int
    eligible_mask: np.ndarray
    sample_x: np.ndarray
    sample_y: np.ndarray
    eligible_count: int
    sampled_count: int

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        return self.x0, self.y0, self.x1, self.y1


def select_reference_pixels(component, h_mask: np.ndarray, *, radius_px: int,
                            max_reference_pixels: int) -> ReferenceSelection:
    """Return exactly the pixels used by the original RAW ring statistics.

    Coordinates are global full-image (x=column,y=row). Sampling is based on
    the row-major order of the eligible cropped annulus; deterministic linspace
    is used when there are more than max_reference_pixels eligible pixels.
    """
    if h_mask.ndim != 2 or h_mask.dtype != np.bool_:
        raise TypeError("h_mask must be 2D bool")
    if int(radius_px) < 0 or int(max_reference_pixels) < 1:
        raise ValueError("invalid reference radius or sampling cap")
    height, width = h_mask.shape
    bx, by = int(component.bbox_x), int(component.bbox_y)
    bw, bh = int(component.bbox_w), int(component.bbox_h)
    if bw <= 0 or bh <= 0 or bx < 0 or by < 0 or bx+bw > width or by+bh > height:
        raise ValueError("candidate bounding box is outside image")
    x0 = max(0, bx-int(radius_px))
    y0 = max(0, by-int(radius_px))
    x1 = min(width, bx+bw+int(radius_px))
    y1 = min(height, by+bh+int(radius_px))
    eligible = np.ones((y1-y0,x1-x0), dtype=bool)
    eligible[by-y0:by-y0+bh, bx-x0:bx-x0+bw] = False
    eligible &= ~h_mask[y0:y1,x0:x1]
    indexes=np.flatnonzero(eligible)
    n=int(indexes.size)
    if n > max_reference_pixels:
        indexes=indexes[np.linspace(0,n-1,max_reference_pixels,dtype=np.int64)]
    sample_y=indexes//eligible.shape[1]+y0
    sample_x=indexes%eligible.shape[1]+x0
    return ReferenceSelection(
        x0,y0,x1,y1,eligible,
        sample_x.astype(np.int64,copy=False),
        sample_y.astype(np.int64,copy=False),
        n,int(indexes.size),
    )


def project_reference_masks(selection: ReferenceSelection, *, image_bounds: tuple[int,int,int,int],
                            valid_reference: bool) -> tuple[np.ndarray,np.ndarray]:
    """ROI-cropped (eligible, *actually used* sample) booleans.

    Invalid references still have an eligible geometric annulus, but no
    statistical sample was used. These must never be shown as valid samples.
    """
    x0,y0,x1,y1=(int(z) for z in image_bounds)
    if not (0 <= x0 < x1 and 0 <= y0 < y1):
        raise ValueError("invalid ROI bounds")
    elig=np.zeros((y1-y0,x1-x0),dtype=bool)
    used=np.zeros_like(elig)
    ox0,oy0=max(x0,selection.x0),max(y0,selection.y0)
    ox1,oy1=min(x1,selection.x1),min(y1,selection.y1)
    if ox1>ox0 and oy1>oy0:
        elig[oy0-y0:oy1-y0,ox0-x0:ox1-x0]=selection.eligible_mask[
            oy0-selection.y0:oy1-selection.y0,ox0-selection.x0:ox1-selection.x0
        ]
    if valid_reference:
        x,y=selection.sample_x,selection.sample_y
        within=(x>=x0)&(x<x1)&(y>=y0)&(y<y1)
        used[y[within]-y0,x[within]-x0]=True
    return elig,used
