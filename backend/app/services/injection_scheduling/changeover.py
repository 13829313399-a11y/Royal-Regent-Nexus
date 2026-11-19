from decimal import Decimal as D

REFERENCE = {
    5: ("43.20", "24.48"),
    7: ("50.40", "24.48"),
    12: ("64.80", "36"),
    14: ("86.40", "36"),
    18: ("86.40", "36"),
    24: ("100.80", "48.24"),
    32: ("122.40", "48.24"),
    60: ("144", "60.48"),
    80: ("194.40", "72"),
    104: ("237.60", "72"),
    120: ("288", "78.48"),
}


def transition(previous, target, settings):
    a = target.get("required_machine_a")
    refs = settings.get("changeover_reference", REFERENCE)
    buckets = sorted(float(k) for k in refs)
    bucket = next((k for k in buckets if a is not None and k >= float(a)), buckets[-1])
    ref = next(value for key, value in refs.items() if float(key) == bucket)
    mold_minutes, color_minutes = (D(str(x)) for x in ref)
    same_asset = previous is not None and previous.get("mold_asset_id") == target.get(
        "mold_asset_id"
    )
    same_output = previous is not None and previous.get(
        "output_configuration"
    ) == target.get("output_configuration")
    same_color = previous is not None and (
        previous.get("colorant_code"),
        previous.get("color_name"),
    ) == (target.get("colorant_code"), target.get("color_name"))
    same_material = previous is not None and tuple(
        previous.get(k) for k in ("resin", "material_grade", "material_raw")
    ) == tuple(target.get(k) for k in ("resin", "material_grade", "material_raw"))
    mold = D(0) if same_asset and same_output else mold_minutes
    clean = D(0) if same_color and same_material else color_minutes
    if not same_material:
        clean = max(clean, D(str(settings.get("material_change_minutes", 60))))
    matrix_key = f"{(previous or {}).get('material_raw', '')}|{(previous or {}).get('colorant_code', '')}>{target.get('material_raw', '')}|{target.get('colorant_code', '')}"
    if matrix_key in settings.get("cleaning_matrix", {}):
        clean = D(str(settings["cleaning_matrix"][matrix_key]))
    return {
        "mold_change_minutes": mold,
        "color_change_minutes": clean,
        "changeover_minutes": mold + clean,
        "is_time_estimated": previous is None or a not in buckets or not same_material,
        "reference_bucket": bucket,
        "outside_reference": a is not None and float(a) > buckets[-1],
    }
