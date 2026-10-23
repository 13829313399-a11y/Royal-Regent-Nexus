from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from test_molding_sample_api import make_client, login_as
from test_carton_opening_preview_api import setup, upload, balances
from test_carton_opening_preview import workbook

BASE = "/api/carton-procurement/inventory/history-imports/batches"


def test_batch_reversal_reimport_replay_and_factory_permission_boundaries(monkeypatch):
    with make_client(monkeypatch) as client:
        assert client.get(BASE, params={"factory_id": "huaxing"}).status_code == 401
        setup(client, monkeypatch)
        rows = [["PO", "I", "A33外箱", 30, 20, 15, "A1", 10, 2],
                ["PO", "I", "A33外箱", 30, 20, 15, "A1", 12, None]]
        content = workbook(rows)
        checked = upload(client, content).json()
        posted = upload(client, content, preview=False, token=checked["source_fingerprint"])
        assert posted.status_code == 201, posted.text
        batch = client.get(BASE, params={"factory_id": "huaxing"}).json()["items"][0]
        batch_id = batch["batch_id"]
        path = f"{BASE}/{batch_id}"
        assert client.post(path + "/reversal-preview", params={"factory_id": "huakang-b"}).status_code == 404
        preview = client.post(path + "/reversal-preview", params={"factory_id": "huaxing"})
        assert preview.status_code == 200 and preview.json()["errors"] == [], preview.text
        payload = {"factory_id": "huaxing", "request_id": str(uuid4()), "reason": "整批导错，撤销后重导",
                   "expected_fingerprint": preview.json()["source_fingerprint"]}
        login_as(client, "qc_inspector")
        assert client.get(BASE, params={"factory_id": "huaxing"}).status_code == 403
        assert client.post(path + "/reversal-preview", params={"factory_id": "huaxing"}).status_code == 403
        assert client.post(path + "/reverse", json=payload).status_code == 403
        login_as(client, "admin")
        rejected = client.post(path + "/reverse", json={**payload, "reason": ""})
        assert rejected.status_code == 422
        barrier = Barrier(2)
        def confirm():
            barrier.wait(timeout=10)
            return client.post(path + "/reverse", json=payload)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [future.result(timeout=30) for future in [pool.submit(confirm), pool.submit(confirm)]]
        assert all(response.status_code == 200 for response in responses), [response.text for response in responses]
        assert sorted(response.json()["duplicate"] for response in responses) == [False, True]
        assert all(response.json()["reversed_count"] == 2 for response in responses)
        assert all(Decimal(row["balance"]) == 0 for row in balances(client))
        assert client.post(path + "/reverse", json=payload).json()["duplicate"]
        audit = client.get("/api/carton-procurement/audit-events", params={"factory_id": "huaxing"}).json()
        cancellation = next(event for event in audit["items"] if event["event_type"] == "HISTORY_INVENTORY_BATCH_REVERSED")
        assert "request" not in cancellation["detail"]

        # Corrected quantities can be posted as a fresh batch without deleting history.
        rows[1][7] = 15
        corrected = workbook(rows)
        new_preview = upload(client, corrected).json()
        assert new_preview["errors"] == [], new_preview
        second = upload(client, corrected, preview=False, token=new_preview["source_fingerprint"])
        assert second.status_code == 201 and second.json()["imported_count"] == 2, second.text
        assert set(second.json()["movement_ids"]).isdisjoint(posted.json()["movement_ids"])
        assert Decimal(balances(client)[0]["balance"]) == 25
        assert client.post(path + "/reverse", json=payload).json()["duplicate"]
        assert Decimal(balances(client)[0]["balance"]) == 25
        listed = client.get(BASE, params={"factory_id": "huaxing"}).json()
        assert listed["total"] == 2 and {row["status"] for row in listed["items"]} == {"ACTIVE", "REVERSED"}
        new_batch = next(row for row in listed["items"] if row["status"] == "ACTIVE")
        new_path = f"{BASE}/{new_batch['batch_id']}"
        next_preview = client.post(new_path + "/reversal-preview", params={"factory_id": "huaxing"}).json()
        assert next_preview["errors"] == [], next_preview
        next_payload = {**payload, "request_id": str(uuid4()), "expected_fingerprint": next_preview["source_fingerprint"]}
        assert client.post(new_path + "/reverse", json=next_payload).status_code == 200
        # Even the byte-identical file may be reimported after its batch was cancelled.
        exact = upload(client, corrected).json()
        assert exact["errors"] == []
        final = upload(client, corrected, preview=False, token=exact["source_fingerprint"])
        assert final.status_code == 201 and final.json()["imported_count"] == 2, final.text
        assert Decimal(balances(client)[0]["balance"]) == 25
