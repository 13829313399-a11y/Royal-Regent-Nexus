from copy import deepcopy

from .changeover import REFERENCE

DEFAULTS = {
    "business_timezone": "Asia/Shanghai",
    "target_basis_hours": 24,
    "downstream_lead_days": 3,
    "allowance_rate": 0.01,
    "material_change_minutes": 60,
    "day_start": "08:00",
    "night_start": "20:00",
    "working_days": list(range(7)),
    "daily_breaks": [],
    "setup_interruptible": False,
    "allowed_upsize": {
        "4": [5, 7],
        "5": [5, 7],
        "7": [7, 10, 12],
        "10": [10, 12, 14],
        "12": [12, 14, 18],
        "14": [14, 18, 24],
        "18": [18, 24],
        "24": [24, 32, 35],
        "32": [32, 35, 40, 50],
        "35": [35, 40, 50],
        "40": [40, 50, 60],
        "50": [50, 60, 80],
        "60": [60, 80],
        "80": [80, 100, 104],
        "100": [100, 104, 120],
        "104": [104, 120],
        "120": [120],
    },
    "changeover_reference": {str(k): list(v) for k, v in REFERENCE.items()},
    "cleaning_matrix": {},
    "color_ranks": {"透明": 0, "白色": 1, "浅色": 2, "中色": 3, "深色": 4, "黑色": 5},
    "defaults_note": "班制与允许上放为可编辑建议；24小时目标、3天准备期、1%材料系数与转换参考来自原表。",
}


def factory_defaults():
    return deepcopy(DEFAULTS)
