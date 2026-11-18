"""纯阈值图装配：不读取/使用真值、对象ID或历史保留规则。"""
import numpy as np
CACHE={}
def render(spec,l,t,r,b):
 p=spec['pixel_band_ids']
 if p not in CACHE:CACHE[p]=np.load(p,mmap_mode='r')
 ids=CACHE[p][t:b,l:r]
 lo=np.full(ids.shape,float(spec['fallback'][0]),np.float64);hi=np.full(ids.shape,float(spec['fallback'][1]),np.float64)
 for z in spec['bands']:
  m=ids==int(z['band_id']);lo[m]=z['low_dn'];hi[m]=z['high_dn']
 if np.any(lo>hi):raise ValueError('TL>TH')
 return lo,hi
