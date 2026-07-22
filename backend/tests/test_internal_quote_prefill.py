from app.services.internal_quote_prefill import prefill_molding_from_engineering


def test_engineering_molds_prefill_molding_and_keep_department_fields() -> None:
    engineering = {
        "molds": [
            {
                "mold_no": "M01",
                "chinese_name": "水桌主体",
                "material": "PP",
                "material_type": "7032 E3",
                "color": "Blue",
                "net_weight_g": "125.5",
                "cavity": "2",
                "quantity": "1",
                "machine_code": "20A",
                "target_output": "3000",
                "cycle_time_seconds": "45",
            },
            {
                "mold_no": "M02",
                "chinese_name": "顶桌面",
                "material": "ABS",
            },
        ]
    }
    molding = {
        "injection_loss_rate_percent": "3",
        "injection_lines": [
            {
                "mold_no": "M01",
                "machine_name": "200T",
                "quantity": "2",
                "remark": "啤机部补录",
            },
            {"item": "手工追加行", "machine_name": "80T", "quantity": "1"},
        ],
        "blow_lines": [{"item": "吹气件"}],
    }

    result = prefill_molding_from_engineering(engineering, molding)

    first, second, manual = result["injection_lines"]
    assert first["item"] == "水桌主体"
    assert first["mold_no"] == "M01"
    assert first["material"] == "PP"
    assert first["grade"] == "7032 E3"
    assert first["color"] == "Blue"
    assert first["net_weight_g"] == "125.5"
    assert first["cavity"] == "2"
    assert first["sets"] == "1"
    assert first["machine_code"] == "20A"
    assert first["target_output"] == "3000"
    assert first["cycle_time_seconds"] == "45"
    assert first["machine_name"] == "200T"
    assert first["quantity"] == "2"
    assert first["remark"] == "啤机部补录"
    assert set(first["engineering_synced_fields"]) == {
        "item", "mold_no", "material", "grade", "color", "net_weight_g",
        "cavity", "sets", "machine_code", "target_output", "cycle_time_seconds",
    }
    assert second["item"] == "顶桌面"
    assert second["mold_no"] == "M02"
    assert second["material"] == "ABS"
    assert second["machine_name"] == ""
    assert second["quantity"] == "1"
    assert manual["item"] == "手工追加行"
    assert result["blow_lines"] == [{"item": "吹气件"}]


def test_engineering_refresh_updates_owned_values_without_overwriting_molding_values() -> None:
    first = prefill_molding_from_engineering(
        {"molds": [{"mold_no": "M12", "chinese_name": "挂钩", "color": "Orange"}]},
        {"injection_lines": []},
    )
    first["injection_lines"][0]["machine_name"] = "160T"
    first["injection_lines"][0]["quantity"] = "3"

    refreshed = prefill_molding_from_engineering(
        {"molds": [{"mold_no": "M12", "chinese_name": "挂钩（改）", "color": "Blue"}]},
        first,
    )

    row = refreshed["injection_lines"][0]
    assert row["item"] == "挂钩（改）"
    assert row["color"] == "Blue"
    assert row["machine_name"] == "160T"
    assert row["quantity"] == "3"
    assert len(refreshed["injection_lines"]) == 1


def test_disney_mold_no_prefills_matching_molding_row() -> None:
    result = prefill_molding_from_engineering(
        {"molds": [{"mold_no": "M01", "chinese_name": "车面", "disney_mold_no": "D-M01"}]},
        {"injection_lines": []},
    )

    row = result["injection_lines"][0]
    assert row["disney_mold_no"] == "D-M01"
    assert "disney_mold_no" in row["engineering_synced_fields"]


def test_removed_engineering_mold_removes_only_projected_row() -> None:
    molding = prefill_molding_from_engineering(
        {"molds": [{"mold_no": "M01", "chinese_name": "工程行"}]},
        {"injection_lines": [{"item": "手工行"}]},
    )

    refreshed = prefill_molding_from_engineering({"molds": []}, molding)

    assert refreshed["injection_lines"] == [{"item": "手工行"}]


def test_generic_engineering_material_type_becomes_selectable_material_category() -> None:
    result = prefill_molding_from_engineering(
        {"molds": [{"mold_no": "M01", "chinese_name": "水桌主体", "material": "", "material_type": "pp"}]},
        {"injection_lines": []},
    )

    row = result["injection_lines"][0]
    assert row["material"] == "pp"
    assert row["grade"] == ""
    assert "material" in row["engineering_synced_fields"]
    assert "grade" not in row["engineering_synced_fields"]


def test_generic_engineering_material_keeps_saved_concrete_grade_after_refresh() -> None:
    engineering = {
        "molds": [
            {
                "mold_no": "M01",
                "chinese_name": "水桌主体",
                "material": "",
                "material_type": "PP",
            }
        ]
    }
    first = prefill_molding_from_engineering(engineering, {"injection_lines": []})
    first_row = first["injection_lines"][0]
    first_row["material"] = "1#PP"
    first_row["grade"] = "JM350/K8009"

    refreshed = prefill_molding_from_engineering(engineering, first)

    assert refreshed["injection_lines"][0]["material"] == "1#PP"
    assert refreshed["injection_lines"][0]["grade"] == "JM350/K8009"


def test_generic_engineering_material_change_clears_incompatible_saved_grade() -> None:
    existing = prefill_molding_from_engineering(
        {"molds": [{"mold_no": "M01", "material": "", "material_type": "PP"}]},
        {"injection_lines": []},
    )
    existing["injection_lines"][0]["material"] = "1#PP"
    existing["injection_lines"][0]["grade"] = "JM350/K8009"

    refreshed = prefill_molding_from_engineering(
        {"molds": [{"mold_no": "M01", "material": "", "material_type": "PVC"}]},
        existing,
    )

    assert refreshed["injection_lines"][0]["material"] == "PVC"
    assert refreshed["injection_lines"][0]["grade"] == ""


def test_generic_material_column_also_keeps_saved_concrete_grade() -> None:
    engineering = {"molds": [{"mold_no": "M01", "material": "PP", "material_type": ""}]}
    existing = prefill_molding_from_engineering(engineering, {"injection_lines": []})
    existing["injection_lines"][0]["material"] = "1#PP"
    existing["injection_lines"][0]["grade"] = "7032 E3"

    refreshed = prefill_molding_from_engineering(engineering, existing)

    assert refreshed["injection_lines"][0]["material"] == "1#PP"
    assert refreshed["injection_lines"][0]["grade"] == "7032 E3"


def test_compatible_generic_values_in_both_engineering_columns_keep_saved_grade() -> None:
    engineering = {
        "molds": [
            {
                "mold_no": "M01",
                "material": "1#PP",
                "material_type": "PP",
            }
        ]
    }
    existing = prefill_molding_from_engineering(engineering, {"injection_lines": []})
    existing["injection_lines"][0]["material"] = "1#PP"
    existing["injection_lines"][0]["grade"] = "JM350/K8009"

    refreshed = prefill_molding_from_engineering(engineering, existing)

    assert refreshed["injection_lines"][0]["material"] == "1#PP"
    assert refreshed["injection_lines"][0]["grade"] == "JM350/K8009"


def test_bare_engineering_a_code_preserves_matching_saved_baseline_selection() -> None:
    engineering = {"molds": [{"mold_no": "M01", "machine_code": "18"}]}
    existing = prefill_molding_from_engineering(engineering, {"injection_lines": []})
    assert existing["injection_lines"][0]["machine_code"] == "18A"

    existing["injection_lines"][0]["machine_code"] = "18A"
    existing["injection_lines"][0]["machine_name"] = "180T"
    refreshed = prefill_molding_from_engineering(engineering, existing)

    assert refreshed["injection_lines"][0]["machine_code"] == "18A"
    assert refreshed["injection_lines"][0]["machine_name"] == "180T"


def test_changed_engineering_a_code_replaces_incompatible_saved_selection() -> None:
    existing = prefill_molding_from_engineering(
        {"molds": [{"mold_no": "M01", "machine_code": "18"}]},
        {"injection_lines": []},
    )
    existing["injection_lines"][0]["machine_name"] = "180T"

    refreshed = prefill_molding_from_engineering(
        {"molds": [{"mold_no": "M01", "machine_code": "20"}]},
        existing,
    )

    assert refreshed["injection_lines"][0]["machine_code"] == "20A"
    assert refreshed["injection_lines"][0]["machine_name"] == ""
