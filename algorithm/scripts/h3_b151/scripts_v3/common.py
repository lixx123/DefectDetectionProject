"""公共I/O与冻结路径；不读取人工真值。"""
from pathlib import Path
import os,sys,json,csv,hashlib,time,logging,platform,ctypes
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ["B151_RUN_OUTPUT"]).resolve()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def dump(p,v):
 p=OUT/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else str(x)),encoding='utf-8')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()
def csvout(p,v,columns=None):
 p=OUT/p;p.parent.mkdir(parents=True,exist_ok=True);df=v if isinstance(v,pd.DataFrame) else pd.DataFrame(v,columns=columns);df.to_csv(p,index=False,encoding='utf-8-sig',na_rep='NOT_VERIFIABLE');return df
def memory():
 class M(ctypes.Structure):
  _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong),('PeakWorkingSetSize',ctypes.c_size_t),('WorkingSetSize',ctypes.c_size_t),('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t)]
 m=M();m.cb=ctypes.sizeof(m)
 try:
  k=ctypes.windll.kernel32;k.GetCurrentProcess.restype=ctypes.c_void_p
  ok=ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(m),m.cb)
  return {'rss_bytes':m.WorkingSetSize,'process_lifetime_peak_rss_bytes':m.PeakWorkingSetSize} if ok else {'rss_bytes':'NOT_VERIFIABLE'}
 except Exception:return {'rss_bytes':'NOT_VERIFIABLE'}
