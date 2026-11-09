"""Create public synthetic JP trial files; never read customer files or server tests."""
from __future__ import annotations

import argparse
from datetime import datetime
from email.message import EmailMessage
from hashlib import sha256
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill


FILES = {
    "schedule": "01_合成演示_排期参照.xlsx",
    "price": "02_合成演示_货价参照.xlsx",
    "confirmed": "03_合成演示_确认价_USD.xlsx",
    "mail": "04_合成演示_问单邮件.eml",
}
ITEM = "99901"
LONG_ITEM = "99901-000-2B-003-ZZ0"
CUSTOMER_PO = "0000999001"


def _save_book(path: Path, title: str, rows: list[list], header: int = 1):
    book = Workbook()
    sheet = book.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    for cell in sheet[header]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="176659")
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = min(
            48, max(16, max(len(str(cell.value or "")) for cell in column) + 2)
        )
    sheet.freeze_panes = f"A{header + 1}"
    book.properties.title = "合成演示数据，不是真实客户资料"
    book.properties.creator = "JP 独立试用演示生成器"
    book.save(path)
    book.close()


def create_demo(output_dir: str | Path) -> dict:
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    planned = list(FILES.values()) + ["演示操作说明.txt", "demo-manifest.json"]
    existing = [name for name in planned if (output / name).exists()]
    if existing:
        raise FileExistsError("演示文件已存在，请使用空文件夹：" + ", ".join(existing))

    _save_book(output / FILES["schedule"], "华康B", [
        ["合成演示排期：全部为虚构资料，不可作为正式订单"],
        ["仅用于本机试用；此历史行用于演示资料带出与连续编号"],
        ["订单编号", "客名", "客PO", "", "", "货号", "子货号", "报关货号",
         "产品名称", "版本", "数量", "", "装箱数", "国家", "备注"],
        ["0126-0009", "Demo Customer", "0000000001", "", "", ITEM,
         ITEM + " ZZ0", ITEM, "合成演示玩具（非真实资料）", "3L", 3, "", 3,
         "美国", "合成历史记录"],
    ], header=3)

    # The price reference intentionally uses another packaging suffix.  The
    # explicit confirmation workbook below resolves the exact email variant.
    _save_book(output / FILES["price"], "合成演示货价", [
        ["货号编码", "产品货号", "客货价(HK$)", "货运类别", "长货号", "货价日期", "外箱-装箱数", "备注"],
        ["DEMO-C", ITEM, 12.5, "柜货", "99901-000-2B-003-AA0", datetime(2026, 11, 1), 3, "合成演示候选价"],
        ["DEMO-F", ITEM, 10, "出厂价", "99901-000-2B-003-AA0", datetime(2026, 11, 1), 3, "合成演示候选价"],
    ])
    _save_book(output / FILES["confirmed"], "合成演示确认价", [
        ["货号", "邮件长货号", "货运类别", "装箱数", "货币", "候选客货价(HK$)", "确认价格", "确认币种", "备注"],
        [ITEM, LONG_ITEM, "柜货", 3, "USD", 12.5, 3, "USD", "合成演示，3 USD 按系统规则换算为 23.4 HKD"],
        [ITEM, LONG_ITEM, "出厂价", 3, "USD", 10, 2, "USD", "合成演示，2 USD 按系统规则换算为 15.6 HKD"],
    ])

    mail = EmailMessage()
    mail["Subject"] = "Demo Customer order inquiry"
    mail["From"] = "Synthetic Demo <synthetic-demo@example.invalid>"
    mail["To"] = "Local Trial <local-trial@example.invalid>"
    mail["Date"] = "Mon, 09 Nov 2026 10:00:00 +0800"
    mail["Message-ID"] = "<jp-synthetic-demo-20261109@example.invalid>"
    mail.set_content("合成演示，不是真实客户订单。请使用 HTML 表格预览本机问单流程。")
    mail.add_alternative(
        "<html><body><h2>合成演示，不是真实客户订单</h2>"
        "<p>S/D 12/31/2026</p><p>仅供本机试用，所有货号、价格和订单均为虚构。</p>"
        "<table><tr><th>Item</th><th>Qty</th><th>Customer PO</th></tr>"
        f"<tr><td>{LONG_ITEM}</td><td>12</td><td>{CUSTOMER_PO}</td></tr></table>"
        "</body></html>", subtype="html"
    )
    (output / FILES["mail"]).write_bytes(mail.as_bytes())

    instructions = """华康 B JP 问单：纯合成演示

这里的客户、货号、价格、订单、邮箱均为虚构，不包含真实客户资料。
建议先在空白试用数据中演示，演示文件不要上传正式系统。

1. 启动华康 B 问单试用包，在参照资料处上传 01（排期）和 02（货价）。
2. 上传 03（确认价），数字币种选择 USD。本示例含柜货和出厂价两条确认价。
3. 在问单导入处填写跟单员“演示跟单”，来单日期填 2026-11-09，上传 04 邮件。
4. 点击解析，核对一行：Demo Customer，客 PO 0000999001，货号 99901，数量 12，装箱数 3。
   确认后的柜货价为 23.4 HKD，出厂价为 15.6 HKD；是系统按 USD × 7.8 换算的演示值。
   若先不上传 03，可观察长货号版本不同时的货价待确认提示；上传 03 后重新解析。
5. 勾选该行，核对日期、价格和跟单员，填写“合成演示已核对”，确认导出。
6. 导出为 44 列金山格式 Excel：1 行表头 + 1 行数据。空白试用库首个流水号为 10。
   在历史导出中可重新下载；重复同批提交复用导出，不应再次增加流水号。

参照中那一条旧记录只用于演示历史资料与编号，不会作为新订单导出。
已存在试用数据时，编号会接着本机数据递增，不一定从 10 开始。
本机试用数据独立保存，不会上传或修改线上系统，也不与其他电脑合并编号。
"""
    (output / "演示操作说明.txt").write_text(instructions, encoding="utf-8-sig")
    manifest = {
        "synthetic_only": True,
        "description": "全部为虚构演示资料，不包含真实客户信息",
        "files": FILES,
        "expected": {"rows": 1, "export_columns": 44, "customer_po": CUSTOMER_PO,
                     "item": ITEM, "quantity": 12, "price_hkd": "23.4", "factory_price_hkd": "15.6"},
        "sha256": {name: sha256((output / name).read_bytes()).hexdigest() for name in FILES.values()},
    }
    (output / "demo-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    create_demo(args.output_dir)
    print(f"已生成 3 份合成参照表和 1 封合成邮件：{args.output_dir.resolve()}")
