import importlib

from test_molding_sample_api import login_as, make_client


def test_engineer_can_create_and_read_persistent_raw_materials(monkeypatch):
    with make_client(monkeypatch) as client:
        unauthenticated = client.get("/api/raw-materials?factory_id=huaxing")
        assert unauthenticated.status_code == 401

        profile = login_as(client, "engineer")
        assert "molding_sample:raw_material_write" in profile["permissions"]

        baseline_response = client.get("/api/raw-materials?factory_id=huaxing")
        assert baseline_response.status_code == 200
        baseline = baseline_response.json()
        assert len(baseline) == 286
        assert baseline[0]["material_code"] == "91000001"
        assert baseline[0]["material_name"] == "ABS 750NSW"

        db_module = importlib.import_module("app.db")
        raw_material_service = importlib.import_module("app.services.raw_material")
        with db_module.SessionLocal() as db:
            assert raw_material_service.seed_raw_material_defaults(db) == 0

        payload = {
            "factory_id": "huaxing",
            "material_code": "RM-ENG-001",
            "material_name": "工程新增 PP 料",
            "category": "PP",
            "spec": "共聚 PP",
            "unit": "KG",
            "supplier": "华兴材料供应商",
            "safety_stock_kg": 50,
            "status": "启用",
            "notes": "工程部新增测试资料",
        }
        created_response = client.post("/api/raw-materials", json=payload)
        assert created_response.status_code == 201
        created = created_response.json()
        assert created["id"].startswith("RM-")
        assert created["created_by"] == "user-engineer"
        assert created["material_code"] == payload["material_code"]
        assert created["safety_stock_kg"] == 50

        listed_response = client.get("/api/raw-materials?factory_id=huaxing")
        assert listed_response.status_code == 200
        listed = listed_response.json()
        assert len(listed) == 287
        assert any(row["material_code"] == "RM-ENG-001" for row in listed)

        duplicate_response = client.post("/api/raw-materials", json=payload)
        assert duplicate_response.status_code == 409
        assert duplicate_response.json()["detail"] == "当前厂区已存在相同物料编号"


def test_raw_material_creation_is_scoped_to_engineering_and_warehouse(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "qa_inspector")
        forbidden = client.post("/api/raw-materials", json={
            "factory_id": "huaxing",
            "material_code": "RM-QA-001",
            "material_name": "QA 不应新增",
            "category": "ABS",
            "unit": "KG",
        })
        assert forbidden.status_code == 403

        client.post("/api/auth/logout")
        login_as(client, "warehouse_keeper")
        allowed = client.post("/api/raw-materials", json={
            "factory_id": "huaxing",
            "material_code": "RM-WH-001",
            "material_name": "仓管新增 ABS",
            "category": "ABS",
            "unit": "KG",
        })
        assert allowed.status_code == 201
