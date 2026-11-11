from pathlib import Path
import hashlib,json
from infrastructure.engines.manifest import PROFILE,canonical,sha

def package(root,version='1.0.0'):
    root=Path(root);root.mkdir(parents=True)
    (root/'engine_runner.exe').write_bytes(b'UNIT_STUB_NOT_FOR_RELEASE')
    (root/'payload.bin').write_bytes(b'UNIT_PAYLOAD')
    files={p.name:sha(p) for p in root.iterdir()}
    data=dict(engine_id='reference',engine_version=version,protocol_version='1.0',output_schema_version='1.0',runner='engine_runner.exe',runner_sha256=files['engine_runner.exe'],algorithm_source_sha256='a'*64,engine_bundle_sha256=hashlib.sha256(canonical(files)).hexdigest(),config_version='0.2.0',supported_input=PROFILE,files=files)
    save(root,data);return root,data

def save(root,data):(root/'engine_manifest.json').write_text(json.dumps(data),encoding='utf-8')
