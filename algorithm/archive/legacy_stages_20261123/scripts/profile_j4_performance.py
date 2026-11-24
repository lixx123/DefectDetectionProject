"""Independent J4 diagnostics; never selects or changes production parameters."""
from pathlib import Path
import sys,argparse,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from scripts.j4_profile_tools.common import OUT,dump
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['baseline','audit','profile','report','all'],default='all');a=p.parse_args()
    if a.stage in ('baseline','all'):
        from scripts.j4_profile_tools.common import preflight
        preflight()
    if a.stage in ('audit','all'):
        from scripts.j4_profile_tools.spatial import audit
        audit()
    if a.stage in ('profile','all'):
        from scripts.j4_profile_tools.profiler import profile
        profile()
    if a.stage in ('report','all'):
        from scripts.j4_profile_tools.reporting import report
        report()
if __name__=='__main__':
    try:main()
    except Exception:
        OUT.mkdir(parents=True,exist_ok=True);dump(OUT/'DIAGNOSTIC_FAILURE.json',dict(status='FAIL',traceback=traceback.format_exc()));raise
