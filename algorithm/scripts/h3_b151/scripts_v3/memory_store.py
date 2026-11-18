"""算法必需内部源状态只留内存；QA明细只能写qa_full_reference。"""
import io
from collections import Counter
import numpy as np
from common import OUT,dump,csvout
MODE='FAST';ROOT=None;MASKS={};ROWS={};TRACE={};EVENTS=Counter()
def reset(mode,root):
 global MODE,ROOT
 MODE=mode;ROOT=root;MASKS.clear();ROWS.clear();TRACE.clear();EVENTS.clear()
def put_mask(name,**data):
 keep={k:data[k] for k in ['grouped_source_only_i32','inferred_bridge_i32','core_xyxy']}
 f=io.BytesIO();np.savez_compressed(f,**keep);MASKS[name]=f.getvalue()
 if MODE=='QA':
  p=ROOT/'tile_masks';p.mkdir(parents=True,exist_ok=True);(p/(name+'.npz')).write_bytes(f.getvalue())
def load(name):
 with np.load(io.BytesIO(MASKS[name])) as z:return z['grouped_source_only_i32'].copy(),tuple(z['core_xyxy'])
def all_data(name):
 with np.load(io.BytesIO(MASKS[name])) as z:return {k:z[k].copy() for k in z.files}
def put_rows(name,rows):
 ROWS[name]=rows
 if MODE=='QA':csvout(str((ROOT/'tile_objects'/f'{name}.csv').relative_to(OUT)),rows)
def event(path,body):
 EVENTS['J4_internal_event']+=1
 if MODE=='QA':dump(str(path.relative_to(OUT)),body)
def capture_stage(dest,name,window,core,response,low,high,detection):
 if MODE!='QA':return
 p=ROOT/'stage_audit';p.mkdir(parents=True,exist_ok=True)
 np.savez_compressed(p/(name+'.npz'),core=core,window=window,THRESHOLD_H=detection['maps']['h_original'],POST_FGH=detection['maps']['fused_joint_display'])
