"""Read-only baseline audit; writes only to a fresh review directory."""
from pathlib import Path
import sys, json, hashlib, shutil
import numpy as np
import pandas as pd
import cv2
from scipy.spatial import cKDTree
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_case03_unified_final_detector_26_1_2 as old
from scripts.run_case03k8i_stage2_fullband_priority_contours import read_prior_mask
from src.detection.case03j5_seam_match import sampled_bridge_evidence

OUT = ROOT / 'outputs/UNIFIED_REVIEW_20261019_v1'

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(8*1024*1024), b''): h.update(block)
    return h.hexdigest()

def main():
    OUT.mkdir(exist_ok=False)
    files = [ROOT/'main.py', ROOT/'AGENTS.md', ROOT/'PROJECT_IMPLEMENTATION.md']
    for folder in ('config', 'src', 'scripts', 'tests'):
        files.extend((ROOT/folder).rglob('*.py'))
    manifest = []
    for p in files:
        backup = OUT/'source_backup'/p.relative_to(ROOT)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, backup)
        manifest.append({'path':str(p), 'sha256':sha(p), 'bytes':p.stat().st_size})
    for p in old.OUT.rglob('*'):
        if p.is_file(): manifest.append({'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size})
    for fr in (1,2):
        p = old.C.DATA_ROOT/f'26 ({fr}).raw'
        manifest.append({'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size})
    (OUT/'baseline_sha256.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    pairs=[]; stages=[]
    for fr in (1,2):
        rows = pd.read_csv(old.OUT/f'26_{fr}/FINAL_DEFECTS_AND_MEASUREMENTS.csv')
        raw=np.memmap(old.C.DATA_ROOT/f'26 ({fr}).raw',dtype='>u2',mode='r',shape=(9200,11276))
        objects=[]
        for row in rows.itertuples(index=False):
            m,b=old.unpack(row.raw_mask_npz,'mask','global_RAW_bbox_xyxy_exclusive')
            objects.append({'mask':m,'bbox':b,'id':row.final_ID})
            for uid in row.J5_B_or_K8E_sources.split(';'):
                if not uid.startswith('B:'): continue
                band=int(uid.split(':')[2][1:]); label=int(uid.split(':')[3][1:])
                try: prior=read_prior_mask(fr,band,label)
                except FileNotFoundError: continue
                pm,pb=old.tight(prior['mask'],prior['box'])
                stages.append({'frame':fr,'source_uid':uid,'final_ID':row.final_ID,
                    'final_area':int(m.sum()),'final_bbox':json.dumps(b),
                    'historical_area':int(pm.sum()),'historical_bbox':json.dumps(pb),
                    'intersection':old.global_intersection({'mask':m,'bbox':b},{'mask':pm,'bbox':pb}),
                    'reason':row.acceptance_reason,'historical_npz':prior['source_file']})
        for i,a in enumerate(objects):
            for b in objects[i+1:]:
                aa=a['bbox'];bb=b['bbox']
                if max(aa[0]-bb[2],bb[0]-aa[2],aa[1]-bb[3],bb[1]-aa[3])>40: continue
                ya,xa=np.where(a['mask']);yb,xb=np.where(b['mask'])
                pa=np.column_stack([xa+aa[0],ya+aa[1]]);pb=np.column_stack([xb+bb[0],yb+bb[1]])
                dist,idx=cKDTree(pa).query(pb); k=int(dist.argmin())
                p0=tuple(map(int,pa[idx[k]]));p1=tuple(map(int,pb[k]))
                med,pos,n=sampled_bridge_evidence(raw,p0,p1)
                pairs.append({'frame':fr,'a':a['id'],'b':b['id'],'intersection':old.global_intersection(a,b),
                    'gap_px':float(dist[k]),'p0':str(p0),'p1':str(p1),'dog_median':med,'positive_fraction':pos})
        if fr==1:
            box=(5190,4500,5370,4720);x0,y0,x1,y1=box
            g=np.asarray(raw[y0:y1,x0:x1],np.float32);lo,hi=np.percentile(g,[1,99])
            g=cv2.cvtColor(np.uint8(np.clip((g-lo)/(hi-lo)*255,0,255)),cv2.COLOR_GRAY2BGR)
            before=g.copy();history=g.copy()
            for ob in objects:
                a,b,c,d=ob['bbox']
                if x0<=a<c<=x1 and y0<=b<d<=y1:
                    cv2.rectangle(before,(a-x0,b-y0),(c-x0-1,d-y0-1),(0,200,255),1)
                    cv2.putText(before,ob['id'][-4:],(a-x0,b-y0-3),0,.3,(0,200,255),1)
            for label,col in [(614,(0,0,255)),(1273,(0,255,255)),(1562,(255,255,0))]:
                p=read_prior_mask(1,2,label);cs,_=cv2.findContours(np.uint8(p['mask']),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                for c in cs:
                    c=c+np.array([p['box'][0]-x0,p['box'][1]-y0],np.int32)
                    cv2.drawContours(history,[c],-1,col,1)
            canvas=cv2.resize(np.hstack([g,before,history]),None,fx=3,fy=3,interpolation=cv2.INTER_NEAREST)
            ok,buf=cv2.imencode('.png',canvas);assert ok
            (OUT/'F1_B02_RAW_current_historical_x5190_y4500.png').write_bytes(buf.tobytes())
    pd.DataFrame(stages).to_csv(OUT/'historical_vs_final.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(pairs).to_csv(OUT/'near_pair_pixel_RAW_evidence.csv',index=False,encoding='utf-8-sig')
    print(OUT)
    print(pd.DataFrame(pairs).to_string(index=False))

if __name__=='__main__': main()
