import re
import unicodedata


def normalize_code(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip().upper()


def machine_requirement(value):
    raw = str(value or "").strip()
    text = normalize_code(raw)
    match = re.search(r"(\d+(?:\.\d+)?)\s*A", text)
    family = (
        "TWO_COLOR"
        if "双色" in text
        else "VERTICAL"
        if "立式" in text
        else "HORIZONTAL"
    )
    forbidden = []
    if "装不下" in text and "新" in text:
        codes = re.search(r"新([\d.、,，/]+)", text)
        if codes:
            forbidden = [f"新{n}" for n in re.findall(r"\d+", codes.group(1))]
    return {
        "raw": raw,
        "required_machine_a": float(match.group(1)) if match else None,
        "machine_family": family,
        "speed_class": "HIGH_SPEED"
        if re.search(r"(要排|必须|需).*高速", text)
        else None,
        "preferred_speed_class": "HIGH_SPEED" if "高速" in text else None,
        "required_capabilities": ["HEATING"] if "电热" in text else [],
        "forbidden_machine_codes": forbidden,
        "uncertain_qualifiers": ["双"] if re.search(r"A双$", text) else [],
    }


def state_from_text(value):
    text = str(value or "")
    if re.search(
        r"(不需要|无需|不用|无需再|不必)检修|检修(已)?完成|已修好|维修完成", text
    ):
        return "IDLE"
    if re.search(r"(正在|待|需)?检修|维修中|故障停机", text):
        return "MAINTENANCE"
    return "IDLE"


def dispatch_from_text(value):
    text = str(value or "")
    if re.search(r"已恢复|解除暂停|修模完成|修好", text):
        return "READY"
    if "待通知" in text:
        return "WAIT_NOTICE"
    if "暂停" in text:
        return "PAUSED"
    if "修模" in text:
        return "MOLD_REPAIR"
    if "待料" in text:
        return "WAIT_MATERIAL"
    return "READY"


def machine_capabilities(specification, type_raw="", note="", manipulator=""):
    text = normalize_code(f"{specification} {type_raw} {note} {manipulator}")
    req = machine_requirement(text)
    ton = re.search(r"(\d+(?:\.\d+)?)\s*T", text)
    forbidden = re.findall(r"(?:不可|不能|禁止)啤\s*([A-Z]+)", text)
    only = re.search(r"只可以啤\s*([A-Z]+)(?:\s+([A-Z0-9-]+))?", text)
    return {
        "machine_a": req["required_machine_a"],
        "clamp_ton": float(ton.group(1)) if ton else None,
        "machine_family": req["machine_family"],
        "speed_class": "HIGH_SPEED"
        if "高速" in text
        else "ELECTRIC"
        if "全电" in text
        else "NORMAL",
        "manipulator": manipulator,
        "capabilities": {
            "CORE_PULL": not bool(re.search(r"抽芯(不行|抽不了|不可)", text)),
            "HEATING": "电热" in text,
        },
        "restrictions": {
            "forbidden_resins": forbidden,
            "only_resin": only.group(1) if only else None,
            "only_grade": only.group(2) if only else None,
            "transparent_only": "只可以啤透明" in text,
        },
        "operating_status": state_from_text(note),
        "notes": note,
        "warnings": [s for s in ["机器不稳定", "ABS不好啤"] if s in text],
    }
