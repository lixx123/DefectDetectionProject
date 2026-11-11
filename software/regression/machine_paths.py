"""Source-only machine-path audit; historical data and reports are out of scope."""
import ast
import json
from pathlib import Path

SCOPES=('ui','tests','regression','scripts','application')


def machine_path(value):
    normalized=value.replace('\\','/').casefold()
    prefixes=(('d:', '疵病检测'), ('c:', 'users/'))
    return any(f'{drive}/{folder}' in normalized for drive,folder in prefixes)


def scan_machine_paths(root):
    root=Path(root)
    production=[]; permanent=[]; scanned=0
    for scope in SCOPES:
        for path in sorted((root/scope).rglob('*.py')):
            scanned+=1
            source=path.read_text(encoding='utf-8-sig')
            lines=set()
            for number,line in enumerate(source.splitlines(),1):
                if machine_path(line): lines.add(number)
            # Decode string escapes and constant concatenation as well.
            tree=ast.parse(source,filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node,ast.Constant) and isinstance(node.value,str) and machine_path(node.value):
                    lines.add(node.lineno)
            target=permanent if scope=='tests' else production
            target.extend(dict(path=path.relative_to(root).as_posix(),line=n) for n in sorted(lines))
    return dict(production_code_hits=production,permanent_test_hits=permanent,
                scanned_python_files=scanned,scopes=list(SCOPES),
                external_path_scripts=[dict(script='regression/reproduce_display_observation.py',path_source='CLI_ARGUMENT')],
                status='FAIL' if production or permanent else 'PASS')


if __name__=='__main__':
    report=scan_machine_paths(Path(__file__).resolve().parents[1])
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if report['status']=='PASS' else 1)
