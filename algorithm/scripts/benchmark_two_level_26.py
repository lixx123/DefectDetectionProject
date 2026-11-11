"""Sequential, fail-fast six-run 26-only benchmark; each mode is a fresh process.

The first full baseline may already be running in this task. Waiting for its
acceptance is explicit; no historical result is counted as newly computed.
"""
from pathlib import Path
import sys,json,time,subprocess
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts.run_unified_final_revision import write_json


def run(version='v1'):
    root=C.OUTPUT_ROOT/f'K8A_TWO_LEVEL_20261020_{version}'
    if not root.is_dir():raise FileNotFoundError(root)
    first=C.OUTPUT_ROOT/f'K8A_TWO_LEVEL_26_1_FULL_20261020_{version}'
    start=time.monotonic()
    while not (first/'acceptance.json').exists():
        if (first/'FAILED.json').exists():raise RuntimeError((first/'FAILED.json').read_text(encoding='utf8'))
        if time.monotonic()-start>3600:raise TimeoutError('first current-task full baseline incomplete')
        time.sleep(5)
    rows=[]
    for frame in (1,2):
        for mode in ('full','roi-j4','roi-bh'):
            name=f'K8A_TWO_LEVEL_26_{frame}_{mode.upper().replace("-","_")}_20261020_{version}'
            out=C.OUTPUT_ROOT/name
            command=[sys.executable,str(ROOT/'main.py'),'--case','unified-final','--input',str(C.DATA_ROOT/f'26 ({frame}).raw'),
                '--roi-mode',mode,'--run-id',name]
            write_json(root/'benchmark_progress.json',{'frame':frame,'mode':mode,'output':str(out),'command':command,'phase':'RUNNING'})
            print('BENCHMARK_STAGE',frame,mode,flush=True)
            if not (frame==1 and mode=='full'):
                with (root/f'{frame}_{mode}_execution.log').open('x',encoding='utf8') as log:
                    subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            check=[sys.executable,str(ROOT/'scripts/verify_two_level_unified.py'),'--output',str(out),'--frame',str(frame)]
            with (root/f'{frame}_{mode}_independent_QA.log').open('x',encoding='utf8') as log:
                subprocess.run(check,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            acceptance=json.loads((out/'acceptance.json').read_text(encoding='utf8'))
            rows.append({'frame':frame,'mode':mode,'output':str(out),'command':command,**acceptance})
            write_json(root/'completed_benchmarks.json',rows)
            if frame==1 and mode=='full':
                command=[sys.executable,str(ROOT/'scripts/verify_two_level_W005.py'),'--full',str(out),'--output',str(root/'W005_NONWORK_DIAGNOSTIC')]
                with (root/'W005_execution.log').open('x',encoding='utf8') as log:
                    subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    write_json(root/'benchmark_progress.json',{'phase':'ALL_SIX_FRESH_RUNS_AND_QA_COMPLETE','completed':len(rows)})
    print('BENCHMARK_COMPLETE',len(rows),flush=True)


if __name__=='__main__':run()
