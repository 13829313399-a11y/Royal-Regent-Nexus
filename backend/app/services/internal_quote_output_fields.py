"""Explicit, revision-bound editable source fields for the output table."""
import json


def row_key(section, path):
    return section + ":" + "/".join(map(str, path))


class SourceLabel(str):
    def __new__(cls, text, section, path):
        obj = super().__new__(cls, text)
        obj.source_key = row_key(section, path)
        return obj


def bind_source_label(sheet, cell, value):
    if isinstance(value, SourceLabel):
        if not hasattr(sheet, "_quote_bindings"):
            sheet._quote_bindings = {}
        sheet._quote_bindings[cell.coordinate] = {"group": value.source_key, "kind": "name"}
        sheet._quote_bindings[sheet.cell(cell.row, cell.column + 1).coordinate] = {"group": value.source_key, "kind": "price"}


OPERATIONS = {"clamp": "夹模", "pad_print": "移印", "uv": "UV", "spray": "散枪", "edge": "边模", "paint": "油色", "dip": "浸油", "wipe": "抹油", "pp_water": "擦 PP 水"}


def source_groups(sections, region_code=""):
    """No client-supplied paths: only these business inputs can be patched."""
    groups = []
    for section in sections:
        if not section.is_required:
            continue
        code = section.department
        payload = json.loads(section.payload_json or "{}")

        def add(row, path, price_keys=(), category="", extra_prices=()):
            if not isinstance(row, dict):
                return
            name_keys = ("name", "item") if code == "hair" else ("item", "name", "doll_name", "chinese_name")
            name_key = next((key for key in name_keys if key in row), None)
            group = {"id": row_key(code, path), "section": code, "section_name": section.department_name,
                     "label": str(row.get(name_key, "") or category or section.department_name),
                     "category": category, "fields": []}

            def field(key_path, value, label, kind, currency="", nullable=False):
                group["fields"].append({"id": row_key(code, path + key_path), "path": path + key_path,
                                        "label": label, "kind": kind, "currency": currency, "value": value, "nullable": nullable})
            if name_key:
                field([name_key], row[name_key], "名称", "name")
            for key in price_keys:
                field([key], row.get(key), "模具报价" if key == "cost_rmb" else "原始单价", "price", "RMB" if key.endswith("rmb") else "HKD")
            for key_path, label, nullable in extra_prices:
                parent = row
                for key in key_path[:-1]:
                    parent = parent.get(key, {})
                field(key_path, parent.get(key_path[-1]), label, "price", "HKD", nullable)
            if group["fields"]:
                groups.append(group)

        def currency_price(row, force_rmb=False):
            if force_rmb or row.get("unit_price_source_currency") == "RMB":
                return "unit_price_rmb"
            if row.get("unit_price_source_currency") == "HKD":
                return "unit_price_hkd"
            return "unit_price_rmb" if row.get("unit_price_rmb") not in (None, "") else "unit_price_hkd"

        def rows(key, data=payload, prefix=()):
            return [(row, [*prefix, key, index]) for index, row in enumerate(data.get(key, []) or []) if isinstance(row, dict)]

        if code == "engineering":
            for row, path in rows("materials"):
                add(row, path, [currency_price(row, row.get("category") == "hardware")], row.get("auxiliary_category") or row.get("category", "物料"))
            for row, path in rows("molds"):
                add(row, path, ["cost_rmb"], "模具")
                for part, part_path in rows("parts", row, path):
                    add(part, part_path, category="模具零件")
        elif code == "sales":
            for row, path in rows("packaging_materials"):
                add(row, path, [currency_price(row)], row.get("category", "包装"))
            for row, path in rows("customer_supplied_materials"):
                add(row, path, ["unit_price_hkd"], "客供物料")
            for row, path in rows("cartons"):
                add(row, path, category="纸箱")
            if region_code == "indonesia":
                add(payload, [], category="印尼运费", extra_prices=[(["indonesia_freight_hkd"], "印尼运费", False)])
        elif code == "electronic":
            def electronic(data, prefix):
                key = "quick_quotes" if data.get("quote_mode") == "quick" else "components"
                def walk(items):
                    for row, path in items:
                        # Electronic calculation prefers an existing RMB key,
                        # including a blank pending price; HKD is legacy input.
                        add(row, path, ["unit_price_rmb" if "unit_price_rmb" in row else "unit_price_hkd"], "电子")
                        if key == "components":
                            walk(rows("children", row, path))
                walk(rows(key, data, prefix))
            if "quote_groups" in payload:
                for group, path in rows("quote_groups"):
                    add(group, path, category="电子报价名称")
                    electronic(group, path)
            else:
                electronic(payload, [])
        elif code == "painting":
            if payload.get("quote_mode") == "quick":
                add(payload.get("quick_quote", {}), ["quick_quote"], category="喷油快捷报价",
                    extra_prices=[(["spray_labor_hkd"], "喷油人工", False), (["paint_hkd"], "油漆", False)])
            else:
                for row, path in rows("rows"):
                    prices = [(["operations", key, "unit_price_hkd"], OPERATIONS.get(key, key) + "单价", False)
                              for key, operation in row.get("operations", {}).items() if isinstance(operation, dict)]
                    if row.get("cost_allocation") in {"split", "direct"}:
                        prices += [(["paint_cost_hkd"], "油漆金额", True), (["labor_cost_hkd"], "人工金额", True)]
                    add(row, path, category="喷油", extra_prices=prices)
        elif code in {"slush", "hair"}:
            for row, path in rows("lines"):
                add(row, path, ["unit_price_hkd"], "搪胶" if code == "slush" else "车发")
        elif code == "sewing":
            if payload.get("quote_mode") == "quick":
                for row, path in rows("quick_quotes"):
                    add(row, path, ["unit_price_hkd"], "车缝")
            else:
                for group, path in rows("groups"):
                    add(group, path, category="车缝产品组")
                    for row, child in rows("materials", group, path):
                        add(row, child, ["unit_price_rmb"], "车缝物料")
        elif code == "assembly":
            for group, path in rows("groups"):
                add(group, path, category="装配产品组")
                for row, child in rows("processes", group, path):
                    add(row, child, category="装配工序")
        elif code == "molding":
            for row, path in rows("injection_lines"):
                # Linked names are owned by Engineering and would be overwritten
                # by its projection on save. Edit the Engineering source instead.
                if row.get("engineering_source_key") and row.get("engineering_sync_disabled") is not True:
                    continue
                add(row, path, category="注塑")
    return groups
