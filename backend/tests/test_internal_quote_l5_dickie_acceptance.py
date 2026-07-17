import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from test_internal_quote_api import login, logout, make_client


pytestmark = pytest.mark.skipif(
    os.getenv("L5_3_ACCEPTANCE") != "1",
    reason="L5.3 real Dickie acceptance is opt-in",
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _payloads(baseline: dict) -> dict[str, dict]:
    molds = [
        {
            "item": f"{row['parts_en']} 模具",
            "quantity": 1,
            "cost_rmb": row["mold_cost_hkd"],
            "dickie_project_name_en": row["project_name_en"],
            "dickie_mold_no": row["mold_no"],
            "dickie_parts_en": row["parts_en"],
            "dickie_resin": row["resin"],
            "dickie_mold_size": row["mold_size"],
            "dickie_mold_material": row["mold_material"],
            "dickie_cavities": row["cavities"],
            "dickie_parts_per_shot": row["parts_per_shot"],
            "dickie_mold_cost_hkd": row["mold_cost_hkd"],
            "dickie_remark_en": row["remark_en"],
        }
        for row in baseline["mold_rows"]
    ]
    return {
        "engineering": {
            "materials": [],
            "molds": molds,
            "amortization_qty": 10_000,
            "customer_mold_subsidy_usd": 0,
            "cartons": [],
        },
        "sales": {
            "additional_tax_hkd": 0,
            "indonesia_freight_hkd": 0,
            "tax_categories": [],
            "scenarios": [],
            "customer_quote_fields": {
                "dickie": {
                    "client_name": baseline["client_name"],
                    "quote_date": "2026-05-15",
                    "attention": baseline["attention"],
                    "revision": baseline["revision"],
                    "from_name": baseline["from_name"],
                    "project_name_en": "Disney Cable Car Series",
                    "first_shot_time": baseline["first_shot_time"],
                    "finish_time": baseline["finish_time"],
                    "product_rows": baseline["product_rows"],
                    "remark_lines": baseline["remark_lines"],
                    "material_prices_hkd": baseline["material_prices_hkd"],
                }
            },
        },
    }


def _save_and_submit(client, quote_id: str, code: str, payload: dict) -> None:
    saved = client.put(
        f"/api/internal-quotes/{quote_id}/sections/{code}",
        json={"revision": 1, "payload": payload, "reason": "L5.3 Dickie 真实样表录入"},
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
        json={"revision": current["revision"], "decision": "approve", "reason": "L5.3 双人复核通过"},
    )
    assert reviewed.status_code == 200, reviewed.text


def _request_na(client, quote_id: str, code: str) -> None:
    requested = client.post(
        f"/api/internal-quotes/{quote_id}/sections/{code}/request-na",
        json={"revision": 1, "reason": "Dickie 客户专属字段由业务与工程分段完整承载"},
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


def test_l5_3_real_dickie_full_release_preflight_consume_and_output(monkeypatch):
    baseline_path = Path(os.environ["L5_3_BASELINE_PATH"])
    p4_path = Path(os.environ["L5_3_P4_PATH"])
    template_path = Path(os.environ["L5_3_TEMPLATE_PATH"])
    output_path = Path(os.environ["L5_3_CUSTOMER_OUTPUT_PATH"])
    report_path = Path(os.environ["L5_3_REPORT_PATH"])
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    payloads = _payloads(baseline)

    with make_client(monkeypatch) as client:
        submitter = login(client, "l5_3_dickie_submitter", "admin", "*", "*")
        created = client.post(
            "/api/internal-quotes",
            json={
                "factory_id": "huaxing",
                "workshop_code": "huaxing-workshop",
                "workshop_name": "华兴",
                "quote_no": "IQ-L5-3-DICKIE",
                "product_name": "Disney Cable Car Series",
                "customer": "Dickie",
                "qty": 10_000,
                "version_label": "V1",
                "initiator_department": "sales-business",
                "business_owner_id": submitter["id"],
                "business_owner_name": submitter["display_name"],
                "target_date": "2026-08-31",
                "remark": "L5.3 Dickie Disney Cable 真实样表验收",
            },
        )
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]

        _save_and_submit(client, quote_id, "engineering", payloads["engineering"])
        logout(client)
        login(client, "l5_3_dickie_reviewer", "admin", "*", "*")
        _review(client, quote_id, "engineering")
        logout(client)
        login(client, "l5_3_dickie_submitter", "admin", "*", "*")

        for code in ("electronic", "molding", "painting", "slush", "sewing", "assembly"):
            _request_na(client, quote_id, code)
            logout(client)
            login(client, "l5_3_dickie_reviewer", "admin", "*", "*")
            _approve_na(client, quote_id, code)
            logout(client)
            login(client, "l5_3_dickie_submitter", "admin", "*", "*")

        _save_and_submit(client, quote_id, "sales", payloads["sales"])
        logout(client)
        login(client, "l5_3_dickie_reviewer", "admin", "*", "*")
        _review(client, quote_id, "sales")
        logout(client)
        login(client, "l5_3_dickie_submitter", "admin", "*", "*")

        submitted = client.post(f"/api/internal-quotes/{quote_id}/final-submit", json={"revision": 1})
        assert submitted.status_code == 200, submitted.text
        logout(client)
        login(client, "l5_3_dickie_reviewer", "admin", "*", "*")
        approved = client.post(
            f"/api/internal-quotes/{quote_id}/final-review",
            json={"revision": 2, "decision": "approve", "reason": "L5.3 Dickie 真实样表最终放行"},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["export"]["release_stage"] == "p4_final_approved"
        assert approved.json()["export"]["template_version"] == "internal-quote-p4-v2"

        artifacts = client.get("/api/customer-price/internal-quote-artifacts?factory_id=huaxing")
        assert artifacts.status_code == 200, artifacts.text
        handoff = artifacts.json()[0]
        downloaded = client.get(f"/api/customer-price/internal-quote-artifacts/{handoff['id']}/download")
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.headers["x-internal-quote-release-stage"] == "p4_final_approved"
        p4_path.parent.mkdir(parents=True, exist_ok=True)
        p4_path.write_bytes(downloaded.content)
        p4_sha = hashlib.sha256(downloaded.content).hexdigest()
        assert p4_sha == handoff["sha256"]

        env = os.environ.copy()
        env["L5_3_PHASE"] = "p4"
        verification = subprocess.run(
            ["cmd.exe", "/d", "/s", "/c", "npm.cmd run test:unit -- --run src/lib/__tests__/l5DickieP4Acceptance.spec.ts"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=180,
            check=False,
        )
        assert verification.returncode == 0, verification.stdout + verification.stderr
        assert output_path.exists()

        consumed = client.post(
            f"/api/customer-price/internal-quote-artifacts/{handoff['id']}/consume",
            json={"consumer_reference": "L5.3-real-dickie-p4"},
        )
        assert consumed.status_code == 200, consumed.text
        duplicate = client.post(
            f"/api/customer-price/internal-quote-artifacts/{handoff['id']}/consume",
            json={"consumer_reference": "L5.3-duplicate"},
        )
        assert duplicate.status_code == 409

        report = {
            "phase": "L5.3",
            "source_file": baseline["source_path"],
            "source_sha256": hashlib.sha256(Path(baseline["source_path"]).read_bytes()).hexdigest(),
            "quote_no": "IQ-L5-3-DICKIE",
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
                "products": len(baseline["product_rows"]),
                "remarks": len(baseline["remark_lines"]),
                "material_prices": len(baseline["material_prices_hkd"]),
                "molds": len(baseline["mold_rows"]),
            },
            "mold_total_hkd": sum(row["mold_cost_hkd"] for row in baseline["mold_rows"]),
            "project_name_en": "Disney Cable Car Series",
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
