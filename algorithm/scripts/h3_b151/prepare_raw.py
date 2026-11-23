"""Reconstruct the B151 statistical and detection domains from an input RAW."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
sys.path.insert(0,str(REPO))
from src.detection.case03k8a_band_locator import BandLocatorConfig, locate_transmission_bands, rasterize_region_masks
from src.detection.two_level_roi import compute_fused

RESIDUAL_HALO_PX=96


def compute_residual_layers(raw, g22_path, c61_path, dog_path, step=2048):
    """Precompute Gaussian22/Closing61 residuals and DoG for the full frame.

    Computed in horizontal strips with a halo so core pixels equal the guarded
    per-window ``filter_context`` results (Gaussian22 support ~66px; 96px halo
    leaves margin). Layers are float32 memmaps on disk, so the per-tile hot path
    only crops instead of recomputing the large-kernel filters.
    """
    import time
    from src.detection.local_boundary_refinement import compute_local_residual
    H,W=raw.shape
    g22=np.lib.format.open_memmap(g22_path,mode='w+',dtype=np.float32,shape=(H,W))
    c61=np.lib.format.open_memmap(c61_path,mode='w+',dtype=np.float32,shape=(H,W))
    dog=np.lib.format.open_memmap(dog_path,mode='w+',dtype=np.float32,shape=(H,W))
    t0=time.perf_counter()
    for y in range(0,H,step):
        y1=min(H,y+step)
        a=max(0,y-RESIDUAL_HALO_PX);b=min(H,y1+RESIDUAL_HALO_PX)
        tile=np.asarray(raw[a:b,:],dtype=np.uint16)
        rg=compute_local_residual(tile,'gaussian22')
        rc=compute_local_residual(tile,'closing61')
        f=tile.astype(np.float32)
        d=cv2.GaussianBlur(f,(0,0),8.)-cv2.GaussianBlur(f,(0,0),2.)
        sl=slice(y-a,y1-a)
        g22[y:y1,:]=rg[sl,:];c61[y:y1,:]=rc[sl,:];dog[y:y1,:]=d[sl,:]
    g22.flush();c61.flush();dog.flush()
    return {'seconds':time.perf_counter()-t0,'halo_px':RESIDUAL_HALO_PX,
            'strip_step_px':step,'gaussian22_bytes':g22_path.stat().st_size,
            'closing61_bytes':c61_path.stat().st_size,'dog_bytes':dog_path.stat().st_size}

def prepare(path, out):
    shape=(9200,11276)
    if path.stat().st_size != 2*np.prod(shape):
        raise ValueError('Invalid RAW byte count')
    raw=np.memmap(path,mode='r',dtype='>u2',shape=shape)
    if raw.max()>4095:raise ValueError('RAW violates 12-bit input contract')
    cfg=BandLocatorConfig()
    geometry=locate_transmission_bands(raw,cfg)
    if not geometry['bands']:raise ValueError('No work bands')
    region,ids=rasterize_region_masks(shape,geometry['bands'],geometry['exterior'],cfg)
    stats=np.zeros(shape,np.uint8)
    for b in geometry['bands']:
        x=np.arange(b['core_x_min'],b['core_x_max_exclusive'])
        top=b['top_line_y_at_x0']+b['top_line_slope_y_per_x']*x
        bottom=b['bottom_line_y_at_x0']+b['bottom_line_slope_y_per_x']*x
        y0=max(0,int(np.floor(top.min())));y1=min(shape[0],int(np.ceil(bottom.max()))+1)
        y=np.arange(y0,y1)[:,None]
        sl=stats[y0:y1,x[0]:x[-1]+1]
        mask=(y>=top)&(y<=bottom)
        if (sl[mask]!=0).any():raise ValueError('Overlapping statistics bands')
        sl[mask]=b['band_id']
    detect=np.where((region==2)&(ids==stats),ids,0)
    out.mkdir(parents=True,exist_ok=False)
    bh,timing=compute_fused(raw,out/'fused.npy')
    res_timing=compute_residual_layers(raw,out/'residual_gaussian22.npy',
                                       out/'residual_closing61.npy',out/'dog.npy')
    timing={**timing,'residual_layers':res_timing}
    specs={'A1':[]};rects=[];counts=[]
    for b in geometry['bands']:
        bid=b['band_id'];q=stats==bid;d=detect==bid
        low,high=np.quantile(bh[q],[.95,.999],method='linear')
        if not 0<=low<high<65535:raise ValueError(f'Invalid H3 thresholds in band {bid}')
        specs['A1'].append(dict(band_id=bid,low_dn=float(low),high_dn=float(high)))
        y,x=np.where(d)
        if not x.size:raise ValueError(f'Empty EVAL band {bid}')
        rects.append([max(0,int(x.min())-105),max(0,int(y.min())-105),min(shape[1],int(x.max())+106),min(shape[0],int(y.max())+106)])
        counts.append(dict(band=bid,stats_pixels=int(q.sum()),detect_pixels=int(d.sum())))
    plan=[]
    for iy,y in enumerate(range(0,shape[0],256)):
        for ix,x in enumerate(range(0,shape[1],256)):
            r=min(shape[1],x+256);b=min(shape[0],y+256)
            if any(x<q[2] and q[0]<r and y<q[3] and q[1]<b for q in rects):
                plan.append(dict(tile_id=f'T{iy:03d}_{ix:03d}',ix=ix,iy=iy,core_xyxy=[x,y,r,b]))
    np.save(out/'detect.npy',detect)
    np.save(out/'stats.npy',stats)
    def sha(p):
        with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
    inp=dict(sample_id=path.stem,raw=str(path),raw_sha256=sha(path),
             response=str(out/'fused.npy'),response_sha256=sha(out/'fused.npy'),
             ids=str(out/'detect.npy'),ids_sha256=sha(out/'detect.npy'),
             residual_gaussian22=str(out/'residual_gaussian22.npy'),
             residual_gaussian22_sha256=sha(out/'residual_gaussian22.npy'),
             residual_closing61=str(out/'residual_closing61.npy'),
             residual_closing61_sha256=sha(out/'residual_closing61.npy'),
             dog=str(out/'dog.npy'),dog_sha256=sha(out/'dog.npy'),
             specs=specs,size_review_bands=geometry['bands'])
    (out/'inputs.json').write_text(json.dumps(dict(input=inp,plan=plan,counts=counts,timing=timing),ensure_ascii=False,indent=2),encoding='utf-8')
    return inp,plan

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    prepare(a.input.resolve(strict=True),a.output.resolve())
