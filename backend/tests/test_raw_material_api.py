import importlib
import sqlite3

import pytest

from test_molding_sample_api import login_as, make_client, make_client_with_database


def create_fixed_position_user(
    username: str,
    role_id: str,
    department: str,
    factory_id: str = "huaxing",
) -> None:
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    user_id = f"user-{username}"
    now = auth_service.now_text()
    with db_module.SessionLocal() as db:
        salt, password_hash = auth_service.make_password_hash("123456")
        db.add(
            auth_models.AuthUser(
                id=user_id,
                username=username,
                display_name=username,
                password_salt=salt,
                password_hash=password_hash,
                status="active",
                force_password_change=0,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            auth_models.AuthUserRole(
                id=f"{user_id}:{role_id}:{factory_id}:{department}",
                user_id=user_id,
                role_id=role_id,
                factory_id=factory_id,
                department=department,
            )
        )
        db.add(
            auth_models.EmployeeProfile(
                user_id=user_id,
                primary_factory_id=factory_id,
                primary_department=department,
                position=username,
                phone="",
                email="",
                confirmation_status="confirmed",
                source_registration_request_id="",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            auth_models.AuthUserAuthorizationRevision(
                user_id=user_id,
                revision=1,
                updated_at=now,
            )
        )
        db.commit()


def login_fixed_position_user(client, username: str):
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "123456"},
    )
    assert response.status_code == 200
    return response.json()


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
        assert {row["factory_id"] for row in baseline} == {"*"}
        assert baseline[0]["material_code"] == "91000001"
        assert baseline[0]["material_name"] == "ABS 750NSW"
        next_material_code = max(
            int(row["material_code"])
            for row in baseline
            if row["material_code"].isdecimal()
        ) + 1

        db_module = importlib.import_module("app.db")
        raw_material_service = importlib.import_module("app.services.raw_material")
        with db_module.SessionLocal() as db:
            assert raw_material_service.seed_raw_material_defaults(db) == 0

        payload = {
            "factory_id": "huaxing",
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
        assert created["material_code"] == f"{next_material_code:08d}"
        assert created["safety_stock_kg"] == 50
        assert created["unit_price_hkd_per_lb"] is None

        update_response = client.patch(
            f"/api/raw-materials/{created['id']}?factory_id=huaxing",
            json={
                "material_name": "工程更新 PP 料",
                "category": "PP",
                "spec": "高流动共聚 PP",
                "unit": "KG",
                "supplier": "华兴材料供应商",
                "safety_stock_kg": 60,
                "unit_price_hkd_per_lb": 6.25,
                "status": "启用",
                "notes": "工程部编辑并维护单价",
            },
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["material_code"] == created["material_code"]
        assert updated["material_name"] == "工程更新 PP 料"
        assert updated["unit_price_hkd_per_lb"] == 6.25
        assert updated["safety_stock_kg"] == 60

        listed_response = client.get("/api/raw-materials?factory_id=huaxing")
        assert listed_response.status_code == 200
        listed = listed_response.json()
        assert len(listed) == 287
        assert any(
            row["material_code"] == created["material_code"]
            and row["material_name"] == "工程更新 PP 料"
            and row["unit_price_hkd_per_lb"] == 6.25
            for row in listed
        )

        next_payload = {**payload, "material_name": "工程新增 PP 料（二）"}
        next_response = client.post("/api/raw-materials", json=next_payload)
        assert next_response.status_code == 201
        assert next_response.json()["material_code"] == f"{next_material_code + 1:08d}"


def test_raw_material_creation_is_scoped_to_engineering_and_warehouse(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "qa_inspector")
        forbidden = client.post("/api/raw-materials", json={
            "factory_id": "huaxing",
            "material_name": "QA 不应新增",
            "category": "ABS",
            "unit": "KG",
        })
        assert forbidden.status_code == 403

        client.post("/api/auth/logout")
        login_as(client, "engineer")
        baseline = client.get("/api/raw-materials?factory_id=huaxing").json()[0]
        client.post("/api/auth/logout")
        login_as(client, "qa_inspector")
        blocked_update = client.patch(
            f"/api/raw-materials/{baseline['id']}?factory_id=huaxing",
            json={
                "material_name": baseline["material_name"],
                "category": baseline["category"],
                "spec": baseline["spec"],
                "unit": baseline["unit"],
                "supplier": baseline["supplier"],
                "safety_stock_kg": baseline["safety_stock_kg"],
                "unit_price_hkd_per_lb": 9.99,
                "status": baseline["status"],
                "notes": baseline["notes"],
            },
        )
        assert blocked_update.status_code == 403

        client.post("/api/auth/logout")
        login_as(client, "warehouse_keeper")
        allowed = client.post("/api/raw-materials", json={
            "factory_id": "huaxing",
            "material_name": "仓管新增 ABS",
            "category": "ABS",
            "unit": "KG",
        })
        assert allowed.status_code == 201


def test_every_engineering_and_warehouse_fixed_position_can_manage_home_raw_materials(
    monkeypatch,
):
    fixed_positions = (
        ("fixed_engineer", "position_engineering_engineer", "engineering"),
        ("fixed_engineering_supervisor", "position_engineering_supervisor", "engineering"),
        ("fixed_engineering_manager", "position_engineering_manager", "engineering"),
        ("fixed_warehouse_keeper", "position_warehouse_keeper", "pmc-warehouse"),
        ("fixed_warehouse_supervisor", "position_warehouse_supervisor", "pmc-warehouse"),
        ("fixed_warehouse_manager", "position_warehouse_manager", "pmc-warehouse"),
    )

    with make_client(monkeypatch) as client:
        for username, role_id, department in fixed_positions:
            create_fixed_position_user(username, role_id, department)
            profile = login_fixed_position_user(client, username)
            assert "molding_sample:raw_material_write" in profile["permissions"]
            created = client.post(
                "/api/raw-materials",
                json={
                    "factory_id": "huaxing",
                    "material_name": f"{username} 新增原料",
                    "category": "ABS",
                    "unit": "KG",
                },
            )
            assert created.status_code == 201
            client.post("/api/auth/logout")

        login_fixed_position_user(client, "fixed_engineer")
        assert client.get(
            "/api/raw-materials",
            params={"factory_id": "huadeng"},
        ).status_code == 200
        assert client.post(
            "/api/raw-materials",
            json={
                "factory_id": "huadeng",
                "material_name": "工程师不得写入外厂原料",
                "category": "ABS",
                "unit": "KG",
            },
        ).status_code == 403
        client.post("/api/auth/logout")

        login_fixed_position_user(client, "fixed_warehouse_keeper")
        assert client.get(
            "/api/raw-materials",
            params={"factory_id": "huadeng"},
        ).status_code == 403


def test_shared_raw_material_created_in_c_can_be_read_and_updated_in_d(monkeypatch):
    with make_client(monkeypatch) as client:
        create_fixed_position_user(
            "fixed_engineer_c",
            "position_engineering_engineer",
            "engineering",
            factory_id="huakang-c",
        )
        create_fixed_position_user(
            "fixed_engineer_d",
            "position_engineering_engineer",
            "engineering",
            factory_id="huakang-d",
        )

        login_fixed_position_user(client, "fixed_engineer_c")
        created_response = client.post(
            "/api/raw-materials",
            json={
                "factory_id": "huakang-c",
                "material_name": "C 厂新增全厂共享 ABS",
                "category": "ABS",
                "spec": "共享规格",
                "unit": "KG",
                "supplier": "共享供应商",
                "safety_stock_kg": 25,
                "status": "启用",
                "notes": "由 C 厂创建",
            },
        )
        assert created_response.status_code == 201
        created = created_response.json()
        assert created["factory_id"] == "*"

        client.post("/api/auth/logout")
        login_fixed_position_user(client, "fixed_engineer_d")
        d_rows_response = client.get(
            "/api/raw-materials",
            params={"factory_id": "huakang-d"},
        )
        assert d_rows_response.status_code == 200
        assert any(row["id"] == created["id"] for row in d_rows_response.json())

        updated_response = client.patch(
            f"/api/raw-materials/{created['id']}",
            params={"factory_id": "huakang-d"},
            json={
                "material_name": "D 厂更新后的全厂共享 ABS",
                "category": "ABS",
                "spec": "共享规格 v2",
                "unit": "KG",
                "supplier": "共享供应商",
                "safety_stock_kg": 30,
                "status": "启用",
                "notes": "由 D 厂更新",
            },
        )
        assert updated_response.status_code == 200
        assert updated_response.json()["factory_id"] == "*"

        client.post("/api/auth/logout")
        login_fixed_position_user(client, "fixed_engineer_c")
        c_rows_response = client.get(
            "/api/raw-materials",
            params={"factory_id": "huakang-c"},
        )
        assert c_rows_response.status_code == 200
        shared_row = next(row for row in c_rows_response.json() if row["id"] == created["id"])
        assert shared_row["material_name"] == "D 厂更新后的全厂共享 ABS"
        assert shared_row["safety_stock_kg"] == 30


def test_raw_material_factory_context_accepts_only_entity_factories(monkeypatch):
    valid_factory_ids = (
        "huakang-a",
        "huakang-b",
        "huakang-c",
        "huakang-d",
        "huadeng",
        "huaxing",
    )
    invalid_factory_ids = ("group", "*", "fake-factory")

    with make_client(monkeypatch) as client:
        login_as(client, "admin")

        for factory_id in valid_factory_ids:
            response = client.get(
                "/api/raw-materials",
                params={"factory_id": factory_id},
            )
            assert response.status_code == 200

        baseline = client.get(
            "/api/raw-materials",
            params={"factory_id": "huaxing"},
        ).json()[0]
        update_payload = {
            "material_name": baseline["material_name"],
            "category": baseline["category"],
            "spec": baseline["spec"],
            "unit": baseline["unit"],
            "supplier": baseline["supplier"],
            "safety_stock_kg": baseline["safety_stock_kg"],
            "status": baseline["status"],
            "notes": baseline["notes"],
        }

        for factory_id in invalid_factory_ids:
            get_response = client.get(
                "/api/raw-materials",
                params={"factory_id": factory_id},
            )
            assert get_response.status_code == 422

            post_response = client.post(
                "/api/raw-materials",
                json={
                    "factory_id": factory_id,
                    "material_name": "非法厂区原料",
                    "category": "ABS",
                    "unit": "KG",
                },
            )
            assert post_response.status_code == 422

            patch_response = client.patch(
                f"/api/raw-materials/{baseline['id']}",
                params={"factory_id": factory_id},
                json=update_payload,
            )
            assert patch_response.status_code == 422


def test_startup_refuses_legacy_factory_raw_materials_before_shared_seed(
    monkeypatch,
    tmp_path,
):
    database_path = tmp_path / "legacy_raw_materials.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE raw_materials (
                id VARCHAR(64) NOT NULL PRIMARY KEY,
                factory_id VARCHAR(64) NOT NULL,
                material_code VARCHAR(128) NOT NULL,
                material_name VARCHAR(255) NOT NULL,
                category VARCHAR(128) NOT NULL,
                spec VARCHAR(255) NOT NULL,
                unit VARCHAR(64) NOT NULL,
                supplier VARCHAR(255) NOT NULL,
                safety_stock_kg FLOAT,
                status VARCHAR(16) NOT NULL,
                notes TEXT NOT NULL,
                created_by VARCHAR(64) NOT NULL,
                created_at VARCHAR(32) NOT NULL,
                updated_at VARCHAR(32) NOT NULL,
                CONSTRAINT uq_raw_materials_factory_code
                    UNIQUE (factory_id, material_code)
            );
            INSERT INTO raw_materials (
                id, factory_id, material_code, material_name, category, spec,
                unit, supplier, safety_stock_kg, status, notes,
                created_by, created_at, updated_at
            ) VALUES (
                'RM-LEGACY-HX-001', 'huaxing', '91000001', '旧厂区 ABS',
                'ABS', '', 'KG', '', NULL, '启用', '', 'legacy',
                '2026-07-14 08:00:00', '2026-07-14 08:00:00'
            );
            """
        )
        connection.commit()

    with pytest.raises(RuntimeError, match="20260720_0027"):
        with make_client_with_database(monkeypatch, database_path):
            pass

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT id, factory_id, material_code FROM raw_materials ORDER BY id"
        ).fetchall()
    assert rows == [("RM-LEGACY-HX-001", "huaxing", "91000001")]
