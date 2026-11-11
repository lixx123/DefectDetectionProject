"""Runtime integrity probes; file paths stay in memory, never in review data."""
from pathlib import Path
import hashlib
from .repository import ReviewConflict
from .model import digest,source_payload
from ..review_admission import load_policy


def file_digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def make_guard(package_dir,context,result=None):
    path=Path(package_dir)/'result.json'
    if result is not None and (Path(package_dir)/'manifest.json').is_file() and not path.is_file():raise ReviewConflict('RESULT_MISMATCH: formal source missing')
    expected=file_digest(path) if path.is_file() else None
    if result is not None and expected is not None:
        # Bind the already-loaded domain result to the current formal file, not
        # merely to a fresh file hash which could already represent a new result.
        from domain import InspectionResult
        try:
            current=InspectionResult.load_json(path)
            if digest(source_payload(current))!=context.source_result_digest:raise ReviewConflict('RESULT_MISMATCH')
        except (ValueError,OSError) as exc:
            raise ReviewConflict('RESULT_MISMATCH: formal source is changed or invalid') from exc
    def check():
        if result is not None and digest(source_payload(result))!=context.source_result_digest:raise ReviewConflict('RESULT_MISMATCH')
        policy=load_policy()
        if (policy.policy_id,policy.policy_version,policy.policy_hash)!=(context.policy_id,context.policy_version,context.policy_hash):raise ReviewConflict('POLICY_MISMATCH')
        if expected is not None and (not path.is_file() or file_digest(path)!=expected):raise ReviewConflict('RESULT_MISMATCH')
    return check
