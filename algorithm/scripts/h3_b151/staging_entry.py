"""Official B151-H3 entry. H3 per-band adaptive thresholds are the only mode.

The run-folder strategy token stays 'A1' so historical outputs remain
addressable; it now denotes exactly one contract (P95/P99.9 per band).
"""
import argparse, os, sys, logging
from pathlib import Path
from prepare_raw import prepare

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input', required=True, type=Path)
    p.add_argument('--run-output', required=True, type=Path)
    p.add_argument('--edge-spots', choices=('on','off'), default=None,
                   help='Explicit A/B override; omission uses user_config')
    a=p.parse_args()
    if a.edge_spots is not None:
        from config import user_config
        user_config.H3_EDGE_SPOTS_ENABLED = a.edge_spots == 'on'
    raw=a.input.resolve(strict=True)
    output=a.run_output.resolve()
    inp,plan=prepare(raw,output/'input')
    os.environ['B151_RUN_OUTPUT']=str(output)
    os.environ['B151_RAW']=str(raw)
    (output/'analysis_cache').mkdir()
    sys.path.insert(0,str(Path(__file__).resolve().parent/'scripts_v3'))
    import detector
    logging.basicConfig(level=logging.INFO)
    detector.one(inp,'A1','MEDIUM_LARGE_FAST',plan)
    # 大内存中间残差层(Gaussian22/Closing61/DoG, 约1.2GB)可由 RAW 重算，
    # 检测完成后删除，只保留必要结果(最终对象CSV/精确mask/图/指标)。
    for _name in ('residual_gaussian22.npy','residual_closing61.npy','dog.npy'):
        _p=output/'input'/_name
        if _p.exists():_p.unlink()
    detector.dump('access.json',detector.guard.receipt('detector'))


if __name__ == "__main__":
    main()
