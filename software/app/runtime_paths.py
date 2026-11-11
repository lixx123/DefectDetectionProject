"""Application locations only; never algorithm or review policy."""
from pathlib import Path
import sys


def application_root():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_root():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS).resolve()
    return application_root()


def output_root():
    return application_root() / 'output'


def logical_path(path):
    """Comparable Windows path, without the extended-length I/O prefix."""
    value=str(path)
    prefix=chr(92)*2+'?'+chr(92)
    if value.startswith(prefix+'UNC'+chr(92)):
        value=chr(92)*2+value[len(prefix)+4:]
    elif value.startswith(prefix):value=value[len(prefix):]
    return Path(value)


def native_path(path, *, force=False):
    """Win32 long-path spelling only; never changes path containment rules."""
    path=Path(path).absolute()
    if sys.platform!='win32':return path
    value=str(path);prefix=chr(92)*2+'?'+chr(92)
    if value.startswith(prefix) or (not force and len(value)<240):return path
    if value.startswith(chr(92)*2):return Path(prefix+'UNC'+chr(92)+value[2:])
    return Path(prefix+value)
