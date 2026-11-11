"""Packaging path and impact boundaries; no real engine or RAW."""
from pathlib import Path
import sys
from app import runtime_paths
from regression.policies import code_impact


def test_development_root_is_cwd_independent(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runtime_paths.application_root()==Path(__file__).resolve().parents[1]
    assert runtime_paths.output_root()==runtime_paths.application_root()/'output'


def test_frozen_resources_and_writable_root_are_distinct(tmp_path,monkeypatch):
    exe=tmp_path/'中文发布'/'DefectInspectionSoftware.exe'
    bundle=exe.parent/'_internal'
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'executable',str(exe))
    monkeypatch.setattr(sys,'_MEIPASS',str(bundle),raising=False)
    assert runtime_paths.application_root()==exe.parent
    assert runtime_paths.resource_root()==bundle
    assert runtime_paths.output_root()==exe.parent/'output'
    assert not exe.parent.exists()  # Lookup has no write side effects.


def test_release_scope_does_not_hide_business_changes():
    assert not code_impact(['app/runtime_paths.py','packaging/defect_inspection.spec'])['real_engine_required']
    for name in ['core/pipeline.py','application/inspection_service.py','domain/defect.py','packaging/unreviewed_engine.py']:
        assert code_impact([name])['real_engine_required']
