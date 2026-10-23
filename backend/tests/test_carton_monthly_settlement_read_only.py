from test_molding_sample_api import make_client, login_as
from test_carton_master_api import prepare

BASE = "/api/carton-procurement"


def test_monthly_settlement_workspace_is_read_only(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        login_as(client, "admin")
        workspace = client.get(BASE + "/monthly-settlements/workspace",
                               params={"factory_id": "huaxing", "period": "2026-10", "currency": "CNY"})
        assert workspace.status_code == 200, workspace.text
        body = workspace.json()
        assert body["read_only"] is True
        assert body["can_submit"] is False and body["can_lock"] is False
        assert "totals" in body and "lines" in body

        for action in ("submit", "lock", "unlock"):
            response = client.post(BASE + f"/monthly-settlements/{action}",
                                   json={"factory_id": "huaxing", "period": "2026-10", "currency": "CNY", "reason": "只读验证"})
            assert response.status_code == 410, (action, response.text)
