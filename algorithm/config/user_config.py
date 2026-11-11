"""用户可修改的工程参数。

本文件只放配置，不放具体算法流程。所有路径、RAW参数和Case00输出参数
集中在这里，便于复现实验并在每次运行时保存快照。
"""

from pathlib import Path


# 工程和数据路径：原始数据目录只读，结果写入本工程 outputs。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(r"D:\疵病检测\疵病实测数据\260624批次表观（5片）")
OUTPUT_ROOT = PROJECT_ROOT / "outputs"
LOG_ROOT = PROJECT_ROOT / "logs"

# 260624 RAW 解析参数：16 bit 容器、大端字序、有效数据为12 bit。
RAW_WIDTH = 11276
RAW_HEIGHT = 9200
RAW_DTYPE = "uint16"
RAW_ENDIAN = "big"
EFFECTIVE_BITS = 12

# 探测器像元尺寸；Case00只记录，后续几何定量阶段使用，单位为 μm/px。
PIXEL_SIZE_UM = 3.2

# 样品和帧组织：每片4帧；Case02代表图固定使用每片第1帧。
SAMPLE_IDS = [26, 27, 28, 29, 30]
FRAME_IDS = [1, 2, 3, 4]

# Case00 输出参数：预览只用于显示，不参与任何DN统计。
PREVIEW_MAX_SIZE = 2048
HISTOGRAM_BIN_COUNT = 1 << EFFECTIVE_BITS
PROFILE_PLOT_DPI = 120

# 后续阶段预留配置；Case03-A只执行阈值方法对照，不执行连通域和分类。
ROI_CONFIG = {"enabled": False, "x": None, "y": None, "width": None, "height": None}
BACKGROUND_CONFIG = {"methods": ["gaussian", "median", "morphology"], "kernel_sizes_px": [31, 61, 101]}
BLACKHAT_KERNEL_SIZES_PX = [3, 5, 9, 15, 31]
# Black-Hat统一使用椭圆结构元；kernel尺寸为像素，必须使用奇数。
BLACKHAT_KERNEL_SHAPE = "ellipse"
# 多尺度融合方式：取各尺度原始DN响应的逐像素最大值。
BLACKHAT_FUSION_METHOD = "max"
# Black-Hat显示图的百分位映射，仅影响PNG显示，不改变原始响应数值。
BLACKHAT_PREVIEW_PERCENTILE_LOW = 0.0
BLACKHAT_PREVIEW_PERCENTILE_HIGH = 99.9
# Top-N仅用于人工观察，不等于最终缺陷判定；单位分别为个、pixel、pixel。
BLACKHAT_TOP_PATCH_COUNT = 20
BLACKHAT_PATCH_SIZE_PX = 256
BLACKHAT_TOP_PATCH_MIN_DISTANCE_PX = 128
# Case02验证诊断参数：仅影响诊断图册和候选对照，不改变主流程默认行为。
CASE02_VALIDATION_CONTACT_SHEET_MAX_SIZE = 3000
CASE02_VALIDATION_TOPN_PER_SCALE = 10
CASE02_VALIDATION_MATCH_RADIUS_PX = 16
CASE02_VALIDATION_ATLAS_COLUMNS = 5
# Case03-A全图阈值分割与鲁棒阈值对照参数；不覆盖Case02参数。
CASE03A_INPUT_RUN = "outputs/case02/run_20260930_153727"
CASE03A_SAMPLE_IDS = [26, 27, 28, 29, 30]
CASE03A_FRAME_ID = 1
CASE03A_SCALES_PX = [3, 5, 9, 15, 31]
CASE03A_FIXED_THRESHOLDS_DN = [150, 200, 250, 300]
CASE03A_FIXED_PRIMARY_DN = 200
CASE03A_MAD_K_VALUES = [3, 5, 7]
CASE03A_MAD_PRIMARY_K = 5
CASE03A_MAD_FLOOR_DN = 120
CASE03A_GRID_SIZE_PX = 256
CASE03A_GRID_SAMPLE_STRIDE_PX = 4
CASE03A_PREVIEW_MAX_EDGE_PX = 2048
CASE03A_PATCH_SIZE_PX = 256
CASE03A_STRIPE_ROWS_PX = 256
# 这些坐标是历史高响应候选，不是人工真值；报告必须保留该语义。
CASE03A_DIAGNOSTIC_POINTS = [
    {"sample_id": 26, "frame_id": 1, "label": "historical_candidate_01", "x": 1666, "y": 668},
    {"sample_id": 26, "frame_id": 1, "label": "historical_candidate_02", "x": 8110, "y": 1403},
    {"sample_id": 26, "frame_id": 1, "label": "historical_candidate_03", "x": 9437, "y": 1075},
    {"sample_id": 30, "frame_id": 1, "label": "historical_candidate_01", "x": 4105, "y": 179},
    {"sample_id": 30, "frame_id": 1, "label": "historical_candidate_02", "x": 2333, "y": 1764},
]

# Case03-A-R1修订参数：仅写入outputs/case03a_revision新运行目录，不改变A0历史结果。
# A1为各尺度独立固定DN候选扫描；候选来自既有Case02的P99/P99.9量级和上下邻近级别，
# 不是已经确认的正式阈值，也不根据候选面积反向优化。
CASE03A_REVISION_FIXED_THRESHOLDS_BY_SCALE = {
    3: [120, 130, 140, 150, 160, 180, 200],
    5: [140, 150, 160, 170, 180, 200, 220],
    9: [160, 170, 180, 190, 200, 220, 240],
    15: [180, 190, 200, 210, 220, 240, 260],
    31: [200, 220, 230, 240, 250, 280, 300],
}
# 仅用于生成可复核的代表性A1密度图和无损掩膜，不代表最优值。
CASE03A_REVISION_A1_MASK_THRESHOLD_BY_SCALE = {3: 150, 5: 170, 9: 190, 15: 210, 31: 230}
# A2先在样品26的中心小区域做筛查，再用以下三组代表参数完成5样品对照。
CASE03A_REVISION_LOCAL_SCREEN_K = [3, 5, 7]
CASE03A_REVISION_LOCAL_SCREEN_FLOOR_DN = [120, 160, 200]
CASE03A_REVISION_LOCAL_SCREEN_MIN_EXCESS_DN = [0, 10, 20]
CASE03A_REVISION_LOCAL_REPRESENTATIVES = [
    {"name": "A2_k5_floor120_excess10", "k": 5, "floor_dn": 120, "min_excess_dn": 10},
    {"name": "A2_k5_floor160_excess10", "k": 5, "floor_dn": 160, "min_excess_dn": 10},
    {"name": "A2_k7_floor120_excess20", "k": 7, "floor_dn": 120, "min_excess_dn": 20},
]
CASE03A_REVISION_SCREEN_SAMPLE_ID = 26
CASE03A_REVISION_SCREEN_CROP_SIZE_PX = 2048
CASE03A_REVISION_DENSITY_MAX_EDGE_PX = 2048
CASE03A_REVISION_DIAGNOSTIC_WINDOW_SIZE_PX = 256
CASE03A_REVISION_REGION_FRACTIONS = {
    "upper15": (0.00, 0.15),
    "middle40": (0.30, 0.70),
    "lower15": (0.85, 1.00),
}

# Case03-B：仅读取既有Case02融合响应，提取全图候选连通域。
# 所有阈值都是候选生成参数，不等价于缺陷真值或最终判定阈值。
CASE03B_INPUT_RUN = "outputs/case02/run_20260930_153727"
CASE03B_SAMPLE_IDS = [26, 27, 28, 29, 30]
CASE03B_FRAME_ID = 1
CASE03B_SINGLE_THRESHOLDS_DN = [220, 230, 250]
CASE03B_HYSTERESIS_PAIRS_DN = [(150, 230), (170, 230)]
CASE03B_PRIMARY_HYSTERESIS_DN = (150, 230)
CASE03B_CONNECTIVITY = 8
CASE03B_LOCAL_COMPARISON_CONNECTIVITY = 4
CASE03B_COMPONENT_TILE_SHAPE = (512, 1024)
CASE03B_LOCAL_SYNTHETIC_SHAPES = [(64, 64), (256, 384), (1024, 1024)]
CASE03B_LOCAL_PATCH_SIZE_PX = 256
CASE03B_LOCAL_PATCH_HALF_SIZE_PX = 128
CASE03B_ATLAS_MAX_CANDIDATES = 100
CASE03B_PREVIEW_MAX_EDGE_PX = 2048
CASE03B_DIAGNOSTIC_POINTS = [
    {"sample_id": 26, "frame_id": 1, "label": "historical_candidate_01", "x": 1666, "y": 668},
    {"sample_id": 26, "frame_id": 1, "label": "historical_candidate_02", "x": 8110, "y": 1403},
    {"sample_id": 26, "frame_id": 1, "label": "historical_candidate_03", "x": 9437, "y": 1075},
    {"sample_id": 30, "frame_id": 1, "label": "historical_candidate_01", "x": 4105, "y": 179},
    {"sample_id": 30, "frame_id": 1, "label": "historical_candidate_02", "x": 2333, "y": 1764},
]
CASE03B_PATCH_TYPES = [
    "historical_candidate",
    "medium_response",
    "weak_response",
    "fine_line",
    "high_noise",
    "blackband_edge",
    "blackband_edge_256",
    "blackband_edge_512",
]

# Case03-C第一阶段：只关联样品26的既有S230/H170-230候选并生成描述性特征。
# 本阶段不修改Case03-B阈值、不使用局部MAD、不删除任何候选，也不把特征映射为真实性标签。
CASE03C_INPUT_RUN = "outputs/case03b/run_20261008_153500"
CASE03C_CASE02_INPUT_RUN = "outputs/case02/run_20260930_153727"
CASE03C_GALLERY_RUN = "outputs/case03b_gallery/run_20261008_sample26_review"
CASE03C_SAMPLE_ID = 26
CASE03C_FRAME_ID = 1
CASE03C_SINGLE_THRESHOLD_DN = 230
CASE03C_HYSTERESIS_LOW_DN = 170
CASE03C_HYSTERESIS_HIGH_DN = 230
CASE03C_CONNECTIVITY = 8
CASE03C_COMPONENT_TILE_SHAPE = (512, 1024)
CASE03C_RAW_REFERENCE_RADIUS_PX = 12
CASE03C_RAW_REFERENCE_MAX_PIXELS = 512
CASE03C_RAW_REFERENCE_MIN_PIXELS = 20
CASE03C_RAW_TRANSITION_MARGIN_PX = 64
CASE03C_RAW_TRANSITION_PERCENTILE = 99.5
CASE03C_RAW_PROFILE_ROW_CHUNK = 256
CASE03C_RAW_PROFILE_COLUMN_SAMPLE_ROWS = 512
CASE03C_MAX_MEMORY_MB = 4096
CASE03C_TARGET_REVIEW_PATCHES = 60
CASE03C_REVIEW_PATCH_SIZE_PX = 256
CASE03C_REVIEW_CONTACT_SHEET_ROWS = 5
CASE03C_REVIEW_CONTACT_SHEET_COLUMNS = 2
CASE03C_LOCAL_ROI_MAX_COUNT = 13
CASE03C_EXPECTED_S_COUNT = 91937
CASE03C_EXPECTED_S_AREA = 121467
CASE03C_EXPECTED_H_COUNT = 88043
CASE03C_EXPECTED_H_AREA = 311790
THRESHOLD_CONFIG = {"fixed": [5, 10, 20], "mad_k": [3, 4, 5, 6]}
MORPHOLOGY_CONFIG = {"opening_kernel_px": 3, "closing_kernel_px": 3, "min_area_px": 1}
REPEATABILITY_CONFIG = {"max_position_error_px": None, "delta_dn_tolerance": None}


def as_dict() -> dict:
    """返回可JSON序列化的完整配置快照。"""

    return {
        name: value
        for name, value in globals().items()
        if name.isupper() and not name.startswith("__")
    }

# Case03-B样品26人工复核图册：仅展示与数据导出，不改Case03-B检测结果。
# 坐标为原始RAW全分辨率x=列、y=行；来源仅为历史响应/结构候选，不代表真值。
CASE03B_GALLERY_SOURCE_RUN = "outputs/case03b/run_20261008_153500"
CASE03B_GALLERY_SAMPLE_ID = 26
CASE03B_GALLERY_FRAME_ID = 1
CASE03B_GALLERY_THRESHOLDS = {"single_high_dn": 230, "hysteresis_low_1_dn": 170, "hysteresis_low_2_dn": 150}
CASE03B_GALLERY_DEFAULT_PATCH_SIZE_PX = 256
CASE03B_GALLERY_ROIS = [
    {"label": "strong_candidate_01", "x": 1666, "y": 668, "size_px": 256, "category": "historical_high_response"},
    {"label": "strong_candidate_02", "x": 8110, "y": 1403, "size_px": 256, "category": "historical_high_response"},
    {"label": "three_spot_candidates", "x": 9437, "y": 1075, "size_px": 256, "category": "historical_high_response"},
    {"label": "three_spot_candidates_wide", "x": 9437, "y": 1075, "size_px": 512, "category": "historical_high_response"},
    {"label": "upper_short_line_like", "x": 3148, "y": 1125, "size_px": 256, "category": "visible_structure_unverified"},
    {"label": "lower_short_line_like", "x": 3057, "y": 8406, "size_px": 256, "category": "visible_structure_unverified"},
    {"label": "thin_vertical_candidate", "x": 8348, "y": 6317, "size_px": 256, "category": "elongated_component_not_truth"},
    {"label": "small_spot_candidate", "x": 2341, "y": 949, "size_px": 256, "category": "connected_component_not_truth"},
    {"label": "weak_structure_unverified", "x": 2895, "y": 2992, "size_px": 256, "category": "weak_structure_unverified"},
    {"label": "bright_background_upper", "x": 5638, "y": 690, "size_px": 256, "category": "background_reference_not_truth"},
    {"label": "bright_background_lower", "x": 5638, "y": 8510, "size_px": 256, "category": "background_reference_not_truth"},
    {"label": "blackband_transition", "x": 5638, "y": 128, "size_px": 256, "category": "edge_stress_test"},
    {"label": "middle_low_response", "x": 3459, "y": 3452, "size_px": 256, "category": "background_reference_not_truth"},
]

 
# Case03-D：仅在样品26已存在的88,043个H170/230候选上建立复核优先级。
# 本阶段评分严格不读取人工标签；人工标签仅在评分完成之后作探索性验证。
# 不丢弃候选，不把复核顺序解释为疵病真实性概率或检测召回率。
CASE03D_SOURCE_FEATURE_CSV = "outputs/case03c/run_20261008_174000/hysteresis_candidate_features.csv"
CASE03D_SOURCE_LABELS_VERIFIED_CSV = "outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v2/candidate_labels_verified.csv"
CASE03D_SOURCE_LABELS_PROVISIONAL_CSV = "outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v2/candidate_labels_sensitivity_plus_boxes_v2.csv"
CASE03D_SAMPLE_ID = 26
CASE03D_FRAME_ID = 1
CASE03D_AREA_RANK_WEIGHT = 0.5
CASE03D_PEAK_RANK_WEIGHT = 0.5
CASE03D_FIRST_TIER_FRACTION = 0.01
CASE03D_SECOND_TIER_CUMULATIVE_FRACTION = 0.10
CASE03D_REVIEW_BUDGETS = [100, 500, 1000, 5000]
CASE03D_PRIMARY_RANKING_METHOD = "equal_weight_area_peak_global_percentile"
CASE03D_ATLAS_PATCH_SIZE_PX = 192
CASE03D_ATLAS_CANDIDATES_PER_GROUP = 12
CASE03D_FULL_GALLERY_ENABLED = True
CASE03D_EXPECTED_H_COUNT = 88043
CASE03D_EXPECTED_H_TOTAL_PIXELS = 311790
CASE03D_REVIEW_031_046_056_STATUS = "non_target_for_case03d__not_candidate_negative_truth"

# Case03-D 微小候选独立审核队列：不改变主排序、不自动删除C组。
CASE03D_EXPECTED_ONE_PIXEL_H_COUNT = 35678
CASE03D_MICRO_AUDIT_TOP_N = 100
CASE03D_MICRO_AUDIT_ATLAS_COUNT = 12

 
# Case03-D-R2：面向自动判别的可解释规则首轮工程参数；仅样品26第1帧。
# 注意：这是未经过独立数据集验证的筛选规则，不可将输出解释为真实疵病概率。
CASE03D_AUTO_MIN_AREA_PX = 20
CASE03D_AUTO_MIN_PEAK_DN = 270
CASE03D_AUTO_MIN_RAW_DARK_DELTA_DN = 20.0
CASE03D_AUTO_MIN_BBOX_FILL = 0.23
CASE03D_AUTO_REVIEW_MIN_AREA_PX = 12
CASE03D_AUTO_REVIEW_MIN_PEAK_DN = 275
CASE03D_AUTO_REVIEW_TINY_HIGH_PEAK_DN = 275
CASE03D_AUTO_UNCERTAIN_FIRST_BATCH = 500
CASE03D_AUTO_EXPECTED_SOURCE_H_COUNT = 88043
CASE03D_AUTO_EXPECTED_SOURCE_H_PIXELS = 311790
CASE03D_AUTO_ROI_031_046_056 = "not_target_for_this_stage"

 
# Case03-E：用户已确认保留的10处RAW异常，局部边界精修方法对照。
# 注意：这些是工程先验固定参数，不能对同一10处人工手绘边界调参后声称独立准确率。
CASE03E_ROI_SIZE_PX = 256
CASE03E_METHODS = ["closing61", "closing101", "gaussian22"]
CASE03E_LEVELS = ["liberal", "conservative"]
CASE03E_MAX_AREA_FRACTION = 0.25
# 不填物面尺度与大小分级门限，待用户提供有效标定及分级标准。
CASE03E_OBJECT_PLANE_UM_PER_PIXEL = None
CASE03E_SIZE_GRADE_THRESHOLDS = None

 
# Case03-E2：多候选自动发现与双阈值互补融合的固定开发参数（2026-10-10）。
# 初版对照窗口固定256px、128px网格对齐；不是全图扫描。
# 调参必须生成新的run-id；旧结果和人工标签不得覆盖。
CASE03E2_WINDOW_SIZE_PX = 256
CASE03E2_GRID_STRIDE_PX = 128
CASE03E2_MIN_LOCAL_COMPONENT_AREA_PX = 5
CASE03E2_GAUSSIAN_MORPH_HIGH_FLOOR_DN = 65.0
CASE03E2_GAUSSIAN_MORPH_LOW_FLOOR_DN = 24.0
CASE03E2_GAUSSIAN_MORPH_HIGH_K_MAD = 4.0
CASE03E2_GAUSSIAN_MORPH_LOW_K_MAD = 1.8
CASE03E2_MAX_LOCAL_REGION_AREA_FRACTION = 0.10
CASE03E2_KEEP_H_REGION_MIN_AREA_PX = 3
CASE03E2_KEEP_H_REGION_STRONG_PEAK_DN = 280.0
CASE03E2_H_ONLY_PROVISIONAL_AREA_MIN_PX = 12
CASE03E2_H_ONLY_PROVISIONAL_PEAK_DN = 350.0
CASE03E2_GRADE_THRESHOLDS_OBJECT_PLANE_UM = None
CASE03E2_OBJECT_PLANE_UM_PER_PIXEL = None

 
# Case03-E2-H：仅H170/230产生初始候选，Gaussian/Closing只精修H候选。
# 不允许Gaussian/Closing独立产生新的噪声候选。历史融合v5保留可对照。
CASE03E2_HSEED_MAX_EXTENSION_RADIUS_PX = 12
CASE03E2_HSEED_MIN_H_PIXELS_FOR_REFINEMENT = 3
CASE03E2_HSEED_MAX_AREA_RATIO = 12.0
CASE03E2_HSEED_MAX_RAW_COMPONENT_FRACTION = 0.08

 
# Case03-E2-H3 有界精修：只针对已有H候选，不能生成独立新目标。
# 当Gaussian/Closing低阈值整体触边或桥接时，先在H 7px邻域
# 按局部H响应强度截取被支持的边缘像素，并标记“需复核”。
CASE03E2_HSEED_BOUNDED_FALLBACK_ENABLED = True
CASE03E2_HSEED_BOUNDED_RADIUS_PX = 7
CASE03E2_HSEED_BOUNDED_MAX_AREA_RATIO = 3.0


# Case03-F：小面积候选RAW局部对比试验（仅旁路建议，不删除源H）。
# 面积单位px²；相对对比度无量纲；Z为相对局部噪声显著性。
# 本方案只试验样品26既有9窗口；恢复只需忽略case03f目录。
CASE03F_SMALL_AREA_MAX_PX = 5
CASE03F_MIN_RELATIVE_CONTRAST = 0.08
CASE03F_MIN_SIGNIFICANCE_Z = 3.0
CASE03F_RING_OUTER_RADIUS_PX = 12
CASE03F_RING_INNER_GUARD_PX = 2
CASE03F_RING_MIN_COUNT = 20
CASE03F_SIGMA_FLOOR_DN = 3.0
# 保护与大H候选靠近的小分量，优先避免损伤十字划痕边缘。
CASE03F_PROTECT_LARGE_NEARBY_RADIUS_PX = 3
CASE03F_PROTECT_LARGE_AREA_PX = 30

# Case03-G：10样例局部RAW筛噪+历史Gaussian22/Closing61 H约束轮廓精修联合实验。
# 面积为原H连通域的px²，半径为像素；人工多边形仅用于后验评价/图册。
CASE03G_PROTECT_STRUCTURE_MIN_AREA_PX = 6
CASE03G_PROTECT_STRUCTURE_RADIUS_PX = 8
CASE03G_PROTECT_EXISTING_REFINEMENT = True


# Case03-H：扩展背景纹理筛选至6~30 px² + 双高斯差DoG暗核保护；仅旁路。
# 所有数值均为探索性阈值，未通过独立样本标定。
CASE03H_MEDIUM_MIN_AREA_PX = 6
CASE03H_MEDIUM_MAX_AREA_PX = 30
CASE03H_MIN_RELATIVE_CONTRAST = 0.06
CASE03H_MIN_SIGNIFICANCE_Z = 2.5
CASE03H_PROTECT_BLACKHAT_PEAK_DN = 320.0
CASE03H_PROTECT_DOG_MEDIAN_DN = 16.0
CASE03H_PROTECT_BIG_AREA_PX = 40
CASE03H_PROTECT_BIG_RADIUS_PX = 5
CASE03H_PROTECT_STROKE_MIN_LENGTH_PX = 12
CASE03H_PROTECT_STROKE_ASPECT = 3.5

# DoG局部相干暗核计算的两个高斯尺度，单位px，要求large>small>0。
CASE03H_DOG_SMALL_SIGMA_PX = 2.0
CASE03H_DOG_LARGE_SIGMA_PX = 8.0

# Case03-T: 26号第2帧固定/全图MAD/局部MAD双阈值对照试验。
# 选值不依赖26号第二帧人工标注；全部统计作用于12bit DN BlackHat融合响应。
# 不设置120DN等大幅固定阈值下限（防止“假自适应”）；以MAD噪声下限3DN防止塌陷。
CASE03T_GRID_SIZE_PX = 256
CASE03T_GRID_SAMPLE_STRIDE_PX = 4
CASE03T_GLOBAL_SAMPLE_STRIDE_PX = 16
CASE03T_BACKGROUND_TRIM_PERCENTILE = 98.0
CASE03T_LOW_K_MAD = 3.5
CASE03T_HIGH_K_MAD = 5.0
CASE03T_NOISE_FLOOR_DN = 3.0
CASE03T_LOW_FLOOR_DN = 20.0
CASE03T_HIGH_FLOOR_DN = 40.0
CASE03T_MIN_HYSTERESIS_GAP_DN = 15.0

# Case03-I：疑似疵病尺寸分级，仅用于工程可视化，单位是相机图像像素，
# NOT成品合格判定，不转换物面微米（须另行标定光学放大倍率）。
# 同时计算面积和最大Feret(像素中心)长度，两个规则取更高等级。
CASE03I_MEDIUM_AREA_MIN_PX2 = 40
CASE03I_LARGE_AREA_MIN_PX2 = 250
CASE03I_MEDIUM_LENGTH_MIN_PX = 15.0
CASE03I_LARGE_LENGTH_MIN_PX = 45.0
CASE03I_CONNECTIVITY = 8
CASE03I_MAX_COMPONENTS_PER_WINDOW = 3000

# Case03-J1：断裂划痕物理关联试验，纯编号和尺寸重算，不填充连接像素。
# 所有参数为工程启发式候选，不作为物理真值或正式尺寸验收。
CASE03J_MAX_LINK_GAP_PX = 18.0
CASE03J_MIN_CORE_AREA_PX = 80
CASE03J_MIN_PIECE_AREA_PX = 8
CASE03J_MIN_PIECE_LENGTH_PX = 5.0
CASE03J_STRONG_ASPECT_RATIO = 1.35
CASE03J_ANGLE_TOLERANCE_DEG = 38.0
CASE03J_MIN_BRIDGE_DOG_MEDIAN_DN = 16.0
CASE03J_MIN_BRIDGE_POSITIVE_FRACTION = 0.7
CASE03J_SHORT_CONNECTOR_GAP_PX = 4.0
CASE03J_MIN_PIECE_DOG_MEDIAN_DN = 12.0
CASE03J_MIN_CORE_LENGTH_PX = 15.0

# Case03-J2：在冻结Case03-I/J1结果上重建“一个连续显示轮廓”。
# 只改变衍生显示掩膜和对象映射；原RAW/H/筛噪/精修mask永久保留不变。
# 当地灰度支持充分且已有长划痕组指向断点时才补画暗线。
# 推断补线像素不参与原始疵病面积、Feret长度的实测统计。
CASE03J2_CONTEXT_MAX_GAP_PX = 18.0
CASE03J2_MAIN_STROKE_MIN_LENGTH_PX = 60.0
CASE03J2_MAIN_STROKE_MIN_ASPECT = 3.0
CASE03J2_PIECE_MIN_AREA_PX = 40
CASE03J2_PIECE_MIN_LENGTH_PX = 12.0
CASE03J2_MAX_PERPENDICULAR_OFFSET_PX = 20.0
CASE03J2_CONTEXT_ANGLE_TOLERANCE_DEG = 35.0
CASE03J2_BRIDGE_HALF_WIDTH_PX = 3
CASE03J2_BRIDGE_MIN_DOG_DN = 12.0
CASE03J2_MAX_CONTEXT_LINKS_PER_GROUP = 1
CASE03J2_AMBIGUOUS_GAP_MARGIN_PX = 2.0

# Case03-J4：先实现全幅覆盖、不跨tile合并；跨tile归并及正式全局对象编号留给Case03-J5。
# 外部使用256核心像素网格，内部按64px halo扩张作H/G/C/F/H与边缘上下文，
# 核心不可重叠、能精确覆盖全图，不假设物理疵病在tile边缘结束。
CASE03J4_CORE_SIZE_PX = 256
CASE03J4_HALO_PX = 64

# Two-level scheduling only: none of these change the frozen detection kernels.
TWO_LEVEL_ROI = {
    'review_margin_px': 12,
    'minimum_algorithm_halo_px': 93,
    'gaussian_support_sigmas': 4,
    'seeded_gaussian_sigma_px': 22.0,
    'residual_smoothing_sigma_px': 0.85,
    'median_radius_px': 1,
    'seeded_closing_kernel_px': 61,
    'K8D_raw_window_px': 128,
    'blackhat_extra_guard_px': 2,
    'blackhat_chunk_px': 512,
    'min_band_count': 1,
    'max_band_count': 16,
    'min_work_fraction': 0.001,
    'max_work_fraction': 0.90,
    'default_mode': 'roi-bh',
}

# Case03-J5：只读取完整Case03-J4输出，不重新提取候选；
# 直接8连通跨核心边界合并，断开缝隙采用方向和RAW DoG双重证据。
# 当一个局部对象面临多个距离相近的gap候选时，拒绝含糊关联。
CASE03J5_GAP_MAX_PX = 18.0
CASE03J5_MIN_LINE_LENGTH_PX = 12.0
CASE03J5_MIN_PIECE_AREA_PX = 5
CASE03J5_MIN_LINE_ASPECT = 1.5
CASE03J5_ANGLE_TOL_DEG = 30.0
CASE03J5_BRIDGE_DOG_MIN_DN = 16.0
CASE03J5_BRIDGE_POSITIVE_FRACTION = 0.70
CASE03J5_AMBIGUITY_GAP_PX = 2.0
UNIFIED_FINAL = {
    "min_j5_scratch_length_px": 10.0,
    "min_b_source_area_px2": 40,
    "max_raw_growth_ratio": 8.0,
    "recovery_seed_distance_px": 40,
    "recovery_background_inner_px": 44,
    "recovery_background_outer_px": 68,
    "recovery_sigma_multiplier": 3.0,
    "recovery_min_sigma_dn": 3.0,
    "recovery_peak_fraction": 0.15,
    "recovery_line_background_sigma_px": 16.0,
    "recovery_min_seed_coverage": 0.90,
    "recovery_max_area_px2": 10000,
    "recovery_max_short_axis_px": 48,
    "recovery_max_roi_px": 512,
    "recovery_max_pair_bbox_gap_px": 36,
    "display_box_scale": 1.5,
    "display_stride": 4,
    "display_font_px": 18,
}
