"""Structured verification; package manifests cannot vouch for themselves."""
from pathlib import Path
from datetime import datetime
from domain import InspectionResult
from domain.serialization import parse_json
from infrastructure.storage.paths import result_key, relative_path, safe_path, is_link
from infrastructure.storage.package import sha256, artifact_references
from infrastructure.storage.manifests import result_metadata, checked_config, validate_manifest_shape
from .models import VerificationReport
from .errors import UnsafeArtifactPathError


class ResultPackageVerifier:
    def inspect(self, package_dir, *, expected_result_id=None, full=True):
        root = Path(package_dir); report = VerificationReport(); result = None
        try:
            key = result_key(expected_result_id if expected_result_id is not None else root.name)
            manifest_path = safe_path(root,'manifest.json')
            manifest = parse_json(manifest_path.read_text(encoding='utf-8-sig'))
            validate_manifest_shape(manifest)
            result_path = safe_path(root,'result.json')
            result = InspectionResult.load_json(result_path); report.result_json_valid = True
            result.validate_final(); report.validate_final = True
            if result.result_id != key or manifest.get('result_id') != key:
                raise ValueError('directory/result/manifest result_id mismatch')
            if manifest.get('package_format_version')!='1.0': raise ValueError('unsupported package format')
            for field, value in result_metadata(result).items():
                if manifest.get(field) != value: raise ValueError(f'manifest/result metadata mismatch: {field}')
            stamp = datetime.fromisoformat(manifest['saved_at'])
            if stamp.tzinfo is None: raise ValueError('saved_at requires timezone')
            refs = artifact_references(result)
            entries = manifest['package_files']
            if not isinstance(entries,list): raise ValueError('package_files must be a list')
            listed = {}; aliases = set(); artifacts = {}
            for entry in entries:
                relative = relative_path(entry['relative_path'])
                if relative == 'manifest.json' or relative.casefold() in aliases:
                    raise ValueError('duplicate/self manifest entry')
                aliases.add(relative.casefold()); listed[relative] = entry
                digest = entry['sha256']
                if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
                    raise ValueError('invalid manifest SHA256')
                if type(entry['bytes']) is not int or entry['bytes']<0: raise ValueError('invalid file bytes')
                if entry['role'] not in ('result','artifact','log','config','config_provenance'):
                    raise ValueError('unknown file role')
                if entry['role']=='artifact': artifacts[relative]=entry
                try:
                    path = safe_path(root,relative)
                except FileNotFoundError:
                    report.missing_files.append(relative); continue
                except UnsafeArtifactPathError:
                    report.unsafe_paths.append(relative); continue
                if full or relative == 'result.json':
                    if sha256(path)!=digest or path.stat().st_size!=entry['bytes']:
                        report.hash_mismatches.append(relative)
            for required, role in (('result.json','result'),('metadata/config_snapshot.json','config'),
                                   ('metadata/config_provenance.json','config_provenance')):
                if required not in listed or listed[required]['role'] != role:
                    raise ValueError(f'missing required package record: {required}')
            if refs.keys()!=artifacts.keys(): raise ValueError('manifest/artifact reference coverage differs')
            if any(artifacts[p]['sha256']!=digest for p,digest in refs.items()):
                raise ValueError('manifest/reference SHA256 mismatch')
            if manifest.get('artifact_count')!=len(artifacts) or manifest.get('artifact_total_bytes')!=sum(e['bytes'] for e in artifacts.values()):
                raise ValueError('manifest artifact totals mismatch')
            checked_config(result,root)
            # Parse provenance as data; never execute configuration content.
            parse_json(safe_path(root,'metadata/config_provenance.json').read_text(encoding='utf-8-sig'))
            for path in root.rglob('*'):
                relative = path.relative_to(root).as_posix()
                if is_link(path): report.unsafe_paths.append(relative)
                elif path.is_file() and relative not in listed and relative!='manifest.json':
                    report.unexpected_files.append(relative)
            report.missing_logs = list(manifest.get('missing_logs', []))
            if 'logs/inspection.log' not in listed:
                if 'logs/inspection.log' not in report.missing_logs: report.missing_logs.append('logs/inspection.log')
                report.warnings.append('INSPECTION_LOG_MISSING')
            report.manifest_valid = True
        except UnsafeArtifactPathError as exc:
            report.unsafe_paths.append(str(exc)); report.errors.append(str(exc))
        except FileNotFoundError as exc:
            report.missing_files.append(str(exc)); report.errors.append(str(exc))
        except Exception as exc:
            report.errors.append(f'{type(exc).__name__}: {exc}')
        if (report.result_json_valid and report.validate_final and report.manifest_valid
                and not any((report.missing_files,report.hash_mismatches,report.unsafe_paths,report.unexpected_files,report.errors))):
            report.status='PASS'
        return report, result

    def verify(self, package_dir, *, expected_result_id=None, full=True):
        return self.inspect(package_dir, expected_result_id=expected_result_id, full=full)[0]
