"""Offline install/select tool; invoke through the GUI exe --engine-tool."""
import argparse,json
from pathlib import Path
from infrastructure.engines import EngineRegistry

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path);p.add_argument('--release-root',required=True,type=Path)
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('install');a.add_argument('package',type=Path);a.add_argument('--no-activate',action='store_true')
    a=sub.add_parser('select');a.add_argument('engine_id');a.add_argument('engine_version')
    sub.add_parser('list');args=p.parse_args(argv);r=EngineRegistry(args.release_root)
    if args.command=='install':result=r.install(args.package,activate=not args.no_activate).identity
    elif args.command=='select':result=r.select(args.engine_id,args.engine_version).identity
    else:result=[m.identity for m in r.discover()]
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));return 0

if __name__=='__main__':raise SystemExit(main())
