"""Case02 Black-Hat基础性质测试。"""

import cv2
import numpy as np

from src.detection.blackhat import black_hat_uint16, create_structuring_element
from src.detection.multiscale import fuse_max_responses


def test_dark_point_has_positive_response() -> None:
    image = np.full((96, 96), 1000, dtype=np.uint16)
    cv2.circle(image, (48, 48), 3, 500, thickness=-1)
    response = black_hat_uint16(image, 9, "ellipse")
    assert int(response[48, 48]) >= 400
    assert response.dtype == np.uint16


def test_dark_line_has_positive_response() -> None:
    image = np.full((96, 96), 1000, dtype=np.uint16)
    cv2.line(image, (15, 48), (80, 48), 500, thickness=2)
    response = black_hat_uint16(image, 9, "ellipse")
    assert int(response[48, 48]) >= 400


def test_constant_image_is_zero() -> None:
    image = np.full((64, 64), 1234, dtype=np.uint16)
    response = black_hat_uint16(image, 5, "ellipse")
    assert np.array_equal(response, np.zeros_like(image))


def test_uint16_and_kernel_validation() -> None:
    image = np.full((32, 32), 4095, dtype=np.uint16)
    response = black_hat_uint16(image, 3, "ellipse")
    assert response.dtype == np.uint16
    assert int(response.min()) >= 0
    assert int(response.max()) <= 65535
    try:
        create_structuring_element(4, "ellipse")
    except ValueError:
        pass
    else:
        raise AssertionError("偶数结构元尺寸应被拒绝")


def test_max_fusion_records_winning_scale() -> None:
    first = np.zeros((4, 4), dtype=np.uint16)
    second = np.zeros((4, 4), dtype=np.uint16)
    first[1, 1] = 10
    second[1, 1] = 20
    fused, winning = fuse_max_responses([(3, first), (5, second)], first.shape)
    assert int(fused[1, 1]) == 20
    assert int(winning[1, 1]) == 2
