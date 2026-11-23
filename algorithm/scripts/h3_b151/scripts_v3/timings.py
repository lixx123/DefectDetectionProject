"""有保护的函数计时/计数；逐函数包裹仅作用当前进程，并在finally恢复。

契约：
- 路径归属用resolve后的is_relative_to判断，不用字符串startswith。
- 同名函数可在多个模块各有一份实现，DATA以(定义模块,函数名)为键，不合并。
- 同一函数对象的别名共用同一个wrapper；已包裹对象不会二次包裹。
- instrument()不可重入，嵌套立即RuntimeError，绝不静默双重计时。
- inclusive含子调用，不能把各行inclusive相加当阶段总耗时；exclusive各行之和
  才是仪表覆盖到的时间。仪表自身开销单独测量并单独报告。
"""
import time,functools,sys
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parents[3]
CHAIN_ROOT=Path(__file__).resolve().parent
DATA=defaultdict(lambda:{'calls':0,'inclusive_seconds':0.,'exclusive_seconds':0.});STACK=[]
STATS={'wrapped_calls':0,'active':False,'stack_leftover':0}
NAMES={'hysteresis_window','detect_window_H_seeded','_refinement_by_H_seed','local_raw_statistics','decide_gate','extend_gate','extract_regions','max_feret_centers_px','max_hull_distance','associate_fragments','reconstruct_continuous_visual','candidate_seam_edges','moments_and_hulls','reconcile','compute_local_residual','compute_external_filter_context'}
def clear():DATA.clear();STACK.clear();STATS['wrapped_calls']=0;STATS['stack_leftover']=0
def wrap(fn,key):
 @functools.wraps(fn)
 def run(*args,**kw):
  start=time.perf_counter();entry=[0.];STACK.append(entry)
  try:return fn(*args,**kw)
  finally:
   dt=time.perf_counter()-start;STACK.pop();r=DATA[key];r['calls']+=1;r['inclusive_seconds']+=dt;r['exclusive_seconds']+=dt-entry[0]
   if STACK:STACK[-1][0]+=dt
   STATS['wrapped_calls']+=1
 run.__timings_wrapped__=True
 return run
def targets():
 """本次进程里实际加载、且位于正式src或当前链目录下的可计时函数。"""
 found={}
 for module in list(sys.modules.values()):
  file=getattr(module,'__file__',None)
  if not file:continue
  resolved=Path(file).resolve()
  if not (resolved.is_relative_to(PROJECT_ROOT/'src') or resolved.is_relative_to(CHAIN_ROOT)):continue
  for name,value in list(vars(module).items()):
   if not callable(value) or getattr(value,'__name__','') not in NAMES:continue
   if getattr(value,'__timings_wrapped__',False):continue
   key=(getattr(value,'__module__','?'),value.__name__)
   found.setdefault((module,name),key)
 return found
@contextmanager
def instrument():
 if STATS['active']:raise RuntimeError('timings.instrument() is not re-entrant')
 changed=[];cache={}
 for (module,name),key in targets().items():
  value=getattr(module,name)
  # 按函数对象复用wrapper，并用元组键区分不同模块中的同名实现。
  slot=id(value)
  if slot not in cache:cache[slot]=(wrap(value,key),value)
  wrapper,original=cache[slot]
  changed.append((module,name,original));setattr(module,name,wrapper)
 STATS['active']=True
 try:yield
 finally:
  try:
   for module,name,value in reversed(changed):setattr(module,name,value)
  finally:
   STATS['active']=False
   STATS['stack_leftover']=len(STACK)
   if STACK:STACK.clear()
def rows(s,a,mode):
 return [{'sample_id':s,'strategy':a,'mode':mode,'defining_module':k[0],'function':k[1],**v,
          'function_allocated_memory':'NOT_VERIFIABLE','physical_disk_IO':'NOT_VERIFIABLE'}
         for k,v in sorted(DATA.items())]
def stats():
 rows_=list(DATA.values())
 return dict(STATS,instrumented_functions=len(rows_),
   total_wrapped_calls=sum(r['calls'] for r in rows_),
   sum_exclusive_seconds=sum(r['exclusive_seconds'] for r in rows_),
   stack_leftover_note='entries still on the timing stack when instrument() exited (measured, not assumed); a wrapped generator abandoned mid-iteration is the only realistic source')
def measure_overhead(calls=20000):
 """测量wrapper自身簿记开销：对一个no-op计时，随后剔除探针统计。"""
 if STATS['active']:raise RuntimeError('measure_overhead requires an idle timer')
 probe=('timings','__overhead_probe__')
 wrapper=wrap(lambda:None,probe)
 start=time.perf_counter()
 for _ in range(calls):wrapper()
 per=(time.perf_counter()-start)/calls
 DATA.pop(probe,None);STATS['wrapped_calls']-=calls
 return per
