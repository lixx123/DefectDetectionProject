import argparse, os, sys, math, logging
from pathlib import Path
from prepare_raw import prepare

p=argparse.ArgumentParser()
p.add_argument('--input', required=True, type=Path)
p.add_argument('--mode', choices=('adaptive_h3','fixed'), default='adaptive_h3')
p.add_argument('--run-output', required=True, type=Path)
a=p.parse_args()
raw=a.input.resolve(strict=True)
output=a.run_output.resolve()
inp,plan=prepare(raw,output/'input')
os.environ['B151_RUN_OUTPUT']=str(output)
os.environ['B151_RAW']=str(raw)
(output/'analysis_cache').mkdir()
sys.path.insert(0,str(Path(__file__).resolve().parent/'scripts_v3'))
import detector
detector.math=math
logging.basicConfig(level=logging.INFO)
mode='A1' if a.mode=='adaptive_h3' else 'A0'
detector.one(inp,mode,'MEDIUM_LARGE_FAST',plan)
detector.dump('access.json',detector.guard.receipt('detector'))
