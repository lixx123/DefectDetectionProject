"""Runtime formal-package authority and read-only RAW evidence; never serialized."""
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
import hashlib
import os
import re
import stat
from .model import digest,source_payload,POLICY_HASH
from .repository import ReviewConflict


def stream_sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


class FormalResultAuthority:
    """Explicit configured repository provenance, not a directory-name heuristic."""
    def __init__(self,repository,*,staging_root=None):
        self.repository=repository;self.staging_root=Path(staging_root).resolve() if staging_root else None
    def load(self,result_id):
        root=self.repository.root.resolve()
        if self.staging_root is not None and (root==self.staging_root or root.is_relative_to(self.staging_root)):
            raise ReviewConflict('TEMPORARY_RESULT: staging cannot grant review authority')
        result=self.repository.load(result_id,verify='full')
        directory=(root/result_id).resolve()
        if directory.parent!=root:raise ReviewConflict('FORMAL_PACKAGE_MISMATCH')
        binding=FormalResultBinding(self,result,directory)
        return result,binding


class FormalResultBinding:
    def __init__(self,authority,result,directory):
        self.authority=authority;self.result=result;self.package_dir=directory;self.result_id=result.result_id
        self.source_digest=digest(source_payload(result))
        self.result_sha=stream_sha256(directory/'result.json');self.manifest_sha=stream_sha256(directory/'manifest.json')
    def require(self,context):
        if (context.result_id,context.source_result_digest)!=(self.result_id,self.source_digest):raise ReviewConflict('RESULT_MISMATCH')
        if digest(source_payload(self.result))!=self.source_digest:raise ReviewConflict('RESULT_MISMATCH')
        try:
            if stream_sha256(self.package_dir/'result.json')!=self.result_sha or stream_sha256(self.package_dir/'manifest.json')!=self.manifest_sha:
                raise ReviewConflict('RESULT_MISMATCH')
        except OSError:raise ReviewConflict('RESULT_MISMATCH: formal package missing') from None


class ReadLease:
    """Windows share-read only: forbid writes, truncation and rename while mapped."""
    def __init__(self,path):
        self.handle=None
        if os.name=='nt':
            import ctypes
            from ctypes import wintypes
            api=ctypes.WinDLL('kernel32',use_last_error=True)
            api.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
            api.CreateFileW.restype=wintypes.HANDLE
            handle=api.CreateFileW(str(path),0x80000000,1,None,3,0x80,None)
            if handle==ctypes.c_void_p(-1).value:raise ReviewConflict('RAW_UNAVAILABLE: cannot acquire read lease')
            api.CloseHandle.argtypes=[wintypes.HANDLE];api.CloseHandle.restype=wintypes.BOOL
            self.api,self.handle=api,handle
    def close(self):
        if self.handle is not None:self.api.CloseHandle(self.handle);self.handle=None


def fingerprint(path):
    s=Path(path).stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


class RawBinding:
    def __init__(self,result,path,sha256,provider,lease,file_identity):
        self.result_id=result.result_id;self.source_digest=digest(source_payload(result));self.path=Path(path)
        self.sha256=sha256;self.width=provider.width;self.height=provider.height
        self.provider=provider;self.lease=lease;self.file_identity=file_identity;self.verified=True;self.lock=RLock()
    def require(self,context):
        with self.lock:
            if not self.verified or (self.result_id,self.source_digest)!=(context.result_id,context.source_result_digest):raise ReviewConflict('RAW_MISMATCH')
            try:
                if fingerprint(self.path)!=self.file_identity:raise ReviewConflict('RAW_MISMATCH: file changed')
            except OSError:raise ReviewConflict('RAW_UNAVAILABLE') from None
    def crop(self,*args):
        with self.lock:
            if not self.verified:raise ReviewConflict('RAW_UNAVAILABLE')
            if fingerprint(self.path)!=self.file_identity:raise ReviewConflict('RAW_MISMATCH: file changed')
            return self.provider.crop(*args)
    def dn(self,*args):
        with self.lock:return self.provider.dn(*args) if self.verified else None
    def thumbnail(self,*args,**kwargs):
        with self.lock:
            if not self.verified:raise ReviewConflict('RAW_UNAVAILABLE')
            return self.provider.thumbnail(*args,**kwargs)
    def clear(self):
        with self.lock:
            self.verified=False
            try:self.provider.clear()
            finally:self.lease.close()


def validate_raw(path,result):
    """I/O must run in the existing worker. Never modifies result or metadata."""
    info=result.input_info
    if info.byte_order!='big' or info.container_bits!=16 or info.effective_bits!=12 or info.input_format not in ('RAW','raw'):
        raise ReviewConflict('RAW_UNSUPPORTED_FORMAT: require RAW / big / 16 container / 12 effective')
    if type(info.width_px) is not int or type(info.height_px) is not int or info.width_px<=0 or info.height_px<=0:
        raise ReviewConflict('RAW_INVALID_DIMENSIONS')
    if not isinstance(info.sha256,str) or not re.fullmatch('[a-fA-F0-9]{64}',info.sha256):raise ReviewConflict('RAW_MISSING_SHA256')
    path=Path(path).resolve()
    try:
        s=path.stat()
        if not stat.S_ISREG(s.st_mode):raise ReviewConflict('RAW_NOT_REGULAR_FILE')
        if s.st_size!=info.width_px*info.height_px*(info.container_bits//8):raise ReviewConflict('RAW_SIZE_MISMATCH')
        lease=ReadLease(path)
    except OSError:raise ReviewConflict('RAW_UNAVAILABLE') from None
    provider=None
    try:
        before=fingerprint(path);actual=stream_sha256(path)
        if fingerprint(path)!=before or actual.lower()!=info.sha256.lower():raise ReviewConflict('RAW_MISMATCH')
        from ui.raw_image_provider import RawImageProvider
        provider=RawImageProvider(path,info.width_px,info.height_px)
        if fingerprint(path)!=before:raise ReviewConflict('RAW_MISMATCH')
        return RawBinding(result,path,actual,provider,lease,before)
    except Exception as exc:
        if provider is not None:provider.clear()
        lease.close()
        if isinstance(exc,ReviewConflict):raise
        raise ReviewConflict('RAW_UNAVAILABLE: validation failed') from None


@dataclass(frozen=True)
class ReviewEligibility:
    formal_result: bool
    result_integrity: bool
    policy_match: bool
    raw_verified: bool
    can_create_session: bool
    can_submit_review: bool
    reason: str


class ReviewAccess:
    def __init__(self,formal_binding=None):self.formal_binding=formal_binding;self.raw=None
    def eligibility(self,context=None,stale=None):
        formal=isinstance(self.formal_binding,FormalResultBinding)
        integrity=not stale and (context is None or context.source_result_digest==self.formal_binding.source_digest) if formal else False
        policy=context is None or context.policy_hash==POLICY_HASH
        raw=bool(self.raw and self.raw.verified and formal and self.raw.result_id==self.formal_binding.result_id and self.raw.source_digest==self.formal_binding.source_digest)
        reason=('当前为临时检测结果，请先保存正式结果后再开始人工复核' if not formal else
                str(stale or 'RESULT_MISMATCH') if not integrity else 'POLICY_MISMATCH' if not policy else
                '缺少可验证原始图像证据，请先关联与当前结果 SHA256 一致的 RAW' if not raw else '真实 RAW 像素 · SHA256 已校验')
        return ReviewEligibility(formal,bool(integrity),policy,raw,formal and bool(integrity) and policy,formal and bool(integrity) and policy and raw,reason)
    def require(self,context,*,submit=False):
        if not isinstance(self.formal_binding,FormalResultBinding):raise ReviewConflict('TEMPORARY_RESULT: formal repository binding required')
        self.formal_binding.require(context)
        if context.policy_hash!=POLICY_HASH:raise ReviewConflict('POLICY_MISMATCH')
        if submit:
            if not self.raw:raise ReviewConflict('RAW_REQUIRED: verified RAW required')
            self.raw.require(context)
