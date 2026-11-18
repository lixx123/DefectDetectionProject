"""本阶段进程读写护栏；系统全局行为不冒充可观测。"""
import os,sys
from pathlib import Path
OUT=Path(os.environ["B151_RUN_OUTPUT"]).resolve();ROOT=Path(__file__).resolve().parents[3]
READS={};WRITES={};DENIED=[]
def norm(p):return os.path.normcase(os.path.abspath(os.fsdecode(p)))
def inside(p,r):return p==r or p.startswith(r+os.sep)
def activate(role):
 sys.dont_write_bytecode=True
 for key in ['TEMP','TMP','TMPDIR','MPLCONFIGDIR','PYTHONPYCACHEPREFIX']:
  p=OUT/'analysis_cache'/key.lower();p.mkdir(exist_ok=True);os.environ[key]=str(p)
 out=norm(OUT);code=[norm(ROOT/x) for x in ['src','scripts','config']];libs=norm(__import__('sysconfig').get_path('purelib'))
 raw={norm(os.environ["B151_RAW"])}
 bh={norm(ROOT/'outputs'/x) for x in ['case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy','case03k6_frame2_fused_blackhat/run_20261012_frame26_2_frozen_kernels_v1/frame26_2_fused_blackhat_exact.npy']}
 def deny(p,reason):DENIED.append(dict(path=p,reason=reason));raise PermissionError(reason+': '+p)
 def mutation(p):
  if isinstance(p,(str,bytes,os.PathLike)):
   n=norm(p)
   if not inside(n,out):deny(n,'OUTSIDE_STAGE_WRITE')
   WRITES[n]=WRITES.get(n,0)+1
 def hook(event,args):
  if event=='open':
   p=args[0]
   if not isinstance(p,(str,bytes,os.PathLike)):return
   n=norm(p);mode=args[1] or '';flags=args[2] if len(args)>2 else 0
   if any(k in str(mode) for k in 'wax+') or isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC):mutation(p);return
   if n.endswith('.raw') and n not in raw:deny(n,'UNAUTHORIZED_RAW')
   if role=='detector':
    if inside(n,norm(ROOT/'outputs')) and not inside(n,out) and n not in bh:deny(n,'HISTORY_OR_GT_FORBIDDEN')
    if inside(n,norm(OUT/'qa_eval')) or 'human_approved' in n:deny(n,'GT_FORBIDDEN')
    if n.endswith(('.csv','.npz','.npy','.json','.png','.xlsx')) and not inside(n,out) and n not in bh and not inside(n,libs) and not any(inside(n,x) for x in code):deny(n,'EXTERNAL_DETECTOR_DATA')
   READS[n]=READS.get(n,0)+1
  elif event in ['os.mkdir','os.remove','os.rmdir','os.truncate','os.chmod','os.utime']:mutation(args[0])
  elif event in ['os.rename','os.replace']:mutation(args[0]);mutation(args[1])
 sys.addaudithook(hook)
def receipt(role):return {'role':role,'argv':sys.argv,'reads':READS,'writes':WRITES,'denied':DENIED,'outside_write_attempts':sum(r['reason']=='OUTSIDE_STAGE_WRITE' for r in DENIED),'GT_violation_attempts':sum('GT' in r['reason'] or 'HISTORY' in r['reason'] for r in DENIED),'system_global_and_native_uninstrumented':'NOT_VERIFIABLE'}
