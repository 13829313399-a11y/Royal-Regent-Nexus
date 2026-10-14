"""Render our generated workbook, never execute formulas from uploaded documents.

This small evaluator only supports the formula vocabulary emitted by
internal_quote_excel. Unsupported/error cells are visibly unavailable, not zero.
It is a display adapter; quote calculations and persistence remain authoritative.
"""
import math
import re
import base64
from decimal import Decimal, ROUND_HALF_UP

from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.utils import get_column_letter, range_boundaries


class FormulaError(ValueError):
    pass


class WorkbookValues:
    def __init__(self, workbook):
        self.workbook = workbook
        self.cache = {}
        self.active = set()

    def cell(self, sheet, address):
        key = (sheet, address.replace("$", ""))
        if key in self.cache:
            return self.cache[key]
        if key in self.active or len(self.active) > 150:
            raise FormulaError("循环引用")
        self.active.add(key)
        try:
            value = self.workbook[sheet][key[1]].value
            if isinstance(value, str) and value.startswith("="):
                value = self.evaluate(self.parse(value), sheet)
            if isinstance(value, float) and not math.isfinite(value):
                raise FormulaError("无效金额")
            self.cache[key] = value
            return value
        finally:
            self.active.remove(key)

    @staticmethod
    def parse(formula):
        tokens = [t for t in Tokenizer(formula).items if t.type != "WHITE-SPACE"]
        position = 0
        precedence = {"=": 1, "<>": 1, "<": 1, ">": 1, "<=": 1, ">=": 1,
                      "&": 2, "+": 3, "-": 3, "*": 4, "/": 4, "^": 5}

        def expression(minimum=0):
            nonlocal position
            if position >= len(tokens):
                raise FormulaError("不完整公式")
            token = tokens[position]
            position += 1
            if token.type == "OPERATOR-PREFIX":
                node = ("unary", token.value, expression(5))
            elif token.type in {"FUNC", "PAREN"} and token.subtype == "OPEN":
                args = []
                if position < len(tokens) and tokens[position].subtype != "CLOSE":
                    args.append(expression())
                    while position < len(tokens) and tokens[position].type == "SEP":
                        position += 1
                        args.append(expression())
                if position >= len(tokens) or tokens[position].subtype != "CLOSE":
                    raise FormulaError("不完整括号")
                position += 1
                node = ("function", token.value[:-1].upper(), args) if token.type == "FUNC" else args[0]
            elif token.type == "OPERAND":
                node = ("operand", token.subtype, token.value)
            else:
                raise FormulaError("不支持的公式")
            while position < len(tokens):
                operator = tokens[position]
                if operator.type == "OPERATOR-POSTFIX" and operator.value == "%":
                    position += 1
                    node = ("percent", node)
                    continue
                priority = precedence.get(operator.value, -1) if operator.type == "OPERATOR-INFIX" else -1
                if priority < minimum:
                    break
                position += 1
                node = ("binary", operator.value, node, expression(priority + 1))
            return node

        result = expression()
        if position != len(tokens):
            raise FormulaError("不支持的公式内容")
        return result

    @staticmethod
    def number(value):
        if value is None or value == "":
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError) as error:
            raise FormulaError("非数字运算") from error

    def evaluate(self, node, sheet):
        kind = node[0]
        if kind == "operand":
            subtype, value = node[1:]
            if subtype == "NUMBER":
                return float(value)
            if subtype == "TEXT":
                return value[1:-1].replace('""', '"')
            if subtype == "LOGICAL":
                return value == "TRUE"
            if subtype != "RANGE":
                raise FormulaError("不支持的引用")
            if "!" in value:
                sheet, value = value.rsplit("!", 1)
                sheet = sheet.strip("'").replace("''", "'")
            if sheet not in self.workbook.sheetnames or not re.fullmatch(r"\$?[A-Z]+\$?\d+(?::\$?[A-Z]+\$?\d+)?", value):
                raise FormulaError("无效引用")
            if ":" not in value:
                return self.cell(sheet, value)
            c1, r1, c2, r2 = range_boundaries(value)
            if (r2 - r1 + 1) * (c2 - c1 + 1) > 50000:
                raise FormulaError("引用范围过大")
            return [self.cell(sheet, f"{get_column_letter(c)}{r}") for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]
        if kind == "unary":
            return self.number(self.evaluate(node[2], sheet)) * (-1 if node[1] == "-" else 1)
        if kind == "percent":
            return self.number(self.evaluate(node[1], sheet)) / 100
        if kind == "binary":
            op = node[1]
            left, right = self.evaluate(node[2], sheet), self.evaluate(node[3], sheet)
            if op == "&":
                return str(left or "") + str(right or "")
            if op in {"=", "<>"} and (isinstance(left, str) or isinstance(right, str)):
                # Currency labels and blank-input checks are emitted by our
                # sewing workbook. An explicit numeric zero is not blank.
                left = "" if left is None else left
                right = "" if right is None else right
                equal = left.casefold() == right.casefold() if isinstance(left, str) and isinstance(right, str) else left == right
                return equal if op == "=" else not equal
            left, right = self.number(left), self.number(right)
            if op == "+": return left + right
            if op == "-": return left - right
            if op == "*": return left * right
            if op == "/": return left / right
            if op == "^" and abs(right) <= 100: return left ** right
            if op == "=": return left == right
            if op == "<>": return left != right
            if op == "<": return left < right
            if op == ">": return left > right
            if op == "<=": return left <= right
            if op == ">=": return left >= right
            raise FormulaError("不支持的运算")
        name, nodes = node[1:]
        if name == "IFERROR":
            try:
                return self.evaluate(nodes[0], sheet)
            except (ValueError, ZeroDivisionError, OverflowError):
                return self.evaluate(nodes[1], sheet)
        if name == "IF":
            return self.evaluate(nodes[1] if self.evaluate(nodes[0], sheet) else nodes[2], sheet)
        args = [self.evaluate(arg, sheet) for arg in nodes]
        flattened = [v for arg in args for v in (arg if isinstance(arg, list) else [arg])]
        if name == "AND": return all(bool(v) for v in flattened)
        if name == "OR": return any(bool(v) for v in flattened)
        numbers = [self.number(v) for v in flattened if isinstance(v, (int, float))]
        if name == "SUM": return sum(numbers)
        if name == "MAX": return max(numbers, default=0)
        if name == "MIN": return min(numbers, default=0)
        if name == "ROUND":
            return float(Decimal(str(args[0])).quantize(Decimal(1).scaleb(-int(args[1])), rounding=ROUND_HALF_UP))
        if name == "VALUE": return self.number(args[0])
        if name == "LEN": return len(str(args[0] or ""))
        if name == "LEFT": return str(args[0])[:int(args[1]) if len(args) > 1 else 1]
        if name == "RIGHT":
            count = int(args[1]) if len(args) > 1 else 1
            return str(args[0])[-count:] if count else ""
        if name == "MID": return str(args[0])[int(args[1]) - 1:int(args[1]) - 1 + int(args[2])]
        if name == "TRIM": return " ".join(str(args[0]).split())
        if name == "FIND": return str(args[1]).index(str(args[0]), int(args[2]) - 1 if len(args) > 2 else 0) + 1
        if name == "SUBSTITUTE" and len(args) == 3: return str(args[0]).replace(str(args[1]), str(args[2]))
        if name == "REPT" and 0 <= int(args[1]) <= 10000: return str(args[0]) * int(args[1])
        if name == "SUMIF":
            criteria, match, values = args if len(args) == 3 else (args[0], args[1], args[0])
            pattern = re.escape(str(match)).replace(r"\*", ".*").replace(r"\?", ".")
            return sum(self.number(v) for c, v in zip(criteria, values) if re.fullmatch(pattern, str(c if c is not None else ""), re.IGNORECASE))
        raise FormulaError(f"不支持的函数 {name}")


def color(value, fallback):
    return f"#{value.rgb[-6:]}" if value is not None and value.type == "rgb" else fallback


def display_value(value, number_format):
    if value is None:
        return ""
    if not isinstance(value, (int, float)):
        return str(value)
    pattern = number_format.split(";")[0]
    places = re.search(r"\.([0#]+)", pattern)
    precision = len(places[1]) if places else 0
    if pattern == "General":
        return f"{value:.6f}".rstrip("0").rstrip(".")
    if "%" in pattern:
        return f"{value * 100:.{precision}f}%"
    return format(value, f"{',' if ',' in pattern else ''}.{precision}f")


def serialize_workbook(workbook):
    evaluator = WorkbookValues(workbook)
    sheets, errors = [], []
    for sheet in workbook:
        if sheet.sheet_state != "visible":
            continue
        merged, covered = {}, set()
        for area in sheet.merged_cells.ranges:
            merged[(area.min_row, area.min_col)] = (area.max_row - area.min_row + 1, area.max_col - area.min_col + 1)
            covered.update((r, c) for r in range(area.min_row, area.max_row + 1) for c in range(area.min_col, area.max_col + 1) if (r, c) != (area.min_row, area.min_col))
        rows = []
        for row in sheet:
            cells = []
            for cell in row:
                if (cell.row, cell.column) in covered:
                    continue
                failed = False
                try:
                    value = evaluator.cell(sheet.title, cell.coordinate)
                except (ValueError, ZeroDivisionError, OverflowError, KeyError, TypeError):
                    value, failed = "待核算", True
                    errors.append(f"{sheet.title}!{cell.coordinate}")
                style = {"color": color(cell.font.color, "#172f2d"), "backgroundColor": color(cell.fill.fgColor, "#ffffff") if cell.fill.patternType == "solid" else "#ffffff",
                         "fontWeight": "700" if cell.font.bold else "400", "fontSize": f"{(cell.font.sz or 10) * 4 / 3:.1f}px",
                         "textAlign": {"centerContinuous": "center"}.get(cell.alignment.horizontal, cell.alignment.horizontal or "left"),
                         "whiteSpace": "pre-wrap" if cell.alignment.wrap_text else "nowrap"}
                for side in ("left", "right", "top", "bottom"):
                    edge = getattr(cell.border, side)
                    if edge and edge.style:
                        style[f"border{side.title()}"] = f"{2 if edge.style in {'medium', 'thick', 'double'} else 1}px solid {color(edge.color, '#839994')}"
                rowspan, colspan = merged.get((cell.row, cell.column), (1, 1))
                cells.append({"address": cell.coordinate, "column": cell.column, "text": display_value(value, cell.number_format),
                              "rowspan": rowspan, "colspan": colspan, "style": style, "unavailable": failed,
                              "binding": getattr(sheet, "_quote_bindings", {}).get(cell.coordinate)})
            rows.append({"index": row[0].row, "height": max(20, (sheet.row_dimensions[row[0].row].height or 15) * 4 / 3), "cells": cells})
        widths = [round((sheet.column_dimensions[get_column_letter(c)].width or 13) * 7 + 5) for c in range(1, sheet.max_column + 1)]
        images = []
        for picture in sheet._images:
            anchor = picture.anchor
            if hasattr(anchor, "_from"):
                marker = anchor._from
                images.append({"src": "data:image/" + picture.format + ";base64," + base64.b64encode(picture._data()).decode(),
                               "left": sum(widths[:marker.col]) + marker.colOff / 9525,
                               "top": sum(row["height"] for row in rows[:marker.row]) + marker.rowOff / 9525,
                               "width": anchor.ext.cx / 9525 if hasattr(anchor, "ext") else picture.width,
                               "height": anchor.ext.cy / 9525 if hasattr(anchor, "ext") else picture.height})
        sheets.append({"name": sheet.title, "widths": widths, "rows": rows, "images": images})
    return sheets, errors
