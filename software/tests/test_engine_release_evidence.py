import json,pytest
from regression.engine_evidence import accept_evidence

def test_packaged_evidence_cannot_claim_a_different_head(tmp_path):
    p=tmp_path/'evidence.json';p.write_text(json.dumps(dict(tested_head='not_tested')))
    with pytest.raises(ValueError,match='HEAD mismatch'):accept_evidence(tmp_path,p,'final_head')

def test_missing_real_evidence_is_not_a_pass(tmp_path):
    with pytest.raises(FileNotFoundError):accept_evidence(tmp_path,tmp_path/'missing.json','head')


def test_system_security_allowance_is_narrow(tmp_path):
    from infrastructure.engines.runtime_audit import security_module_candidate
    root=tmp_path/'ProgramData'
    assert security_module_candidate(root/'Microsoft/Windows Defender/Platform/4.18/MpOav.dll',root)
    for path in [root/'other/MpOav.dll',root/'Microsoft/Windows Defender/Platform/4.18/python.dll',root/'Microsoft/Windows Defender/Platform/a/b/MpOav.dll',tmp_path/'.venv/MpOav.dll']:
        assert not security_module_candidate(path,root)


def test_verified_connection_status_is_metadata_only():
    from regression.engine_evidence import verified_config_metadata
    from configs.loader import load_config
    from domain.serialization import to_dict,from_dict
    from domain.configuration import InspectionConfig
    from copy import deepcopy
    actual=to_dict(load_config(__import__('pathlib').Path(__file__).resolve().parents[1]/'configs/production_v1.yaml'));expected=deepcopy(actual)
    expected['status']='MODEL_ONLY_NOT_CONNECTED_TO_ENGINE'
    normalized,changed=verified_config_metadata(expected,actual,from_dict(InspectionConfig,actual).config_hash())
    assert changed and normalized==from_dict(InspectionConfig,expected).config_hash()

@pytest.mark.parametrize('field',['spatial_scale','parameters','status'])
def test_connection_status_exception_never_allows_tuning_changes(field):
    from regression.engine_evidence import verified_config_metadata
    from configs.loader import load_config
    from domain.serialization import to_dict,from_dict
    from domain.configuration import InspectionConfig
    from copy import deepcopy
    actual=to_dict(load_config(__import__('pathlib').Path(__file__).resolve().parents[1]/'configs/production_v1.yaml'));expected=deepcopy(actual)
    expected['status']='MODEL_ONLY_NOT_CONNECTED_TO_ENGINE'
    if field=='spatial_scale':actual['calibration']['spatial_scale_um_per_px']=9.9
    elif field=='parameters':actual['algorithm_parameters']={'threshold':123}
    else:actual['status']='UNVERIFIED'
    with pytest.raises(ValueError):verified_config_metadata(expected,actual,from_dict(InspectionConfig,actual).config_hash())
