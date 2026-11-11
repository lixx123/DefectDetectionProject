"""Bounded UTF-8 application diagnostics, separate from algorithm/review audit."""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

class ApplicationLog:
    def __init__(self,path,*,max_bytes=1024*1024,backup_count=3):
        self.path=Path(path);self.write_failed=False;self.handler=None
        self.logger=logging.Logger('defect.gui',level=logging.INFO)
        self.fallback=logging.StreamHandler(sys.stderr)
        self.formatter=logging.Formatter('timestamp=%(asctime)s level=%(levelname)s %(message)s')
        self.fallback.setFormatter(self.formatter)
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            self.handler=RotatingFileHandler(self.path,maxBytes=max_bytes,backupCount=backup_count,encoding='utf-8')
            self.handler.setFormatter(self.formatter)
            # logging normally swallows emit errors. Re-raise into this adapter so
            # disk failure is observable and the worker can still finish safely.
            self.handler.handleError=lambda record:(_ for _ in ()).throw(OSError('application log write failed'))
            self.logger.addHandler(self.handler)
        except OSError:self.write_failed=True

    def event(self,level,operation,code,message,*,exc=None,**context):
        fields=' '.join(f'{k}={v}' for k,v in context.items() if v is not None)
        text=f'operation={operation} event={code} message={message} {fields}'
        record=self.logger.makeRecord(self.logger.name,level,'',0,text,(),(type(exc),exc,exc.__traceback__) if exc else None)
        try:
            if self.handler is None:raise OSError('application log unavailable')
            self.logger.handle(record)
        except Exception:
            self.write_failed=True
            # Logging failure is flagged and routed to developer stderr, never
            # allowed to suppress the operation result/error/finished signals.
            try:self.fallback.handle(record)
            except Exception:self.write_failed=True

    def close(self):
        if self.handler:
            try:self.handler.close()
            except OSError:self.write_failed=True
