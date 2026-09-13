"""Independent electronic quotations; legacy single quotations remain valid."""
from copy import deepcopy


def electronic_quote_groups(payload: dict) -> list[dict]:
    if "quote_groups" not in payload:
        return [{**payload, "id": "legacy", "name": "电子报价1"}]
    groups = payload["quote_groups"]
    if not isinstance(groups, list) or len(groups) > 20:
        raise ValueError("电子报价必须为列表，最多20份")
    seen = set()
    for group in groups:
        if not isinstance(group, dict) or "quote_groups" in group:
            raise ValueError("电子报价结构无效")
        group_id = group.get("id")
        name = group.get("name")
        if not isinstance(group_id, str) or not group_id.strip() or len(group_id) > 80 or group_id in seen or group_id == "new":
            raise ValueError("电子报价编号无效或重复")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError("请填写每份电子报价的名称（最多200字）")
        seen.add(group_id)
    return groups


def electronic_has_content(payload: dict) -> bool:
    if payload.get("components") or payload.get("quick_quotes"):
        return True
    return any(payload.get(stem + suffix) not in (None, "", 0, "0", "0.0000")
               for stem in ("bonding", "smt", "labor", "testing", "packaging", "tax_credit_difference")
               for suffix in ("_rmb", "_hkd"))


def electronic_detail_payload(payload: dict) -> dict:
    """Read-only projection for consumers of raw parts (never for calculating totals)."""
    if "quote_groups" not in payload:
        return payload
    components = []
    for group in electronic_quote_groups(payload):
        quick = group.get("quote_mode") == "quick"
        for source in group.get("quick_quotes" if quick else "components", []):
            row = deepcopy(source)
            if quick:
                row.update(quantity=1, children=[])
            row["electronic_quote_id"] = group["id"]
            row["electronic_quote_name"] = group["name"]
            components.append(row)
    return {"quote_mode": "detail", "components": components}
