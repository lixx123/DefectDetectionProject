"""One application factory; frozen builds cannot use developer adapters."""
import sys
from app.runtime_paths import application_root

def create_detector(runtime_root):
    if getattr(sys,'frozen',False):
        from infrastructure.engines import DetectionEngineClient
        return DetectionEngineClient(application_root(),runtime_root)
    from core.detector import Detector
    return Detector(output_root=runtime_root)
