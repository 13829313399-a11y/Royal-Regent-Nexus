import importlib
from copy import deepcopy

import pytest
from sqlalchemy import select, func

from test_internal_quote_api import make_client, login, logout
from test_internal_quote_alternatives import create, fill, fork
from test_internal_quote_series_export import series, image_bytes


def body(client, quotes, kind="scenario", name="整组调价"):
    return {"kind": kind, "name": name, "change_note": "仅复制，产能及用量待工程确认",
            "products": [{"quote_id": q["id"], "revision": q["header_revision"],
                          "family_revision": client.get(f"/api/internal-quotes/{q['id']}/alternatives").json()["revision"]}
                         for q in quotes]}


def counts():
    dbm = importlib.import_module("app.db")
    models = importlib.import_module("app.models.internal_quote")
    with dbm.SessionLocal() as db:
        return tuple(db.scalar(select(func.count()).select_from(getattr(models, name))) for name in (
            "InternalQuote", "InternalQuoteAlternative", "InternalQuoteFamily", "InternalQuoteAttachment", "InternalQuoteAuditLog"))


def test_three_product_group_preserves_inputs_membership_and_issued_bytes(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "true")
    with make_client(monkeypatch) as client:
        login(client, "group-owner", "admin", "*", "*")
        quotes = [fill(client, q) for q in series(client, "GROUP-COPY")]
        quotes[1] = fork(client, quotes[1], "version")
        picture = client.post(f"/api/internal-quotes/{quotes[0]['id']}/product-image", data={"revision": quotes[0]["header_revision"]}, files={"file": ("part.png", image_bytes(), "image/png")})
        assert picture.status_code == 201, picture.text
        quotes[0] = client.get(f"/api/internal-quotes/{quotes[0]['id']}").json()
        issued = client.post(f"/api/internal-quotes/{quotes[0]['id']}/direct-issue", json={"revision": quotes[0]["header_revision"]})
        assert issued.status_code == 200, issued.text
        url = f"/api/internal-quotes/{quotes[0]['id']}/exports/{issued.json()['id']}/download"
        frozen = client.get(url).content
        quotes[0] = client.get(f"/api/internal-quotes/{quotes[0]['id']}").json()
        before = deepcopy(quotes)
        response = client.post(f"/api/internal-quotes/{quotes[0]['id']}/alternative-groups", json=body(client, quotes))
        assert response.status_code == 200, response.text
        result = response.json()
        assert len(result["quotes"]) == 3
        assert len({p["product_root_id"] for p in result["group"]["products"]}) == 3
        for source, copy in zip(before, result["quotes"]):
            assert copy["document_quote_id"] == source["document_quote_id"]
            assert copy["product_root_id"] == source["product_root_id"]
            assert copy["cloned_from_quote_id"] == source["id"]
            for s in source["sections"]:
                other = next(r for r in copy["sections"] if r["department"] == s["department"])
                assert other["payload"] == s["payload"]
            group = client.get(f"/api/internal-quotes/{copy['id']}/alternative-group")
            assert group.status_code == 200 and group.json() == result["group"]
            members = client.get(f"/api/internal-quotes/{copy['id']}/batch-products").json()
            assert [p["quote_id"] for p in members] == [q["id"] for q in result["quotes"]]
        attachments = client.get(f"/api/internal-quotes/{result['quotes'][0]['id']}/attachments").json()
        assert any(a["file_name"] == "part.png" and a["id"] != picture.json()["id"] for a in attachments)
        assert client.get(url).content == frozen
        # A second complete group makes new versions, still within the same document.
        second = client.post(f"/api/internal-quotes/{result['quotes'][0]['id']}/alternative-groups", json=body(client, result["quotes"], "version", ""))
        assert second.status_code == 200, second.text
        assert second.json()["group"]["group_id"] != result["group"]["group_id"]
        assert all(q["version_label"].endswith("V2") for q in second.json()["quotes"])
        leaf = second.json()["quotes"][2]
        removed = client.delete(f"/api/internal-quotes/{leaf['id']}", params={"revision": leaf["header_revision"]})
        assert removed.status_code == 204, removed.text
        members = client.get(f"/api/internal-quotes/{second.json()['quotes'][0]['id']}/batch-products").json()
        assert len(members) == 3 and "已删除" in members[2]["working_version_warning"]
        logout(client); login(client, "group-outsider", "sales_customer_supervisor", "sales-business", "huakang-a")
        denied = client.get(f"/api/internal-quotes/{result['quotes'][0]['id']}/alternative-group")
        assert denied.status_code == 403


@pytest.mark.parametrize("invalid", ["missing", "duplicate", "foreign_document", "stale_header", "stale_family", "archived"])
def test_group_rejects_invalid_selection_without_partial_copies(monkeypatch, invalid):
    with make_client(monkeypatch) as client:
        login(client, "group-invalid", "admin", "*", "*")
        quotes = series(client, "GROUP-INVALID")
        request = body(client, quotes)
        if invalid == "missing": request["products"].pop()
        if invalid == "duplicate": request["products"][2] = request["products"][0]
        if invalid == "foreign_document":
            other = create(client, "OUTSIDE-GROUP")
            request["products"][2] = body(client, [other])["products"][0]
        if invalid == "stale_header": request["products"][2]["revision"] += 1
        if invalid == "stale_family": request["products"][2]["family_revision"] += 1
        if invalid == "archived":
            archived = client.post(f"/api/internal-quotes/{quotes[2]['id']}/alternative-archive", json={"family_revision": 0, "archived": True, "reason": "停止使用"})
            assert archived.status_code == 200
            request["products"][2]["family_revision"] = archived.json()["revision"]
        previous = counts()
        response = client.post(f"/api/internal-quotes/{quotes[0]['id']}/alternative-groups", json=request)
        assert response.status_code in (400, 409), response.text
        assert counts() == previous


def test_late_copy_failure_rolls_back_all_group_members_and_family_updates(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "group-rollback", "admin", "*", "*")
        quotes = series(client, "GROUP-ROLLBACK")
        # Third family already has this name: first two must be rolled back too.
        fork(client, quotes[2], "scenario", "名称冲突")
        request = body(client, quotes, name="名称冲突")
        previous = counts()
        response = client.post(f"/api/internal-quotes/{quotes[0]['id']}/alternative-groups", json=request)
        assert response.status_code == 409, response.text
        assert counts() == previous
        assert client.get(f"/api/internal-quotes/{quotes[0]['id']}/alternatives").json()["revision"] == 0
