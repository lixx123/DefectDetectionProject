"""有保护的函数计时/计数；逐函数包裹仅作用当前进程，并在finally恢复。"""
import time,functools,sys
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from common import ROOT,OUT
DATA=defaultdict(lambda:{'calls':0,'inclusive_seconds':0.,'exclusive_seconds':0.});STACK=[]
NAMES={'hysteresis_window','detect_window_H_seeded','_refinement_by_H_seed','local_raw_statistics','decide_gate','extend_gate','extract_regions','max_feret_centers_px','max_hull_distance','associate_fragments','reconstruct_continuous_visual','candidate_seam_edges','moments_and_hulls','reconcile','compute_local_residual','compute_external_filter_context'}
def clear():DATA.clear();STACK.clear()
def wrap(fn,key):
 @functools.wraps(fn)
 def run(*args,**kw):
  start=time.perf_counter();entry=[0.];STACK.append(entry)
  try:return fn(*args,**kw)
  finally:
   dt=time.perf_counter()-start;STACK.pop();r=DATA[key];r['calls']+=1;r['inclusive_seconds']+=dt;r['exclusive_seconds']+=dt-entry[0]
   if STACK:STACK[-1][0]+=dt
 return run
@contextmanager
def instrument():
 changed=[];cache={}
 for module in list(sys.modules.values()):
  file=getattr(module,'__file__',None)
  if not file or not (str(file).startswith(str(ROOT/'src')) or str(file).startswith(str(OUT/'scripts'))):continue
  for name,value in list(vars(module).items()):
   if callable(value) and getattr(value,'__name__','') in NAMES:
    if id(value) not in cache:cache[id(value)]=wrap(value,value.__name__)
    changed.append((module,name,value));setattr(module,name,cache[id(value)])
 try:yield
 finally:
  for module,name,value in reversed(changed):setattr(module,name,value)
def rows(s,a,mode):
 return [{'sample_id':s,'strategy':a,'mode':mode,'function':k,**v,'function_allocated_memory':'NOT_VERIFIABLE','physical_disk_IO':'NOT_VERIFIABLE'} for k,v in sorted(DATA.items())]
