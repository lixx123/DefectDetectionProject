"""Immutable JSON packages with atomic publication and a repairable index."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import os, shutil, zipfile, hashlib
from domain.serialization import parse_json, to_dict
from infrastructure.storage.paths import result_key, safe_path, is_link
from infrastructure.storage.package import artifact_references, copy_checked, sha256, write_json
from infrastructure.storage.manifests import checked_config, build_manifest, summary_from_manifest
from .base import ResultRepository
from .errors import (RepositoryError, ResultAlreadyExistsError, ResultNotFoundError,
    PackageIntegrityError, UnsafeArtifactPathError, RepositoryIndexError, ConfigSnapshotError)
from .models import SaveRecord, RebuildReport, ExportRecord
from .index import JsonLineIndex, exclusive_lock
from .verifier import ResultPackageVerifier


class JsonResultRepository(ResultRepository):
    def __init__(self, root_dir=Path('output/results')):
        self.root = Path(root_dir).absolute()
        self.root.mkdir(parents=True,exist_ok=True)
        if is_link(self.root): raise UnsafeArtifactPathError('repository root is linked')
        self.verifier = ResultPackageVerifier()
        self.index = JsonLineIndex(self.root)
        self.last_index_report = None

    def _directory(self, key):
        key = result_key(key)
        path = self.root/key
        if is_link(path): raise UnsafeArtifactPathError('result directory is linked')
        if not path.is_dir(): raise ResultNotFoundError(key)
        return path

    def _discard_staging(self, stage):
        # Only this invocation's staging tree; never a formal result directory.
        if stage.parent.resolve()!=self.root.resolve() or not stage.name.startswith('.tmp_') or is_link(stage):
            raise UnsafeArtifactPathError('refusing unsafe staging cleanup')
        if stage.exists(): shutil.rmtree(stage)

    def save(self, result, source_run_dir, *, config_snapshot=None, config_provenance=None, log_source_dir=None):
        result.validate_final()
        key = result_key(result.result_id); final = self.root/key
        if final.exists() or is_link(final): raise ResultAlreadyExistsError(key)
        source = Path(source_run_dir)
        refs = artifact_references(result)
        try: config, origin = checked_config(result,source,config_snapshot)
        except FileNotFoundError as exc:
            raise ConfigSnapshotError('actual hash-matching config snapshot required; never reread current YAML') from exc
        stage = self.root/('.tmp_'+uuid4().hex[:16])
        published = False
        stage_created = False
        try:
            with exclusive_lock(self.root/('.save_'+key+'.lock'), result_lock=True):
                if final.exists() or is_link(final): raise ResultAlreadyExistsError(key)
                stage.mkdir(exist_ok=False)
                stage_created = True
                roles = {}
                for relative,digest in refs.items():
                    copy_checked(source,stage,relative,digest); roles[relative]='artifact'
                (stage/'metadata').mkdir(exist_ok=True)
                write_json(stage/'metadata/config_snapshot.json',to_dict(config)); roles['metadata/config_snapshot.json']='config'
                provenance = dict(config_provenance or {})
                provenance.setdefault('kind',origin)
                provenance['verified_config_hash']=config.config_hash()
                write_json(stage/'metadata/config_provenance.json',provenance); roles['metadata/config_provenance.json']='config_provenance'
                logs_root = Path(log_source_dir) if log_source_dir is not None else source
                missing_logs = []
                log_dir = logs_root/'logs'
                if is_link(log_dir): raise UnsafeArtifactPathError('linked log directory')
                if log_dir.is_dir():
                    for path in sorted(log_dir.rglob('*')):
                        relative = path.relative_to(logs_root).as_posix()
                        if is_link(path): raise UnsafeArtifactPathError('linked log entry')
                        if path.is_file(): copy_checked(logs_root,stage,relative); roles[relative]='log'
                if 'logs/inspection.log' not in roles: missing_logs.append('logs/inspection.log')
                result.save_json(stage/'result.json'); roles['result.json']='result'
                # fsync the codec output before publication.
                with (stage/'result.json').open('r+b') as stream: os.fsync(stream.fileno())
                saved_at = datetime.now(timezone.utc).isoformat()
                manifest = build_manifest(result,stage,roles,saved_at,config_origin=provenance['kind'],missing_logs=missing_logs)
                write_json(stage/'manifest.json',manifest)
                before = self.verifier.verify(stage,expected_result_id=key)
                if before.status!='PASS': raise PackageIntegrityError(str(before.to_dict()))
                if final.exists() or is_link(final): raise ResultAlreadyExistsError(key)
                # Same-volume directory rename: no partial formal package is visible.
                os.rename(stage,final); published = True
                after = self.verifier.verify(final)
                if after.status!='PASS': raise PackageIntegrityError(str(after.to_dict()))
        except RepositoryError: raise
        except FileNotFoundError as exc: raise PackageIntegrityError(f'missing package source: {exc}') from exc
        except Exception as exc: raise RepositoryError(f'package save failed: {exc}') from exc
        finally:
            if not published and stage_created and stage.exists(): self._discard_staging(stage)
        summary = summary_from_manifest(manifest)
        warnings = list(after.warnings)
        try:
            # The index is rebuilt from metadata of already validated packages.
            rows = self._cached_summaries(exclude={key})
            self.index.write(sorted([*rows,summary],key=lambda r:r.saved_at,reverse=True))
            index_status='PASS'
        except Exception as exc:
            index_status='INDEX_UPDATE_FAILED'; warnings.append(f'INDEX_UPDATE_FAILED: {exc}')
        return SaveRecord(summary,str(final),index_status,tuple(warnings))

    def load(self, result_id, *, verify='full'):
        if verify not in ('light','full'): raise ValueError('verify must be light or full')
        directory = self._directory(result_id)
        report, result = self.verifier.inspect(directory,full=verify=='full')
        if report.status!='PASS': raise PackageIntegrityError(str(report.to_dict()))
        return result

    def verify(self, result_id):
        try: directory = self._directory(result_id)
        except (ResultNotFoundError,UnsafeArtifactPathError) as exc:
            from .models import VerificationReport
            report=VerificationReport(errors=[str(exc)])
            if isinstance(exc,UnsafeArtifactPathError): report.unsafe_paths.append(str(exc))
            else: report.missing_files.append(str(result_id))
            return report
        return self.verifier.verify(directory)

    def _formal_dirs(self):
        return sorted(p for p in self.root.iterdir() if not p.name.startswith('.') and (p.is_dir() or is_link(p)))

    def _cached_summaries(self, *, exclude=frozenset()):
        directories = [p for p in self._formal_dirs() if p.name not in exclude]
        if not directories: return []
        rows = [r for r in self.index.read() if r.result_id not in exclude]
        if {r.result_id for r in rows}!={p.name for p in directories}: raise RepositoryIndexError('stale index result set')
        for row in rows:
            directory = self._directory(row.result_id)
            m = parse_json(safe_path(directory,'manifest.json').read_text(encoding='utf-8-sig'))
            if summary_from_manifest(m)!=row: raise RepositoryIndexError('index differs from manifest')
            entry = next(e for e in m['package_files'] if e['relative_path']=='result.json')
            if sha256(safe_path(directory,'result.json'))!=entry['sha256']:
                raise RepositoryIndexError('cached result JSON changed')
        return rows

    def list_results(self):
        try: rows = self._cached_summaries()
        except Exception as exc:
            self.last_index_report = self.rebuild_index()
            self.last_index_report.errors.insert(0,{"index_rebuilt_because":str(exc)})
            rows = self.last_index_report.indexed_results
        return sorted(rows,key=lambda r:r.saved_at,reverse=True)

    def rebuild_index(self):
        report = RebuildReport()
        for directory in self._formal_dirs():
            try:
                verification = self.verifier.verify(directory)
                if verification.status!='PASS':
                    report.skipped_corrupt_results.append(directory.name)
                    report.errors.append({'result_id':directory.name,'verification':verification.to_dict()})
                    continue
                manifest = parse_json(safe_path(directory,'manifest.json').read_text(encoding='utf-8-sig'))
                report.indexed_results.append(summary_from_manifest(manifest))
            except Exception as exc:
                report.skipped_corrupt_results.append(directory.name)
                report.errors.append({'result_id':directory.name,'error':str(exc)})
        report.indexed_results.sort(key=lambda r:r.saved_at,reverse=True)
        try: self.index.write(report.indexed_results)
        except RepositoryIndexError as exc: report.errors.append({'index':str(exc)}); report.status='INDEX_UPDATE_FAILED'
        if report.skipped_corrupt_results and report.status=='PASS': report.status='PARTIAL'
        self.last_index_report=report
        return report

    def query(self, *, sample_id=None, file_name=None, source_sha256=None, start_time=None,
              end_time=None, final_mode=None, fallback_used=None, min_defects=None, max_defects=None):
        def stamp(value):
            if value is None: return None
            time = datetime.fromisoformat(value) if isinstance(value,str) else value
            if time.tzinfo is None: raise ValueError('query times require timezone')
            return time
        start,end=stamp(start_time),stamp(end_time)
        if start and end and start>end: raise ValueError('start_time exceeds end_time')
        if min_defects is not None and (type(min_defects)is not int or min_defects<0): raise ValueError('invalid min_defects')
        if max_defects is not None and (type(max_defects)is not int or max_defects<0): raise ValueError('invalid max_defects')
        if min_defects is not None and max_defects is not None and min_defects>max_defects: raise ValueError('invalid count range')
        if fallback_used is not None and type(fallback_used)is not bool: raise ValueError('fallback_used must be bool')
        filters={'sample_id':sample_id,'file_name':file_name,'source_sha256':source_sha256,'final_mode':final_mode,'fallback_used':fallback_used}
        return [r for r in self.list_results() if all(v is None or getattr(r,k)==v for k,v in filters.items())
            and (start is None or datetime.fromisoformat(r.saved_at)>=start)
            and (end is None or datetime.fromisoformat(r.saved_at)<=end)
            and (min_defects is None or r.defect_count>=min_defects)
            and (max_defects is None or r.defect_count<=max_defects)]

    def find_by_source_sha256(self, digest): return self.query(source_sha256=digest)

    def export_package(self, result_id, zip_path):
        directory = self._directory(result_id)
        report = self.verifier.verify(directory)
        if report.status!='PASS': raise PackageIntegrityError(str(report.to_dict()))
        zip_path = Path(zip_path)
        if zip_path.resolve().is_relative_to(self.root.resolve()):
            raise UnsafeArtifactPathError('export must be outside repository')
        zip_path.parent.mkdir(parents=True,exist_ok=True)
        owned=False
        try:
            with zip_path.open('xb') as stream:
                owned=True
                with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as package:
                    manifest=parse_json((directory/'manifest.json').read_text(encoding='utf-8-sig'))
                    for relative in ['manifest.json',*[e['relative_path'] for e in manifest['package_files']]]:
                        package.write(safe_path(directory,relative),relative)
                stream.flush(); os.fsync(stream.fileno())
            with zipfile.ZipFile(zip_path) as package:
                if package.testzip() is not None: raise PackageIntegrityError('ZIP CRC failure')
                archived_manifest=parse_json(package.read('manifest.json').decode('utf-8-sig'))
                if archived_manifest!=manifest: raise PackageIntegrityError('manifest changed during export')
                if set(package.namelist())!={'manifest.json',*[e['relative_path'] for e in manifest['package_files']]}:
                    raise PackageIntegrityError('ZIP membership differs from manifest')
                for entry in manifest['package_files']:
                    with package.open(entry['relative_path']) as member:
                        digest=hashlib.file_digest(member,'sha256').hexdigest()
                    if digest!=entry['sha256'] or package.getinfo(entry['relative_path']).file_size!=entry['bytes']:
                        raise PackageIntegrityError('ZIP file differs from package manifest')
            record=ExportRecord(str(zip_path),sha256(zip_path),zip_path.stat().st_size)
            receipt=zip_path.with_name(zip_path.name+'.sha256')
            with receipt.open('x',encoding='ascii') as stream: stream.write(record.sha256+'\n')
            return record
        except Exception:
            if owned and zip_path.exists(): zip_path.unlink()
            raise
