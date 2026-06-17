from __future__ import annotations

from enum import Enum


class FeatureCode(str, Enum):
    FLIGHT_CONTROL = "FLIGHT_CONTROL"
    VISION_ANALYSIS_RESULT = "VISION_ANALYSIS_RESULT"
    DATA_ANNOTATION = "DATA_ANNOTATION"
    DATASET_EXPORT = "DATASET_EXPORT"
    MODEL_TRAINING = "MODEL_TRAINING"
    MODEL_RELEASE = "MODEL_RELEASE"
    CROSS_TENANT_STATS = "CROSS_TENANT_STATS"
    PLATFORM_OPS = "PLATFORM_OPS"


ALL_FEATURES = set(FeatureCode)

CUSTOMER_DEFAULT_FEATURES = {
    FeatureCode.FLIGHT_CONTROL,
    FeatureCode.VISION_ANALYSIS_RESULT,
    FeatureCode.DATA_ANNOTATION,
}

ERROR_CODES = {
    "AUTH_401",
    "PERM_403",
    "TENANT_403",
    "TENANT_404",
    "FEATURE_403",
    "DATA_GRANT_412",
    "IDEMP_409",
    "STATE_409",
    "MISSION_422",
    "DJI_502",
    "GIS_422",
    "MEDIA_415",
    "MEDIA_499",
    "INFER_504",
    "MODEL_412",
    "RUNTIME_428",
}

MISSION_STATUSES = [
    "DRAFT",
    "PENDING_APPROVAL",
    "APPROVED",
    "DISPATCHING",
    "DISPATCHED",
    "EXECUTING",
    "PAUSED",
    "RETURNING",
    "LOST_LINK",
    "COMPLETED",
    "ABORTED",
    "MEDIA_SYNCING",
    "PARTIAL_MEDIA_READY",
    "MEDIA_READY",
    "ANALYSIS_READY",
    "CANCELLED",
    "REJECTED",
    "EXPIRED",
    "DISPATCH_FAILED",
    "SYNC_FAILED",
    "ARCHIVED",
]

PHASE_ONE_ALGORITHMS = [
    {
        "code": "traffic_congestion",
        "name": "交通拥堵",
        "target": {"recall": 0.85, "precision": 0.75},
        "default_threshold": 0.80,
    },
    {
        "code": "pedestrian_intrusion",
        "name": "行人闯入",
        "target": {"map50": 0.80, "recall": 0.85},
        "default_threshold": 0.80,
    },
    {
        "code": "two_wheeler_intrusion",
        "name": "两轮车闯入",
        "target": {"map50": 0.80, "recall": 0.85},
        "default_threshold": 0.78,
    },
    {
        "code": "road_obstacle",
        "name": "路面障碍物",
        "target": {"map50": 0.80, "recall": 0.85},
        "default_threshold": 0.75,
    },
    {
        "code": "road_construction",
        "name": "道路施工",
        "target": {"map50": 0.80, "recall": 0.85},
        "default_threshold": 0.75,
    },
    {
        "code": "road_crack",
        "name": "路面裂缝",
        "target": {"map50": 0.75, "recall": 0.80},
        "default_threshold": 0.70,
    },
    {
        "code": "road_pothole",
        "name": "路面坑槽",
        "target": {"map50": 0.75, "recall": 0.80},
        "default_threshold": 0.72,
    },
    {
        "code": "road_water",
        "name": "路面积水",
        "target": {"map50": 0.75, "recall": 0.80},
        "default_threshold": 0.72,
    },
    {
        "code": "marking_blur",
        "name": "路面标线模糊",
        "target": {"map50": 0.75, "recall": 0.80},
        "default_threshold": 0.70,
    },
    {
        "code": "helmet_missing",
        "name": "施工人员未戴安全帽",
        "target": {"map50": 0.85, "recall": 0.88},
        "default_threshold": 0.82,
    },
    {
        "code": "vest_missing",
        "name": "施工人员未穿反光衣",
        "target": {"map50": 0.85, "recall": 0.88},
        "default_threshold": 0.82,
    },
    {
        "code": "guardrail_damage",
        "name": "护栏钢结构破损",
        "target": {"map50": 0.72, "recall": 0.78},
        "default_threshold": 0.70,
    },
    {
        "code": "barrier_damage",
        "name": "隔离栏破损",
        "target": {"map50": 0.72, "recall": 0.78},
        "default_threshold": 0.70,
    },
    {
        "code": "bridge_under_space_stacking",
        "name": "桥下空间堆积物",
        "target": {"map50": 0.72, "recall": 0.78},
        "default_threshold": 0.72,
    },
]

