"""Warehouse-shaped historical demand. Parsing never posts goods or learns master data."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, ROUND_CEILING
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.carton_procurement import CartonOrderLineCreate
from app.schemas.carton_weights import CartonPackingWeights
from app.services.carton_procurement_imports import _cell, _date_text, _header_key, _header_mapping, _number, _text


WEIGHT_ALIASES = {
    "net_weight_kg": {"每箱净重kg", "每箱净重kg选填", "每箱净重", "净重kg", "净重", "netweightkg"},
    "gross_weight_kg": {"每箱毛重kg", "每箱毛重kg选填", "每箱毛重", "毛重kg", "毛重", "grossweightkg"},
}

ALIASES = {
    "customer_po": {"客户po", "客户po选填", "客户采购单号", "客户订单号", "customerpo"},
    "order_no": {"历史订单号", "历史订单号选填", "历史订单编号", "原订单号"},
    "customer_name": {"客户名称", "客户", "公司", "客名"},
    "contract_no": {"合同号", "合同编号"}, "item_no": {"货号", "产品编号", "客货号"},
    "product_name": {"产品名称", "品名"},
    "product_order_quantity": {"产品订单数量", "产品数量", "订单数量"},
    "order_date": {"下单日期", "落单日期", "订单日期"},
    "due_date": {"计划交期", "交货日期", "交期"},
    "customer_due_date": {"客户交期", "客户要求交期"},
    "note": {"备注", "订单备注", "合同备注"},
    "packing": {"装箱数", "内外装箱数"},
    "paper_quality": {"纸质", "材质"}, "specification": {"规格", "尺寸"},
    "dimension_unit": {"规格单位", "尺寸单位"},
    "unit": {"纸品单位", "单位"}, "unit_price": {"单价"}, "currency": {"币种"},
    "other_type": {"其他纸品类型", "卡类类型"}, "other_quantity": {"其他纸品需求数量", "卡类需求数量"},
    "card_quantity": {"卡纸需求数量", "卡纸数量", "卡数量", "卡类", "卡"},
    "legacy_type": {"纸品类型", "纸箱类型", "packagingtype"},
    "legacy_usage": {"每箱个数", "单件用量", "用量", "usagequantity", "unitspercarton"},
}
for prefix, label in (("inner", "内箱"), ("outer", "外箱"), ("card", "卡纸"), ("other", "其他纸品")):
    ALIASES.setdefault(f"{prefix}_quantity", {f"{label}需求数量", f"{label}数量"})
    for field, suffixes in {
        "paper_quality": {"纸质", "材质"}, "specification": {"规格", "尺寸"},
        "dimension_unit": {"规格单位", "尺寸单位"}, "unit": {"纸品单位", "单位"},
        "usage_quantity": {"每箱个数", "装箱数"}, "unit_price": {"单价"},
        "net_weight_kg": {"每箱净重kg", "每箱净重", "净重kg", "净重"},
        "gross_weight_kg": {"每箱毛重kg", "每箱毛重", "毛重kg", "毛重"},
    }.items():
        ALIASES[f"{prefix}_{field}"] = {label + suffix for suffix in suffixes}
ALIASES["outer_quantity"].add("做箱数量")
# The main sheet's one unqualified pair always describes the packed outer carton.
for field, aliases in WEIGHT_ALIASES.items():
    ALIASES[f"outer_{field}"].update(aliases)
EXTRA_ALIASES = {
    **WEIGHT_ALIASES,
    "customer_po": {"客户po", "客户po选填", "客户采购单号", "客户订单号", "customerpo"},
    "order_no": ALIASES["order_no"], "packaging_type": {"纸品类型"},
    "required_quantity": {"纸品需求数量", "需求数量"},
    **{field: ALIASES[field] for field in ("paper_quality", "specification", "dimension_unit", "unit", "unit_price", "currency")},
    "usage_quantity": {"每箱个数"}, "note": {"明细备注", "备注"},
}


def fail(source: str, message: str):
    raise HTTPException(422, detail=f"{source}：{message}")


def number(value: Any, source: str, label: str, *, positive=False) -> Decimal | None:
    if not _text(value):
        return None
    result = _number(value)
    if result is None or not result.is_finite() or result < 0 or (positive and result == 0):
        fail(source, f"{label}必须为{'大于零' if positive else '非负'}数字")
    return result


def check_weight_headers(headers, aliases, source):
    for field, names in aliases.items():
        if field.endswith("_weight_kg"):
            keys = {_header_key(name) for name in names}
            if sum(_header_key(value) in keys for value in headers) > 1:
                fail(source, "同一纸品的净重或毛重出现多列，请各保留一列，避免漏读重量")


def parse_weights(row, mapping, source, *, prefix=""):
    values = {field: number(_cell(row, mapping, prefix + field), source, label)
              for field, label in (("net_weight_kg", "每箱净重（kg）"), ("gross_weight_kg", "每箱毛重（kg）"))}
    try:
        return CartonPackingWeights(**values).model_dump()
    except ValidationError as exc:
        fail(source, "每箱重量不合法：" + "; ".join(error["msg"] for error in exc.errors()[:3]))


def date_value(value: Any, datemode: int, source: str, label: str, required=False) -> str | None:
    if not _text(value) and not required:
        return None
    try:
        result = _date_text(value, datemode)
    except (ValueError, OverflowError):
        result = ""
    if not result:
        fail(source, f"{label}必须是带四位年份的完整日期，例如 2026-09-02")
    return result


def make_line(values: dict, source: str) -> CartonOrderLineCreate:
    try:
        return CartonOrderLineCreate(**values)
    except ValidationError as exc:
        fail(source, "纸品字段不合法：" + "; ".join(f"{'.'.join(map(str,e['loc']))}: {e['msg']}" for e in exc.errors()[:5]))


def parse_wide(worksheets) -> tuple[list[dict], list[str]] | None:
    """Return None for legacy vertical files; supplemental sheets bind explicit IDs only."""
    parsed, warnings, extras = [], [], []
    found = False
    seen_rows: dict[tuple, str] = {}
    unnamed_identities: set[tuple] = set()
    main_by_number: dict[str, dict] = {}
    legacy_sheets=[]
    for sheet, rows, datemode in worksheets:
        if sheet.strip() in {"填写示例", "字段说明"}:
            continue
        if sheet.strip() == "附加纸品明细":
            extras.append((sheet, rows, datemode))
            continue
        header = _header_mapping(rows, ALIASES)
        if not header:
            continue
        index, mapping = header
        if not {"customer_name", "contract_no", "item_no", "order_date"}.issubset(mapping):
            continue
        if not {"inner_quantity", "outer_quantity", "card_quantity", "other_quantity", "packing"}.intersection(mapping):
            if {"legacy_type","legacy_usage"}.issubset(mapping):
                legacy_sheets.append(sheet)
            continue
        card_headers = {_header_key(alias) for alias in ALIASES["card_quantity"]}
        if sum(_header_key(value) in card_headers for value in rows[index]) > 1:
            fail(f"“{sheet}”表头", "卡纸数量出现多列，请保留一列总需求；不同卡类或多规格请用附加纸品明细")
        found = True
        check_weight_headers(rows[index], ALIASES, f"“{sheet}”表头")
        for rownum, row in enumerate(rows[index + 1:], index + 2):
            if not any(_text(_cell(row, mapping, key)) for key in ALIASES):
                continue
            source = f"“{sheet}”第 {rownum} 行"
            fingerprint = tuple((key, _text(_cell(row, mapping, key))) for key in sorted(mapping))
            if fingerprint in seen_rows:
                fail(source, f"与{seen_rows[fingerprint]}完全重复，请删除重复行；不能重复累计需求")
            seen_rows[fingerprint] = source
            head = {key: _text(_cell(row, mapping, key)) for key in ("order_no", "customer_name", "contract_no", "item_no", "customer_po", "product_name", "note")}
            for key, label in (("customer_name", "客户名称"), ("contract_no", "合同号"), ("item_no", "货号")):
                if not head[key]:
                    fail(source, f"{label}不能为空")
            if len(head["order_no"]) > 64:
                fail(source, "历史订单号不能超过64个字符")
            head.update(source=source, quantity_basis="EXPLICIT", row_warnings=[])
            identity=tuple(head[key].strip().casefold() for key in ("customer_name","contract_no","item_no","customer_po"))
            if not head["order_no"]:
                if identity in unnamed_identities:
                    fail(source,"同客户、合同、货号及客户 PO 出现多行主信息，请先核实重复；不同批次须填写不同历史订单号")
                unnamed_identities.add(identity)
            head["product_order_quantity"] = number(_cell(row,mapping,"product_order_quantity"), source, "产品订单数量", positive=True)
            head["order_date"] = date_value(_cell(row,mapping,"order_date"),datemode,source,"下单日期",True)
            head["due_date"] = date_value(_cell(row,mapping,"due_date"),datemode,source,"计划交期",True)
            head["customer_due_date"] = date_value(_cell(row,mapping,"customer_due_date"),datemode,source,"客户交期")
            if head["due_date"] < head["order_date"]:
                fail(source, "计划交期不能早于下单日期")
            if head["customer_due_date"] and head["customer_due_date"] < head["order_date"]:
                fail(source, "客户交期不能早于下单日期")
            packing = _text(_cell(row,mapping,"packing"))
            pair = {}
            if packing:
                parts = packing.split("/")
                if len(parts) != 2:
                    fail(source,"装箱数应为内箱/外箱，例如0/12")
                pair = {key:number(value,source,"装箱数") for key,value in zip(("inner","outer"),parts)}
                if any(value is None for value in pair.values()):
                    fail(source,"装箱数两边都需要数字，例如0/12")
            definitions = []
            weights = {}
            for prefix, label in (("inner","内箱"),("outer","外箱"),("card","卡纸"),("other",_text(_cell(row,mapping,"other_type")))):
                weights[prefix] = parse_weights(row, mapping, source, prefix=f"{prefix}_")
                quantity = number(_cell(row,mapping,f"{prefix}_quantity"),source,f"{label or '其他纸品'}需求数量")
                usage = number(_cell(row,mapping,f"{prefix}_usage_quantity"),source,f"{label or '其他纸品'}每箱个数")
                if prefix in pair:
                    if usage is not None and usage != pair[prefix]:
                        fail(source,f"{label}每箱个数与装箱数{packing}不一致")
                    usage = pair[prefix]
                if quantity == 0:
                    if any(value is not None for value in weights[prefix].values()):
                        fail(source, f"已填写{label or '其他纸品'}每箱重量，但对应纸品需求数量为0，请核对")
                    continue
                if quantity is None and usage and head["product_order_quantity"]:
                    quantity = (head["product_order_quantity"] / usage).to_integral_value(rounding=ROUND_CEILING)
                    head["row_warnings"].append(f"{label}需求数量由产品数量÷每箱个数向上取整计算为{quantity}")
                if quantity is None:
                    if any(value is not None for value in weights[prefix].values()):
                        fail(source, f"已填写{label or '其他纸品'}每箱重量，但没有对应纸品需求数量，请核对")
                    continue
                if not label:
                    fail(source,"其他纸品必须填写具体纸品类型")
                if usage == 0:
                    fail(source,f"{label}需求大于0但装箱数为0，请核实")
                if usage and head["product_order_quantity"]:
                    calculated = (head["product_order_quantity"] / usage).to_integral_value(rounding=ROUND_CEILING)
                    if quantity != calculated:
                        head["row_warnings"].append(f"{label}明确需求{quantity}与装箱换算{calculated}不一致，保留明确需求，请核实备用箱或补单")
                definitions.append((prefix,label,quantity,usage))
            # Generic quality/specification are safe only for exactly one paper demand.
            if len(definitions) > 1 and any(_text(_cell(row,mapping,key)) for key in ("paper_quality","specification","unit_price")):
                fail(source,"同时有多种纸品时，纸质、规格和单价必须按内箱/外箱/卡纸分别填写，不能共用一组")
            own_rows = []
            for prefix,label,quantity,usage in definitions:
                def value(field):
                    explicit = _cell(row,mapping,f"{prefix}_{field}")
                    return explicit if _text(explicit) else (_cell(row,mapping,field) if len(definitions)==1 else None)
                values = {key:_text(value(key)) for key in ("paper_quality","specification","dimension_unit")}
                default_unit = "张" if prefix == "card" else "个"
                values.update(packaging_type=label,required_quantity=quantity,usage_quantity=usage,
                    **weights[prefix],
                    unit=_text(value("unit")) or default_unit,unit_price=number(value("unit_price"),source,"单价") or Decimal(0),
                    currency=(_text(_cell(row,mapping,"currency")) or "CNY").upper(),price_source="历史导入",note="")
                if not _text(value("unit")):
                    head["row_warnings"].append(f"{label}未填纸品单位，按“{default_unit}”计数，请在预览核对")
                if prefix == "card":
                    head["row_warnings"].append("卡数量按“卡纸”需求登记；不同卡类或多种规格请使用附加纸品明细分别填写")
                own_rows.append({**deepcopy(head),"line":make_line(values,source)})
            if head["order_no"]:
                key=head["order_no"].casefold()
                if key in main_by_number:
                    fail(source,"同一历史订单号只能有一行主信息；额外纸品请填附加纸品明细，不同批次使用不同历史订单号")
                main_by_number[key]=head
            elif not own_rows:
                fail(source,"至少填写一项大于0的纸品需求数量")
            parsed.extend(own_rows)
    if not found:
        return None
    if legacy_sheets:
        fail("历史订单导入",f"同一文件混合了新版横表和旧版纵表（{'、'.join(legacy_sheets)}），请拆成两个文件分别预览导入，避免漏读")
    for sheet, rows, _ in extras:
        header=_header_mapping(rows,EXTRA_ALIASES)
        if not header or not {"order_no","packaging_type","required_quantity"}.issubset(header[1]):
            fail(f"“{sheet}”","缺少历史订单号、纸品类型或纸品需求数量表头")
        index,mapping=header
        check_weight_headers(rows[index], EXTRA_ALIASES, f"“{sheet}”表头")
        for rownum,row in enumerate(rows[index+1:],index+2):
            if not any(_text(_cell(row,mapping,key)) for key in EXTRA_ALIASES): continue
            source=f"“{sheet}”第 {rownum} 行"
            order_no=_text(_cell(row,mapping,"order_no"))
            head=main_by_number.get(order_no.casefold())
            if head is None: fail(source,"历史订单号未匹配到唯一的主表订单")
            values={key:_text(_cell(row,mapping,key)) for key in ("packaging_type","paper_quality","specification","dimension_unit","note")}
            values.update(required_quantity=number(_cell(row,mapping,"required_quantity"),source,"纸品需求数量",positive=True),
                **parse_weights(row, mapping, source),
                usage_quantity=number(_cell(row,mapping,"usage_quantity"),source,"每箱个数",positive=True),
                unit=_text(_cell(row,mapping,"unit")) or "张",unit_price=number(_cell(row,mapping,"unit_price"),source,"单价") or Decimal(0),
                currency=(_text(_cell(row,mapping,"currency")) or "CNY").upper(),price_source="历史导入")
            if values["required_quantity"] is None: fail(source,"纸品需求数量不能为空")
            parsed.append({**deepcopy(head),"source":source,"line":make_line(values,source)})
    for key,head in main_by_number.items():
        if not any(row["order_no"].casefold()==key for row in parsed):
            fail(head["source"],"至少填写一项大于0的纸品需求数量")
    if not parsed: fail("历史订单导入","没有可导入的纸品需求")
    return parsed,warnings
