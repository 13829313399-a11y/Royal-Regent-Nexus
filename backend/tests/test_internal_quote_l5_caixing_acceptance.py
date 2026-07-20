import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from test_internal_quote_api import login, logout, make_client


pytestmark = pytest.mark.skipif(
    os.getenv("L5_4_ACCEPTANCE") != "1",
    reason="L5.4 real Caixing acceptance is opt-in",
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _group_cost_rows(rows: list[dict]) -> list[dict]:
    grouped = []
    for row in rows:
        category = str(row.get("category", ""))
        description = str(row.get("description", ""))
        haystack = f"{category} {description}"
        if "纸箱" in haystack or "Carton" in haystack:
            group = "carton"
        elif any(key in haystack for key in ("彩盒", "内咭", "吸塑")):
            group = "packing"
        elif any(key in haystack for key in ("电子", "电池", "IC")):
            group = "electronic"
        elif "车衣" in haystack:
            group = "fabric"
        elif any(key in haystack for key in ("油漆", "喷油")):
            group = "spraying"
        elif "包装人工" in haystack:
            group = "packout"
        elif "装配工" in haystack:
            group = "assembly"
        elif "车发" in haystack:
            group = "rooting"
        elif any(key in haystack for key in ("五金", "其它外购", "其他外购", "利宝", "说明书", "马达")):
            group = "purchase"
        else:
            continue
        grouped.append(
            {
                "group": group,
                "tax_tag": row.get("taxTag", ""),
                "category": category,
                "description": description,
                "base_cost_hkd": row["baseCostHkd"],
                "customer_cost_hkd": row["customerCostHkd"],
            }
        )
    return grouped


def _tool_plan_rows(product_type: str, quote_data: dict) -> list[dict]:
    rows = []
    material_codes = {
        "plastic": {"ABS": 1, "PVC": 2, "HIPS": 3, "PE": 4, "PP": 5, "POM": 7, "C-ABS": 9, "C-PP": 5},
        "plush": {"ABS": 1, "PVC": 2, "C-ABS": 3, "TPR": 4, "PP": 5, "C-PP": 6, "POM": 7, "PE": 8},
    }[product_type]
    item_no = quote_data["metadata"]["itemNo"]
    for row in quote_data["injectionRows"]:
        if not row.get("material") or row.get("materialCostHkd", 0) <= 0 or row.get("moldingCostHkd", 0) <= 0:
            continue
        rows.append(
            {
                "ref_no": str(row["lineNo"]),
                "process_type": "IN",
                "tool_no": "",
                "tooling_cost_hkd": row.get("customerMoldCostHkd", 0),
                "description": row["name"],
                "sku_no": item_no,
                "cavities": row["partsPerShot"],
                "up": row["setsPerShot"],
                "net_weight_g": row["weightG"],
                "material_code": material_codes[row["material"]],
                "material": row["material"],
                "color": "",
                "material_cost_hkd": row["materialCostHkd"],
                "machine_size": str(row["machineTons"]),
                "cycle_time_seconds": row["cycleSeconds"],
                "process_cost_hkd": row["moldingCostHkd"],
            }
        )
    if product_type == "plastic":
        rows.append(
            {"ref_no": "B1", "process_type": "BL", "tool_no": "", "tooling_cost_hkd": 0, "description": "剑身", "sku_no": item_no, "cavities": 1, "up": 1, "net_weight_g": 50, "material_code": 11, "material": "LDPE", "color": "", "material_cost_hkd": 0.722, "machine_size": "BL", "cycle_time_seconds": 45, "process_cost_hkd": 0.718}
        )
    else:
        rows.insert(
            0,
            {"ref_no": "R1", "process_type": "RC", "tool_no": "", "tooling_cost_hkd": 14220, "description": "公仔头", "sku_no": item_no, "cavities": 12, "up": 12, "net_weight_g": 7, "material_code": 14, "material": "PVC", "color": "", "material_cost_hkd": 0.125, "machine_size": "RC", "cycle_time_seconds": 155, "process_cost_hkd": 0.36},
        )
    return rows


def _payloads(product_type: str, baseline: dict) -> dict[str, dict]:
    quote_data = baseline["sheets"][0]["quoteData"]
    tool_rows = _tool_plan_rows(product_type, quote_data)
    molds = []
    source_rows = {str(row["lineNo"]): row for row in quote_data["injectionRows"] if row.get("customerMoldCostHkd", 0) > 0}
    for row in tool_rows:
        if row["tooling_cost_hkd"] <= 0:
            continue
        source = source_rows.get(row["ref_no"], {})
        molds.append(
            {
                "item": f"{row['description']} 模具",
                "quantity": 1,
                "cost_rmb": source.get("moldCostHkd", row["tooling_cost_hkd"]),
                "caixing_tool_plan_ref": row["ref_no"],
                "caixing_mold_cost_hkd": source.get("moldCostHkd", row["tooling_cost_hkd"]),
                "caixing_customer_mold_cost_hkd": row["tooling_cost_hkd"],
            }
        )
    metadata = quote_data["metadata"]
    carton = metadata["carton"]
    return {
        "engineering": {
            "materials": [],
            "molds": molds,
            "amortization_qty": 3000,
            "customer_mold_subsidy_usd": 0,
            "cartons": [],
        },
        "molding": {
            "injection_lines": [],
            "blow_lines": [],
            "caixing_tool_plan_rows": tool_rows,
        },
        "sales": {
            "additional_tax_hkd": 0,
            "indonesia_freight_hkd": 0,
            "tax_categories": [],
            "scenarios": [],
            "customer_quote_fields": {
                "caixing": {
                    "product_type": product_type,
                    "item_number": metadata["itemNo"],
                    "item_name": metadata["itemName"],
                    "quote_date": "2026-06-27" if product_type == "plastic" else "2026-06-02",
                    "carton_length_in": carton["length"],
                    "carton_width_in": carton["width"],
                    "carton_height_in": carton["height"],
                    "carton_cuft": carton["cube"],
                    "carton_cbm": carton["cbm"],
                    "pcs_per_carton": carton["pcsPerCarton"],
                    "carton_price_hkd": carton["cartonPrice"],
                    "cost_rows": _group_cost_rows(quote_data["costRows"]),
                }
            },
        },
    }


def _save_submit(client, quote_id: str, code: str, payload: dict, product_type: str) -> None:
    saved = client.put(
        f"/api/internal-quotes/{quote_id}/sections/{code}",
        json={"revision": 1, "payload": payload, "reason": f"L5.4 彩星{product_type}真实样表录入"},
    )
    assert saved.status_code == 200, saved.text
    submitted = client.post(
        f"/api/internal-quotes/{quote_id}/sections/{code}/submit",
        json={"revision": saved.json()["revision"]},
    )
    assert submitted.status_code == 200, submitted.text


def _review(client, quote_id: str, code: str) -> None:
    sections = client.get(f"/api/internal-quotes/{quote_id}").json()["sections"]
    current = next(row for row in sections if row["department"] == code)
    reviewed = client.post(
        f"/api/internal-quotes/{quote_id}/sections/{code}/review",
        json={"revision": current["revision"], "decision": "approve", "reason": "L5.4 彩星双人复核通过"},
    )
    assert reviewed.status_code == 200, reviewed.text


def _request_na(client, quote_id: str, code: str) -> None:
    requested = client.post(
        f"/api/internal-quotes/{quote_id}/sections/{code}/request-na",
        json={"revision": 1, "reason": "彩星客户专属字段已由工程、啤机和业务分段完整承载"},
    )
    assert requested.status_code == 200, requested.text


def _approve_na(client, quote_id: str, code: str) -> None:
    sections = client.get(f"/api/internal-quotes/{quote_id}").json()["sections"]
    current = next(row for row in sections if row["department"] == code)
    reviewed = client.post(
        f"/api/internal-quotes/{quote_id}/sections/{code}/review",
        json={"revision": current["revision"], "decision": "approve", "reason": "确认该分段不适用"},
    )
    assert reviewed.status_code == 200, reviewed.text


def test_l5_4_real_caixing_plastic_and_plush_release_consume_and_output(monkeypatch):
    cases = [
        {
            "product_type": "plastic",
            "baseline": Path(os.environ["L5_4_PLASTIC_BASELINE_PATH"]),
            "source": Path(os.environ["L5_4_PLASTIC_SOURCE_PATH"]),
            "p4": Path(os.environ["L5_4_PLASTIC_P4_PATH"]),
            "output": Path(os.environ["L5_4_PLASTIC_OUTPUT_PATH"]),
            "quote_no": "IQ-L5-4-CAIXING-PLASTIC",
        },
        {
            "product_type": "plush",
            "baseline": Path(os.environ["L5_4_PLUSH_BASELINE_PATH"]),
            "source": Path(os.environ["L5_4_PLUSH_SOURCE_PATH"]),
            "p4": Path(os.environ["L5_4_PLUSH_P4_PATH"]),
            "output": Path(os.environ["L5_4_PLUSH_OUTPUT_PATH"]),
            "quote_no": "IQ-L5-4-CAIXING-PLUSH",
        },
    ]
    released = []
    with make_client(monkeypatch) as client:
        for case in cases:
            baseline = json.loads(case["baseline"].read_text(encoding="utf-8"))
            quote_data = baseline["sheets"][0]["quoteData"]
            payloads = _payloads(case["product_type"], baseline)
            submitter = login(client, f"l5_4_{case['product_type']}_submitter", "admin", "*", "*")
            created = client.post(
                "/api/internal-quotes",
                json={
                    "factory_id": "huaxing",
                    "workshop_code": "huaxing-workshop",
                    "workshop_name": "华兴",
                    "quote_no": case["quote_no"],
                    "product_name": quote_data["metadata"]["itemName"],
                    "customer": "彩星",
                    "qty": 3000,
                    "version_label": "V1",
                    "initiator_department": "sales-business",
                    "business_owner_id": f"user-l5_4_{case['product_type']}_reviewer",
                    "business_owner_name": f"l5_4_{case['product_type']}_reviewer",
                    "target_date": "2026-08-31",
                    "remark": f"L5.4 彩星{case['product_type']}真实样表验收",
                    "participating_sections": [
                        "sales", "engineering", "electronic", "molding",
                        "painting", "slush", "sewing", "assembly",
                    ],
                },
            )
            assert created.status_code == 201, created.text
            quote_id = created.json()["id"]

            for code in ("engineering", "molding"):
                _save_submit(client, quote_id, code, payloads[code], case["product_type"])
                logout(client)
                login(client, f"l5_4_{case['product_type']}_reviewer", "admin", "*", "*")
                _review(client, quote_id, code)
                logout(client)
                login(client, f"l5_4_{case['product_type']}_submitter", "admin", "*", "*")

            for code in ("electronic", "painting", "slush", "sewing", "assembly"):
                _request_na(client, quote_id, code)
                logout(client)
                login(client, f"l5_4_{case['product_type']}_reviewer", "admin", "*", "*")
                _approve_na(client, quote_id, code)
                logout(client)
                login(client, f"l5_4_{case['product_type']}_submitter", "admin", "*", "*")

            # Sales is the downstream aggregation section and must be reviewed
            # after all upstream sections (including N/A approvals) are final.
            _save_submit(client, quote_id, "sales", payloads["sales"], case["product_type"])
            logout(client)
            login(client, f"l5_4_{case['product_type']}_reviewer", "admin", "*", "*")
            _review(client, quote_id, "sales")
            logout(client)
            login(client, f"l5_4_{case['product_type']}_submitter", "admin", "*", "*")

            submitted = client.post(f"/api/internal-quotes/{quote_id}/final-submit", json={"revision": 1})
            assert submitted.status_code == 200, submitted.text
            logout(client)
            login(client, f"l5_4_{case['product_type']}_reviewer", "admin", "*", "*")
            approved = client.post(
                f"/api/internal-quotes/{quote_id}/final-review",
                json={"revision": 2, "decision": "approve", "reason": "L5.4 彩星真实样表最终放行"},
            )
            assert approved.status_code == 200, approved.text
            artifacts = client.get("/api/customer-price/internal-quote-artifacts?factory_id=huaxing")
            assert artifacts.status_code == 200, artifacts.text
            handoff = next(row for row in artifacts.json() if row["quote_no"] == case["quote_no"])
            downloaded = client.get(f"/api/customer-price/internal-quote-artifacts/{handoff['id']}/download")
            assert downloaded.status_code == 200, downloaded.text
            case["p4"].parent.mkdir(parents=True, exist_ok=True)
            case["p4"].write_bytes(downloaded.content)
            assert hashlib.sha256(downloaded.content).hexdigest() == handoff["sha256"]
            released.append({"case": case, "quote_id": quote_id, "handoff": handoff, "approved": approved.json()})
            logout(client)

        env = os.environ.copy()
        env["L5_4_PHASE"] = "p4"
        verification = subprocess.run(
            ["cmd.exe", "/d", "/s", "/c", "node_modules\\.bin\\vitest.cmd run src/lib/__tests__/l5CaixingP4Acceptance.spec.ts"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=240,
            check=False,
        )
        assert verification.returncode == 0, verification.stdout + verification.stderr

        login(client, "l5_4_consumer", "admin", "*", "*")
        for item in released:
            handoff = item["handoff"]
            consumed = client.post(
                f"/api/customer-price/internal-quote-artifacts/{handoff['id']}/consume",
                json={"consumer_reference": f"L5.4-{item['case']['product_type']}-p4"},
            )
            assert consumed.status_code == 200, consumed.text
            duplicate = client.post(
                f"/api/customer-price/internal-quote-artifacts/{handoff['id']}/consume",
                json={"consumer_reference": "L5.4-duplicate"},
            )
            assert duplicate.status_code == 409
            item["consumed"] = consumed.json()
            item["duplicate_status"] = duplicate.status_code

    report = {
        "phase": "L5.4",
        "cases": [
            {
                "product_type": item["case"]["product_type"],
                "source_file": str(item["case"]["source"]),
                "source_sha256": hashlib.sha256(item["case"]["source"].read_bytes()).hexdigest(),
                "quote_no": item["case"]["quote_no"],
                "quote_id": item["quote_id"],
                "handoff_id": item["handoff"]["id"],
                "handoff_status": item["consumed"]["status"],
                "duplicate_consume_status": item["duplicate_status"],
                "p4_file": str(item["case"]["p4"]),
                "p4_sha256": hashlib.sha256(item["case"]["p4"].read_bytes()).hexdigest(),
                "customer_output_file": str(item["case"]["output"]),
                "customer_output_sha256": hashlib.sha256(item["case"]["output"].read_bytes()).hexdigest(),
            }
            for item in released
        ],
    }
    Path(os.environ["L5_4_REPORT_PATH"]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
