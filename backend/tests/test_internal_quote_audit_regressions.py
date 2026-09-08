import importlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from test_internal_quote_api import ALL_SECTION_CODES, create_payload, login, make_client
from test_internal_quote_p3_api import document_bytes, workbook_bytes_with_image
from test_internal_quote_whole_review import whole_review_payload


def import_mold(client, base, name):
    content = workbook_bytes_with_image([
        ["模号", "产品名称", "材质", "克重", "套数", "模价", "机型", "目标数"],
        [name, name, "ABS", 100, 1, 7750, "4A", 5000],
    ], "U2")
    preview = client.post(base + "/imports/mold/preview", files={"file": (name + ".xlsx", content)})
    assert preview.status_code == 201, preview.text
    batch = preview.json()
    confirmed = client.post(base + f"/imports/{batch['batch_id']}/confirm",
                            json={"revision": batch["target_revision"]})
    assert confirmed.status_code == 200, confirmed.text
    attachments = client.get(base + "/attachments?department=engineering").json()
    source = next(item for item in attachments if item["file_name"] == name + ".xlsx")
    return confirmed.json()["section"], source


def engineering(client, base):
    return next(row for row in client.get(base).json()["sections"] if row["department"] == "engineering")


def test_old_source_delete_preserves_new_import_and_manual_rows(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "audit_delete", "sales_customer_owner", "sales-business")
        created = client.post("/api/internal-quotes", json=create_payload(
            suffix="AUDIT-DELETE", participating_sections=ALL_SECTION_CODES)).json()
        base = f"/api/internal-quotes/{created['id']}"
        old_section, old_source = import_mold(client, base, "old")
        latest, new_source = import_mold(client, base, "new")
        payload = latest["payload"]
        manual = {**payload["molds"][0], "item": "manual"}
        manual.pop("import_batch_id", None)
        manual.pop("image_attachment_ids", None)
        payload["molds"].append(manual)
        saved = client.put(base + "/sections/engineering", json={"revision": latest["revision"], "payload": payload})
        assert saved.status_code == 200, saved.text
        before = engineering(client, base)
        deleted = client.delete(base + f"/attachments/{old_source['id']}", params={"revision": before["revision"]})
        assert deleted.status_code == 204, deleted.text
        after = engineering(client, base)
        assert after["payload"] == before["payload"]
        remaining_ids = {item["id"] for item in client.get(base + "/attachments").json()}
        old_images = set(old_section["payload"]["molds"][0]["image_attachment_ids"])
        new_images = set(latest["payload"]["molds"][0]["image_attachment_ids"])
        # Identical embedded images can be deduplicated across import batches.
        # Keep shared images while the latest rows still reference them.
        assert not (old_images - new_images).intersection(remaining_ids)
        assert new_images <= remaining_ids
        deleted = client.delete(base + f"/attachments/{new_source['id']}", params={"revision": after["revision"]})
        assert deleted.status_code == 204, deleted.text
        assert engineering(client, base)["payload"]["molds"] == [manual]


def test_supporting_attachment_delete_is_separate_and_rejects_referenced_images(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "audit_support", "sales_customer_owner", "sales-business")
        created = client.post("/api/internal-quotes", json=create_payload(suffix="AUDIT-SUPPORT")).json()
        base = f"/api/internal-quotes/{created['id']}"
        section, source = import_mold(client, base, "source")
        params = {"revision": section["revision"]}
        denied = client.delete(base + f"/attachments/{source['id']}/supporting", params=params)
        assert denied.status_code == 409, denied.text
        image_id = section["payload"]["molds"][0]["image_attachment_ids"][0]
        denied = client.delete(base + f"/attachments/{image_id}/supporting", params=params)
        assert denied.status_code == 409, denied.text
        uploaded = client.post(base + "/attachments", data={"department": "engineering"},
                               files={"file": ("note.docx", document_bytes(["supporting note"]),
                                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        assert uploaded.status_code == 201, uploaded.text
        attachment_id = uploaded.json()["id"]
        params = {"revision": engineering(client, base)["revision"]}
        assert client.delete(base + f"/attachments/{attachment_id}", params=params).status_code == 409
        assert client.delete(base + f"/attachments/{attachment_id}/supporting",
                             params={"revision": params["revision"] - 1}).status_code == 409
        deleted = client.delete(base + f"/attachments/{attachment_id}/supporting", params=params)
        assert deleted.status_code == 204, deleted.text
        assert client.get(base + f"/attachments/{attachment_id}/download").status_code == 404
        assert engineering(client, base)["revision"] == params["revision"] + 1


def test_baseline_copy_remaps_mold_images_to_target_attachments(monkeypatch):
    with make_client(monkeypatch) as client:
        owner = login(client, "audit_copy", "sales_customer_supervisor", "sales-business")
        payload = whole_review_payload("AUDIT-COPY", owner["id"], owner["display_name"])
        payload.update(quote_type="series", products=[
            {"product_name": "base", "qty": 5000, "region_code": ""},
            {"product_name": "target", "qty": 3000, "region_code": ""},
        ])
        root = client.post("/api/internal-quotes", json=payload).json()
        base = f"/api/internal-quotes/{root['id']}"
        products = client.get(base + "/batch-products").json()
        target_id = next(item["quote_id"] for item in products if item["quote_id"] != root["id"])
        section, _ = import_mold(client, base, "base-mold")
        target_base = f"/api/internal-quotes/{target_id}"
        revision = client.get(target_base).json()["header_revision"]
        copied = client.post(base + f"/batch-products/{target_id}/copy-baseline", json={"revision": revision})
        assert copied.status_code == 200, copied.text
        copied_ids = engineering(client, target_base)["payload"]["molds"][0]["image_attachment_ids"]
        assert copied_ids
        assert not set(copied_ids).intersection(section["payload"]["molds"][0]["image_attachment_ids"])
        for image_id in copied_ids:
            assert client.get(target_base + f"/attachments/{image_id}/download").status_code == 200


def test_concurrent_same_revision_saves_return_conflict_without_server_error(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "audit_concurrent", "sales_customer_owner", "sales-business")
        created = client.post("/api/internal-quotes", json=create_payload(suffix="AUDIT-CONCURRENT")).json()
        base = f"/api/internal-quotes/{created['id']}"
        service = importlib.import_module("app.services.internal_quote")
        original = service.lock_transaction
        barrier = Barrier(2)

        def synchronized_lock(*args, **kwargs):
            barrier.wait(timeout=10)
            return original(*args, **kwargs)

        monkeypatch.setattr(service, "lock_transaction", synchronized_lock)
        def save(name):
            return client.put(base + "/sections/engineering", json={
                "revision": 1, "payload": {"molds": [{"item": name}]},
            })
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(save, ["first", "second"]))
        assert sorted(response.status_code for response in responses) == [200, 409], [r.text for r in responses]
        assert engineering(client, base)["revision"] == 2


def test_delete_and_save_share_the_same_quote_transaction_lock(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "audit_delete_save", "sales_customer_owner", "sales-business")
        created = client.post("/api/internal-quotes", json=create_payload(suffix="AUDIT-DELETE-SAVE")).json()
        base = f"/api/internal-quotes/{created['id']}"
        section, source = import_mold(client, base, "concurrent-source")
        service = importlib.import_module("app.services.internal_quote")
        original = service.lock_transaction
        barrier = Barrier(2)

        def synchronized_lock(*args, **kwargs):
            barrier.wait(timeout=10)
            return original(*args, **kwargs)

        monkeypatch.setattr(service, "lock_transaction", synchronized_lock)
        def mutate(delete):
            if delete:
                return client.delete(base + f"/attachments/{source['id']}", params={"revision": section["revision"]})
            return client.put(base + "/sections/engineering", json={
                "revision": section["revision"], "payload": {"molds": [{"item": "new manual"}]},
            })
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(mutate, [False, True]))
        assert sorted(r.status_code for r in responses) in ([200, 409], [204, 409]), [r.text for r in responses]
        assert engineering(client, base)["revision"] == section["revision"] + 1


def test_scalar_import_ownership_preserves_newer_values_and_manual_edits():
    from types import SimpleNamespace
    import json
    service = importlib.import_module("app.services.internal_quote_artifacts")
    def batch(name, revision):
        return SimpleNamespace(id=name, confirmed_revision=revision, import_type="electronic",
                               preview_json=json.dumps({"payload_fragment": {"labor_rmb": "5", "components": []}}))
    older, newer = batch("older", 2), batch("newer", 3)
    current = {"labor_rmb": 5, "components": [{"item": "manual"}]}
    cleared, _ = service._clear_import_generated_payload(current, [older], all_batches=[older, newer])
    assert cleared == current
    cleared, _ = service._clear_import_generated_payload(current, [newer], all_batches=[older, newer])
    assert cleared == {"components": [{"item": "manual"}]}
    changed = {**current, "labor_rmb": 7}
    assert service._clear_import_generated_payload(changed, [newer], all_batches=[older, newer])[0] == changed
