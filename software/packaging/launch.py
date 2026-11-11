"""Frozen entry point; QA is explicit, local and never runs detection."""
import sys
import os
import traceback
from app.runtime_paths import output_root


def main():
    # Frozen light styles must not inherit a conflicting Windows dark palette.
    # Qt platform setup only; the source widget styles are unchanged.
    if sys.platform == 'win32' and os.environ.get('QT_QPA_PLATFORM', 'windows') == 'windows':
        os.environ['QT_QPA_PLATFORM'] = 'windows:darkmode=0'
    output_root().joinpath('runtime').mkdir(parents=True, exist_ok=True)
    if '--ledger-acceptance' in sys.argv:
        from ui.ledger_acceptance import run
        return run(sys.argv[sys.argv.index('--ledger-acceptance')+1])
    if '--engine-tool' in sys.argv:
        from tools.install_engine import main as engine_tool
        return engine_tool(sys.argv[sys.argv.index('--engine-tool')+1:])
    if '--engine-acceptance' in sys.argv:
        from release_engine_qa import run
        return run(sys.argv[sys.argv.index('--engine-acceptance')+1])
    if '--release-acceptance' in sys.argv:
        from release_qa import run
        return run(sys.argv[sys.argv.index('--release-acceptance') + 1])
    import logging
    from ui.runtime_log import ApplicationLog
    log=ApplicationLog(output_root()/'runtime/gui_errors.log')
    log.event(logging.INFO,'startup','RELEASE_START','发布版启动')
    log.close()
    from app.main import main as application_main
    return application_main()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        with output_root().joinpath('runtime/launcher_error.log').open('a', encoding='utf-8') as stream:
            traceback.print_exc(file=stream)
        raise
