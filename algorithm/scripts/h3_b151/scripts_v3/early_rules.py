"""从冻结几何支持界推导保守早退；不接受基线对象或人工信息。"""
import math,cv2,numpy as np
from fast_state import STATE
def _classify(labels,stats,valid,margin,minarea,minlength,maxarea,support_minarea=0):
 n=len(stats);safe=set();reasons={'POTENTIAL_MEDIUM_LARGE':0,'ASSOCIATION_SUPPORT':0,'UNCERTAIN':0,'SAFE_SMALL_TO_SKIP':0}
 if n<=1:return safe,reasons
 st=stats[1:];x=st[:,0];y=st[:,1];right=x+st[:,2]-1;bottom=y+st[:,3]-1;area=st[:,4];diag=np.maximum(1.,np.hypot(st[:,2]-1,st[:,3]-1))
 domain=cv2.distanceTransform(np.pad(valid.astype(np.uint8),1),cv2.DIST_C,3)[1:-1,1:-1]
 for j in range(1,n):
  k=j-1;xx=int(x[k]);yy=int(y[k]);ee=int(right[k]);bb=int(bottom[k])
  if area[k]>=minarea or diag[k]>=minlength:reasons['POTENTIAL_MEDIUM_LARGE']+=1;continue
  if area[k]>=maxarea:reasons['UNCERTAIN']+=1;continue
  if xx<margin or yy<margin or ee>=labels.shape[1]-margin or bb>=labels.shape[0]-margin:reasons['ASSOCIATION_SUPPORT']+=1;continue
  if float(domain[yy:bb+1,xx:ee+1].min())<=margin:reasons['UNCERTAIN']+=1;continue
  dx=np.maximum(np.maximum(x-ee,xx-right),0);dy=np.maximum(np.maximum(y-bb,yy-bottom),0);near=(dx<=margin)&(dy<=margin)&(area>=support_minarea);near[k]=False
  if near.any():reasons['ASSOCIATION_SUPPORT']+=1;continue
  safe.add(j);reasons['SAFE_SMALL_TO_SKIP']+=1
 return safe,reasons
def before_refinement(labels,stats,seed):
 p=STATE.params;radius=max(seed.max_extension_radius_px,seed.bounded_fallback_radius_px if seed.enable_bounded_extension_fallback else 0);margin=math.ceil(radius+max(p['J1_gap'],p['J2_gap'],p['J5_gap'])+p['bridge_corridor_radius']+2)
 l,t,r,b=STATE.window;cx,cy,ce,cb=STATE.core;valid=(STATE.ids[t:b,l:r]>0).copy()
 # 核心边界外视为不确定，跨Tile碎片不会早退。
 valid[:max(0,cy-t),:]=False;valid[max(0,cb-t):,:]=False;valid[:,:max(0,cx-l)]=False;valid[:,max(0,ce-l):]=False
 safe,reasons=_classify(labels,stats,valid,margin,p['medium_area'],p['medium_length'],seed.min_h_pixels_for_refinement,support_minarea=seed.min_h_pixels_for_refinement if p.get('micro_cluster_exit_proof_enabled',False) else 0)
 for k,v in reasons.items():STATE.count('H_'+k,v)
 STATE.count('H_initial_components',len(stats)-1);STATE.count('H_skipped_pixels',sum(int(stats[j,4]) for j in safe));STATE.params['H_support_margin_px']=margin
 return safe
def second_gate(mask):
 if not STATE.early:return mask
 n,labels,stats,_=cv2.connectedComponentsWithStats(mask.astype(np.uint8),connectivity=8);p=STATE.params
 margin=math.ceil(max(p['J1_gap'],p['J2_gap'],p['J5_gap'])+p['bridge_corridor_radius']+2);x,y,xx,yy=STATE.core;valid=STATE.ids[y:yy,x:xx]>0
 safe,reasons=_classify(labels,stats,valid,margin,p['medium_area'],p['medium_length'],p['medium_area'])
 for k,v in reasons.items():STATE.count('J4_'+k,v)
 STATE.count('J4_SECOND_GATE_components',len(safe));STATE.count('J4_SECOND_GATE_pixels',sum(int(stats[j,4]) for j in safe))
 return mask&~np.isin(labels,list(safe)) if safe else mask

