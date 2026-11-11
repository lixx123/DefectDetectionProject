"""User-declared spatial scale, distinct from metrological calibration."""
from dataclasses import dataclass, replace
import math
from .common import Record, nonnegative
from .enums import ScaleSource

# ================= 用户输入变量区 =================
# 空间尺度 μm/px；未来由GUI/YAML覆盖，不写入算法函数。
SPATIAL_SCALE_UM_PER_PX = 3.2


@dataclass(kw_only=True)
class CalibrationInfo(Record):
    spatial_scale_um_per_px: float | None = SPATIAL_SCALE_UM_PER_PX
    scale_source: ScaleSource = ScaleSource.DEFAULT
    calibration_id: str | None = None
    calibration_time: str | None = None
    valid: bool = True
    reference_plane: str = "USER_DECLARED"
    metrologically_calibrated: bool = False

    def __post_init__(self):
        value = self.spatial_scale_um_per_px
        if value is not None and (isinstance(value, bool) or not math.isfinite(value) or value <= 0):
            raise ValueError("spatial scale must be finite and positive, or None")
        if self.valid and (value is None or self.scale_source == ScaleSource.UNKNOWN):
            raise ValueError("a valid scale requires a value and known source")
        if value is not None and value != SPATIAL_SCALE_UM_PER_PX and self.scale_source == ScaleSource.DEFAULT:
            self.scale_source = ScaleSource.USER_CONFIG

    def with_user_scale(self, value: float) -> "CalibrationInfo":
        updated = replace(self, spatial_scale_um_per_px=value, scale_source=ScaleSource.USER_CONFIG,
                          valid=True, calibration_id=None, calibration_time=None,
                          metrologically_calibrated=False)
        updated._unknown_fields = dict(self._unknown_fields)
        return updated

    def linear_um(self, pixels: float | None) -> float | None:
        nonnegative(pixels, "pixels")
        return None if pixels is None or not self.valid else pixels * self.spatial_scale_um_per_px

    def area_um2(self, pixels: float | None) -> float | None:
        nonnegative(pixels, "pixels")
        return None if pixels is None or not self.valid else pixels * self.spatial_scale_um_per_px ** 2
