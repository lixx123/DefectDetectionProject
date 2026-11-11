"""Package protocol v1 is independent of InspectionResult schema 1.0."""
from dataclasses import asdict
from pathlib import PureWindowsPath
from domain.configuration import InspectionConfig
from domain.serialization import from_dict, to_dict, parse_json
from infrastructure.repositories.errors import ConfigSnapshotError, ManifestError
from infrastructure.repositories.models import ResultSummary
from .package import sha256
from .paths import safe_path


def checked_config(result, source_run_dir, supplied=None):
    if supplied is None:
        source = safe_path(source_run_dir, 'metadata/config_snapshot.json')
        supplied = parse_json(source.read_text(encoding='utf-8-sig'))
        origin = 'RUN_SNAPSHOT'
    else:
        origin = 'CALLER_HASH_VERIFIED'
    try:
        config = from_dict(InspectionConfig, to_dict(supplied) if isinstance(supplied, InspectionConfig) else supplied)
    except Exception as exc:
        raise ConfigSnapshotError(f'invalid config snapshot: {exc}') from exc
    algorithm = result.algorithm_info
    if (config.config_hash()!=algorithm.config_hash or config.config_name!=algorithm.config_name
            or config.config_version!=algorithm.config_version or config.calibration!=result.calibration_info
            or config.pipeline_mode!=result.execution_info.requested_mode):
        raise ConfigSnapshotError('snapshot does not match original config hash/name/version/calibration/mode')
    return config, origin


def summary_from_manifest(m):
    return ResultSummary(**{key: m[key] for key in ResultSummary.__dataclass_fields__})


def result_metadata(result):
    return dict(schema_version=result.schema_version, result_id=result.result_id, task_id=result.task_id,
        software_version=result.algorithm_info.software_version,
        algorithm_version=result.algorithm_info.algorithm_version,
        config_name=result.algorithm_info.config_name, config_version=result.algorithm_info.config_version,
        config_hash=result.algorithm_info.config_hash,
        source_file_name=result.input_info.file_name, file_name=result.input_info.file_name,
        sample_id=result.input_info.sample_id, source_sha256=result.input_info.sha256,
        final_mode=result.execution_info.final_mode.value,
        fallback_used=result.execution_info.fallback_used, defect_count=len(result.defects),
        total_area_px=result.statistics.total_defect_area_px)


def build_manifest(result, stage, roles, saved_at, *, config_origin, missing_logs):
    entries = []
    for relative, role in sorted(roles.items()):
        path = safe_path(stage,relative)
        entries.append(dict(relative_path=relative,sha256=sha256(path),bytes=path.stat().st_size,role=role))
    artifacts = [e for e in entries if e['role']=='artifact']
    manifest = dict(package_format_version='1.0', **result_metadata(result), saved_at=saved_at,
        artifact_count=len(artifacts), artifact_total_bytes=sum(e['bytes'] for e in artifacts),
        package_files=entries, config_snapshot_origin=config_origin, missing_logs=missing_logs)
    validate_manifest_shape(manifest)
    return manifest


def validate_manifest_shape(manifest):
    def walk(value):
        if isinstance(value,str) and (value.startswith('/') or PureWindowsPath(value).drive or value.startswith('\\')):
            raise ManifestError('manifest contains absolute/drive path text')
        if isinstance(value,dict):
            for child in value.values(): walk(child)
        elif isinstance(value,list):
            for child in value: walk(child)
    walk(manifest)
    for name in ('defect_count','artifact_count','artifact_total_bytes'):
        if type(manifest.get(name)) is not int or manifest[name]<0:
            raise ManifestError('invalid manifest count: '+name)
    if type(manifest.get('fallback_used')) is not bool:
        raise ManifestError('fallback_used must be bool')
    if not isinstance(manifest.get('missing_logs'),list) or any(not isinstance(p,str) for p in manifest['missing_logs']):
        raise ManifestError('missing_logs must be a string list')
