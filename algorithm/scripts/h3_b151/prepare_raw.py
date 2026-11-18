"""Reconstruct the B151 statistical and detection domains from an input RAW."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
sys.path.insert(0,str(REPO))
from src.detection.case03k8a_band_locator import BandLocatorConfig, locate_transmission_bands, rasterize_region_masks
from src.detection.two_level_roi import compute_fused

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
    specs={'A0':[],'A1':[]};rects=[];counts=[]
    for b in geometry['bands']:
        bid=b['band_id'];q=stats==bid;d=detect==bid
        low,high=np.quantile(bh[q],[.95,.999],method='linear')
        if not 0<=low<high<65535:raise ValueError(f'Invalid H3 thresholds in band {bid}')
        specs['A0'].append(dict(band_id=bid,low_dn=170.,high_dn=230.))
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
    inp=dict(sample_id=path.stem,raw=str(path),raw_sha256=sha(path),response=str(out/'fused.npy'),response_sha256=sha(out/'fused.npy'),ids=str(out/'detect.npy'),ids_sha256=sha(out/'detect.npy'),specs=specs)
    (out/'inputs.json').write_text(json.dumps(dict(input=inp,plan=plan,counts=counts,timing=timing),ensure_ascii=False,indent=2),encoding='utf-8')
    return inp,plan

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    prepare(a.input.resolve(strict=True),a.output.resolve())
