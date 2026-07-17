import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from test_internal_quote_api import login, logout, make_client


pytestmark = pytest.mark.skipif(
    os.getenv("L5_2_ACCEPTANCE") != "1",
    reason="L5.2 real Disney acceptance is opt-in",
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _grade(material: str) -> str:
    return {
        "PVC": "普通透明",
        "ABS": "750SW",
        "TPR": "本白橡胶料",
    }[material]


def _machine_code(press_size_ton: float) -> str:
    return {120: "7A", 150: "12A", 180: "14A", 200: "18A"}[int(press_size_ton)]


def _painting_operations(quantity: float, unit_price_hkd: float) -> dict:
    return {
        code: {
            "quantity": quantity if code == "spray" else 0,
            "unit_price_hkd": unit_price_hkd if code == "spray" else 0,
        }
        for code in ("clamp", "pad_print", "spray", "edge", "paint", "dip", "wipe")
    }


def _payloads(baseline: dict) -> dict[str, dict]:
    quote_data = baseline["sheets"][0]["quoteData"]
    plastics = quote_data["plastics"]
    purchased_product = quote_data["purchasedProductParts"]
    purchased_package = quote_data["purchasedPackageParts"]
    materials = []
    for section, rows, category in (
        ("product", purchased_product, "hardware"),
        ("package", purchased_package, "packaging"),
    ):
        for row in rows:
            materials.append(
                {
                    "item": row["description"],
                    "category": category,
                    "quantity": 1,
                    "unit_price_rmb": max(round(row["perPartCostUsd"] * 7.75, 6), 0.0001),
                    "disney_description": row["description"],
                    "disney_section": section,
                    "disney_unit_price_usd": row["perPartCostUsd"],
                    "disney_included": row["included"],
                }
            )

    molds = []
    injection_lines = []
    for index, row in enumerate(plastics, start=1):
        mold_no = f"L5M{index:02d}"
        molds.append(
            {
                "item": f"{row['partDescription']} 模具",
                "quantity": 1,
                "cost_rmb": row["toolCostUsd"] * 7.75,
                "disney_mold_no": mold_no,
                "disney_parts": row["partDescription"],
                "disney_material": row["material"],
                "disney_cavities": row["cavities"],
                "disney_parts_per_shot": row["up"],
                "disney_tool_cost_usd": row["toolCostUsd"],
            }
        )
        injection_lines.append(
            {
                "item": row["partDescription"],
                "material": row["material"],
                "grade": _grade(row["material"]),
                "net_weight_g": row["shotWeightG"],
                "loss_rate_percent": 3,
                "machine_code": _machine_code(row["pressSizeTon"]),
                "sets": row["up"],
                "target_output": 2800,
                "quantity": 1,
                "disney_mold_no": mold_no,
                "disney_resin_cost_usd_kg": row["resinCostUsdKg"],
                "disney_cycle_time_seconds": row["cycleTimeSeconds"],
                "disney_labor_rate_usd_hr": row["laborRateUsdHr"],
            }
        )

    decorations = [
        {
            "application_type": row["applicationType"],
            "rate_per_op_usd": row["ratePerOpUsd"],
            "operations": row["operations"],
        }
        for row in quote_data["decoRows"]
    ]
    painting_rows = [
        {
            "item": row["applicationType"],
            "operations": _painting_operations(row["operations"], row["ratePerOpUsd"] * 7.8),
        }
        for row in quote_data["decoRows"]
    ]
    assembly_groups = [
        {
            "name": row["description"],
            "category": "packaging" if row["description"] == "Packaging" else "assembly",
            "processes": [
                {"name": row["description"], "persons": 1, "teams": 1, "production_qty": 1000}
            ],
        }
        for row in quote_data["laborRows"]
    ]
    metadata = quote_data["metadata"]
    return {
        "engineering": {
            "materials": materials,
            "molds": molds,
            "amortization_qty": metadata["moq"],
            "customer_mold_subsidy_usd": 0,
            "cartons": [],
        },
        "molding": {"injection_lines": injection_lines, "blow_lines": []},
        "painting": {"rows": painting_rows, "disney_decorations": decorations},
        "assembly": {"groups": assembly_groups, "labor_base_hkd": 310},
        "sales": {
            "additional_tax_hkd": 0,
            "indonesia_freight_hkd": 0,
            "tax_categories": [],
            "scenarios": [],
            "customer_quote_fields": {
                "buzzbee": {"color_box_tiers": []},
                "disney": {
                    "item_number": metadata["itemNumber"],
                    "quote_date": "2026-06-03",
                    "revision": metadata["revision"],
                    "minimum_order_qty": metadata["moq"],
                    "moq_prices_usd": {
                        "qty_3000": quote_data["moq3000Usd"],
                        "qty_5000": quote_data["moq5000Usd"],
                        "qty_10000": quote_data["moq10000Usd"],
                    },
                    "transportation_usd": quote_data["transportationUsd"],
                    "model_cost_usd": quote_data["modelCostUsd"],
                    "setup_charge_usd": quote_data["setupChargeUsd"],
                },
            },
        },
    }


def _approve_payload_section(client, quote_id: str, code: str, payload: dict) -> None:
    saved = client.put(
        f"/api/internal-quotes/{quote_id}/sections/{code}",
        json={"revision": 1, "payload": payload, "reason": "L5.2 真实迪士尼样表录入"},
    )
    assert saved.status_code == 200, saved.text
    submitted = client.post(
        f"/api/internal-quotes/{quote_id}/sections/{code}/submit",
        json={"revision": saved.json()["revision"]},
    )
    assert submitted.status_code == 200, submitted.text


def _review_payload_section(client, quote_id: str, code: str) -> None:
    section = client.get(f"/api/internal-quotes/{quote_id}").json()["sections"]
    current = next(row for row in section if row["department"] == code)
    reviewed = client.post(
        f"/api/internal-quotes/{quote_id}/sections/{code}/review",
        json={"revision": current["revision"], "decision": "approve", "reason": "L5.2 双人复核通过"},
    )
    assert reviewed.status_code == 200, reviewed.text


def _mark_not_applicable(client, quote_id: str, code: str) -> None:
    requested = client.post(
        f"/api/internal-quotes/{quote_id}/sections/{code}/request-na",
        json={"revision": 1, "reason": "真实样表无该分段"},
    )
    assert requested.status_code == 200, requested.text


def _approve_not_applicable(client, quote_id: str, code: str) -> None:
    section = client.get(f"/api/internal-quotes/{quote_id}").json()["sections"]
    current = next(row for row in section if row["department"] == code)
    reviewed = client.post(
        f"/api/internal-quotes/{quote_id}/sections/{code}/review",
        json={"revision": current["revision"], "decision": "approve", "reason": "确认真实样表不适用"},
    )
    assert reviewed.status_code == 200, reviewed.text


def test_l5_2_real_disney_full_release_preflight_consume_and_output(monkeypatch):
    baseline_path = Path(os.environ["L5_2_BASELINE_PATH"])
    p4_path = Path(os.environ["L5_2_P4_PATH"])
    template_path = Path(os.environ["L5_2_TEMPLATE_PATH"])
    output_path = Path(os.environ["L5_2_CUSTOMER_OUTPUT_PATH"])
    report_path = Path(os.environ["L5_2_REPORT_PATH"])
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    payloads = _payloads(baseline)

    with make_client(monkeypatch) as client:
        submitter = login(client, "l5_2_disney_submitter", "admin", "*", "*")
        create = {
            "factory_id": "huaxing",
            "workshop_code": "huaxing-workshop",
            "workshop_name": "华兴",
            "quote_no": "IQ-L5-2-DISNEY",
            "product_name": baseline["sheets"][0]["quoteData"]["metadata"]["itemName"],
            "customer": "迪士尼",
            "qty": 3000,
            "version_label": "V1",
            "initiator_department": "sales-business",
            "business_owner_id": submitter["id"],
            "business_owner_name": submitter["display_name"],
            "target_date": "2026-08-31",
            "remark": "L5.2 真实迪士尼样表验收",
        }
        created = client.post("/api/internal-quotes", json=create)
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]

        for code in ("engineering", "molding", "painting", "assembly"):
            _approve_payload_section(client, quote_id, code, payloads[code])
            logout(client)
            login(client, "l5_2_disney_reviewer", "admin", "*", "*")
            _review_payload_section(client, quote_id, code)
            logout(client)
            login(client, "l5_2_disney_submitter", "admin", "*", "*")

        for code in ("electronic", "slush", "sewing"):
            _mark_not_applicable(client, quote_id, code)
            logout(client)
            login(client, "l5_2_disney_reviewer", "admin", "*", "*")
            _approve_not_applicable(client, quote_id, code)
            logout(client)
            login(client, "l5_2_disney_submitter", "admin", "*", "*")

        _approve_payload_section(client, quote_id, "sales", payloads["sales"])
        logout(client)
        login(client, "l5_2_disney_reviewer", "admin", "*", "*")
        _review_payload_section(client, quote_id, "sales")
        logout(client)
        login(client, "l5_2_disney_submitter", "admin", "*", "*")

        submitted = client.post(
            f"/api/internal-quotes/{quote_id}/final-submit",
            json={"revision": 1},
        )
        assert submitted.status_code == 200, submitted.text
        logout(client)
        login(client, "l5_2_disney_reviewer", "admin", "*", "*")
        approved = client.post(
            f"/api/internal-quotes/{quote_id}/final-review",
            json={"revision": 2, "decision": "approve", "reason": "L5.2 迪士尼真实样表双人最终放行"},
        )
        assert approved.status_code == 200, approved.text
        final_export = approved.json()["export"]
        assert final_export["release_stage"] == "p4_final_approved"
        assert final_export["template_version"] == "internal-quote-p4-v2"

        artifacts = client.get(
            "/api/customer-price/internal-quote-artifacts?factory_id=huaxing"
        )
        assert artifacts.status_code == 200, artifacts.text
        handoff = artifacts.json()[0]
        downloaded = client.get(
            f"/api/customer-price/internal-quote-artifacts/{handoff['id']}/download"
        )
        assert downloaded.status_code == 200
        assert downloaded.headers["x-internal-quote-release-stage"] == "p4_final_approved"
        p4_path.parent.mkdir(parents=True, exist_ok=True)
        p4_path.write_bytes(downloaded.content)
        p4_sha = hashlib.sha256(downloaded.content).hexdigest()
        assert p4_sha == handoff["sha256"]

        env = os.environ.copy()
        env["L5_2_PHASE"] = "p4"
        verification = subprocess.run(
            [
                "cmd.exe", "/d", "/s", "/c",
                "npm.cmd run test:unit -- --run src/lib/__tests__/l5DisneyP4Acceptance.spec.ts",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
        assert verification.returncode == 0, verification.stdout + verification.stderr
        assert output_path.exists()

        consumed = client.post(
            f"/api/customer-price/internal-quote-artifacts/{handoff['id']}/consume",
            json={"consumer_reference": "L5.2-real-disney-p4"},
        )
        assert consumed.status_code == 200, consumed.text
        duplicate = client.post(
            f"/api/customer-price/internal-quote-artifacts/{handoff['id']}/consume",
            json={"consumer_reference": "L5.2-duplicate"},
        )
        assert duplicate.status_code == 409

        report = {
            "phase": "L5.2",
            "source_file": os.environ["L5_2_SOURCE_PATH"],
            "source_sha256": hashlib.sha256(Path(os.environ["L5_2_SOURCE_PATH"]).read_bytes()).hexdigest(),
            "quote_no": "IQ-L5-2-DISNEY",
            "quote_id": quote_id,
            "release_revision": approved.json()["quote"]["final_release_revision"],
            "handoff_id": handoff["id"],
            "handoff_status": consumed.json()["status"],
            "duplicate_consume_status": duplicate.status_code,
            "p4_file": str(p4_path),
            "p4_sha256": p4_sha,
            "customer_output_file": str(output_path),
            "customer_output_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            "template_file": str(template_path),
            "source_counts": {
                "plastics": len(baseline["sheets"][0]["quoteData"]["plastics"]),
                "purchased_product": len(baseline["sheets"][0]["quoteData"]["purchasedProductParts"]),
                "purchased_package": len(baseline["sheets"][0]["quoteData"]["purchasedPackageParts"]),
                "labor": len(baseline["sheets"][0]["quoteData"]["laborRows"]),
                "deco": len(baseline["sheets"][0]["quoteData"]["decoRows"]),
            },
            "moq_prices_usd": {
                "3000": baseline["sheets"][0]["quoteData"]["moq3000Usd"],
                "5000": baseline["sheets"][0]["quoteData"]["moq5000Usd"],
                "10000": baseline["sheets"][0]["quoteData"]["moq10000Usd"],
            },
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
