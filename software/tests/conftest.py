"""Markers only for existing tests; never relax or replace their assertions."""
from pathlib import Path
import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        module=Path(str(item.path)).name; name=item.originalname or item.name
        golden=(module=='test_phase4_real_repository.py'
            or module=='test_phase3_reference_outputs.py' and name.startswith('test_real_frozen_')
            or module=='test_phase3_revision.py' and name in ('test_real_remapped_snapshots','test_focus_candidate_from_real_full_ledger'))
        probe=(module=='test_phase3_reference_outputs.py' and name in (
            'test_original_sentinel_guard_really_rejects_uncomputed_values',
            'test_worker_pins_reference_namespace_despite_software_scripts_package'))
        if golden: item.add_marker(pytest.mark.golden); item.add_marker(pytest.mark.slow)
        elif probe: item.add_marker(pytest.mark.reference_probe); item.add_marker(pytest.mark.integration)
        elif item.get_closest_marker('golden') is None and item.get_closest_marker('real_engine') is None:
            item.add_marker(pytest.mark.unit)
        if module.startswith('test_phase4'): item.add_marker(pytest.mark.repository)
        if any(word in name for word in ('unsafe','escape','junction','corrupt','tamper','hash','sentinel')):
            item.add_marker(pytest.mark.security)
