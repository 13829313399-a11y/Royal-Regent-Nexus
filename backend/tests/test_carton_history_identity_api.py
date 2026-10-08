from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from test_molding_sample_api import login_as, make_client
from test_carton_procurement_api import _freeze_carton_time, _history_workbook_bytes


BASE = "/api/carton-procurement"


def _customer(client, name, factory="huaxing"):
    response = client.post(f"{BASE}/customers", json={
        "factory_id": factory, "customer_code": name.upper(), "customer_name": name,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _row(customer, *, order_no="", packaging="外箱"):
    return [order_no, "SC700145365", customer, "203302044", "历史产品", 100,
            "2025-08-05", "2025-08-12", "历史补录", packaging, "A33+B",
            "30 × 20 × 10", "cm", 10, "个", 2, "CNY", "历史合同", "", None]


def _upload(client, rows, *, factory="huaxing", filename="history.xlsx"):
    response = client.post(f"{BASE}/orders/history-imports",
        params={"factory_id": factory},
        files={"file": (filename, _history_workbook_bytes(rows),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert response.status_code == 201, response.text
    return response.json()


def _orders(client, factory="huaxing"):
    response = client.get(f"{BASE}/orders", params={"factory_id": factory})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_different_files_keep_customer_identity_and_same_customer_retries_skip(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        for name in ("Alpha", "Beta"):
            _customer(client, name)
            result = _upload(client, [_row(name)], filename=f"{name}.xlsx")
            assert result["imported_count"] == 1
            assert result["skipped_count"] == 0
        # The canonical customer code still identifies a retry with case/space variations.
        retry = _upload(client, [_row("  ALPHA  ", order_no="HIST-RETRY")])
        assert retry["imported_count"] == 0
        assert retry["skipped_count"] == 1
        orders = _orders(client)
        assert len(orders) == 2
        assert {order["customer_code"] for order in orders} == {"ALPHA", "BETA"}
        assert all(len(order["lines"]) == 1 for order in orders)


@pytest.mark.parametrize("explicit_numbers", [False, True])
def test_one_workbook_groups_and_deduplicates_by_customer(monkeypatch, explicit_numbers):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        for name in ("Alpha", "Beta"):
            _customer(client, name)
        rows = [_row(name, order_no=f"HIST-{name}" if explicit_numbers else "", packaging=paper)
                for name in ("Alpha", "Beta") for paper in ("外箱", "内箱")]
        result = _upload(client, rows)
        assert result["group_count"] == 2
        assert result["imported_count"] == 2
        assert result["imported_line_count"] == 4
        orders = _orders(client)
        assert {order["customer_code"] for order in orders} == {"ALPHA", "BETA"}
        assert all(len(order["lines"]) == 2 for order in orders)
        repeat = _upload(client, rows)
        assert repeat["imported_count"] == 0
        assert repeat["skipped_count"] == 2
        assert len(_orders(client)) == 2


def test_same_customer_staged_duplicate_skips_and_factories_remain_independent(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        for factory in ("huaxing", "huadeng"):
            _customer(client, "Alpha", factory)
            result = _upload(client, [_row("Alpha", order_no="HIST-ONE"),
                                     _row("Alpha", order_no="HIST-TWO")], factory=factory)
            assert result["group_count"] == 2
            assert result["imported_count"] == 1
            assert result["skipped_count"] == 1
        left, right = _orders(client), _orders(client, "huadeng")
        assert len(left) == len(right) == 1
        assert left[0]["id"] != right[0]["id"]
        assert left[0]["factory_id"] == "huaxing"
        assert right[0]["factory_id"] == "huadeng"


def test_concurrent_history_retries_create_only_one_order(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        _customer(client, "Alpha")
        barrier = Barrier(2)
        content = _history_workbook_bytes([_row("Alpha")])

        def send():
            barrier.wait(timeout=10)
            return client.post(f"{BASE}/orders/history-imports", params={"factory_id": "huaxing"},
                files={"file": ("history.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(send) for _ in range(2)]
            responses = [future.result(timeout=30) for future in futures]
        assert any(response.status_code == 201 for response in responses)
        assert all(response.status_code in {201, 429} for response in responses)
        # The bounded file worker may decline the overlapping request. Retrying
        # the same bytes after the winner finishes must still have no new effect.
        assert len(_orders(client)) == 1
        results = []
        for response in responses:
            if response.status_code == 429:
                assert "正在处理" in response.text
                response = send_retry = client.post(f"{BASE}/orders/history-imports", params={"factory_id": "huaxing"},
                    files={"file": ("history.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
                assert send_retry.status_code == 201, send_retry.text
            results.append(response.json())
        assert sorted(result["imported_count"] for result in results) == [0, 1]
        assert sorted(result["skipped_count"] for result in results) == [0, 1]
        assert len(_orders(client)) == 1
