"""Rebuildable atomic JSONL cache; no database and no source-of-truth mutation."""
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4
import json, os, time
from .errors import RepositoryIndexError, ResultAlreadyExistsError
from .models import ResultSummary
from infrastructure.storage.paths import is_link


@contextmanager
def exclusive_lock(path, *, result_lock=False):
    try:
        with Path(path).open('x', encoding='utf-8') as stream:
            stream.write(str(os.getpid())); stream.flush(); os.fsync(stream.fileno())
    except FileExistsError as exc:
        error = ResultAlreadyExistsError if result_lock else RepositoryIndexError
        raise error('save/index lock already exists; no automatic stale-lock deletion') from exc
    try: yield
    finally: Path(path).unlink()


class JsonLineIndex:
    def __init__(self, root): self.root = Path(root)

    def read(self):
        path = self.root/'index.jsonl'
        if is_link(path): raise RepositoryIndexError('linked index')
        try:
            rows = [ResultSummary(**json.loads(line)) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
            if len({r.result_id for r in rows})!=len(rows): raise ValueError('duplicate index keys')
            return rows
        except Exception as exc:
            raise RepositoryIndexError(f'index unreadable: {exc}') from exc

    def write(self, summaries):
        temp = self.root/('.index_'+uuid4().hex+'.tmp')
        try:
            with exclusive_lock(self.root/'.index.lock'):
                with temp.open('x', encoding='utf-8', newline='\n') as stream:
                    for row in summaries:
                        stream.write(json.dumps(asdict(row),ensure_ascii=False,allow_nan=False)+'\n')
                    stream.flush(); os.fsync(stream.fileno())
                os.replace(temp,self.root/'index.jsonl')
        except RepositoryIndexError: raise
        except Exception as exc: raise RepositoryIndexError(str(exc)) from exc
        finally:
            if temp.exists(): temp.unlink()
