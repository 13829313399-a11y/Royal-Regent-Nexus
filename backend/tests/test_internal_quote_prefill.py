from app.services.internal_quote_prefill import prefill_molding_from_engineering


def test_child_parts_remain_descriptive_with_whole_mold_cost_and_department_inputs():
    mold = {"mold_no": "M1", "item": "上壳/下壳", "material": "ABS", "net_weight_g": 100, "quantity": 2}
    original = prefill_molding_from_engineering({"molds": [mold]}, {"injection_lines": []})
    original["injection_lines"][0].update(grade="750SW", machine_code="18A", target_output=3000, remark="已选机台")
    mold["parts"] = [
        {"name": "上壳", "color": "红", "unit_net_weight_g": 12, "output_count": 4, "quantity": 2},
        {"name": "下壳", "unit_net_weight_g": 0, "output_count": 2, "quantity": 1},
    ]
    engineering = {"molds": [mold]}
    # Dependency invalidation must retain the old parent until projection can inherit it.
    cleaned = prefill_molding_from_engineering(engineering, original, remove_missing_only=True)
    result = prefill_molding_from_engineering(engineering, cleaned)
    parent, = result["injection_lines"]
    assert (parent["item"], parent["net_weight_g"], parent["sets"], parent["quantity"]) == ("上壳/下壳", 100, 2, "1")
    assert (parent["grade"], parent["machine_code"], parent["remark"]) == ("750SW", "18A", "已选机台")
    assert parent["engineering_parts"] == mold["parts"]
    assert parent["cost_scope"] == "whole_mold"
    mold["parts"].reverse()
    refreshed = prefill_molding_from_engineering(engineering, result)
    assert refreshed["injection_lines"][0]["engineering_parts"] == mold["parts"]
    assert refreshed["injection_lines"][0]["remark"] == "已选机台"
    assert prefill_molding_from_engineering(engineering, refreshed) == refreshed
    mold["parts"].pop()
    refreshed["injection_lines"].append({"item": "手工件"})
    remaining = prefill_molding_from_engineering(engineering, refreshed, remove_missing_only=True)
    assert [r["item"] for r in remaining["injection_lines"]] == ["上壳/下壳", "手工件"]
    removed = prefill_molding_from_engineering({"molds": []}, remaining, remove_missing_only=True)
    assert removed["injection_lines"][0]["engineering_source_missing"] is True
    assert removed["injection_lines"][0]["remark"] == "已选机台"
    assert removed["injection_lines"][1] == {"item": "手工件"}


def test_same_named_children_in_distinct_molds_never_exchange_inputs():
    engineering = {"molds": [{"mold_no": number, "parts": [{"name": "上壳"}, {"name": "下壳"}]} for number in ("1", "2")]}
    first = prefill_molding_from_engineering(engineering, {})
    for index, row in enumerate(first["injection_lines"]):
        row["remark"] = index
    engineering["molds"].reverse()
    result = prefill_molding_from_engineering(engineering, first)
    assert [r["remark"] for r in result["injection_lines"]] == [1, 0]


def test_detached_parent_remains_explicitly_manual_after_engineering_split():
    engineering = {"molds": [{"mold_no": "1", "item": "上/下"}]}
    first = prefill_molding_from_engineering(engineering, {})
    first["injection_lines"][0].update(engineering_sync_disabled=True, item="手工拆分")
    engineering["molds"][0]["parts"] = [{"name": "上"}, {"name": "下"}]
    result = prefill_molding_from_engineering(engineering, first)
    assert [r["item"] for r in result["injection_lines"]] == ["手工拆分"]


def test_child_rename_preserves_saved_molding_data_and_legacy_child_keys_upgrade():
    part = {"name": "上壳"}
    engineering = {"molds": [{"mold_no": "1", "parts": [part]}]}
    first = prefill_molding_from_engineering(engineering, {})
    first["injection_lines"][0].update(grade="750SW", machine_code="18A", remark="保留")
    part["id"] = "stable-child-id"
    upgraded = prefill_molding_from_engineering(engineering, first)
    assert upgraded["injection_lines"][0]["remark"] == "保留"
    part["name"] = "上壳改名"
    cleaned = prefill_molding_from_engineering(engineering, upgraded, remove_missing_only=True)
    result = prefill_molding_from_engineering(engineering, cleaned)
    assert result["injection_lines"][0]["engineering_parts"][0]["name"] == "上壳改名"
    assert result["injection_lines"][0]["remark"] == "保留"


def test_legacy_unlinked_parent_is_consumed_once_with_descriptive_children():
    engineering = {"molds": [{"mold_no": "1", "item": "上/下", "parts": [{"name": "上"}, {"name": "下"}]}]}
    original = {"injection_lines": [{"mold_no": "1", "item": "上/下", "remark": "已填", "machine_code": "18A"}, {"item": "手工"}]}
    result = prefill_molding_from_engineering(engineering, original)
    assert [row["item"] for row in result["injection_lines"]] == ["上/下", "手工"]
    assert result["injection_lines"][0]["remark"] == "已填"
    assert len(result["injection_lines"][0]["engineering_parts"]) == 2


def test_legacy_child_can_be_renamed_on_first_save_without_losing_department_inputs():
    engineering = {"molds": [{"mold_no": "1", "parts": [{"name": "上壳"}]}]}
    original = prefill_molding_from_engineering(engineering, {})
    original['injection_lines'][0]['remark'] = '旧备注'
    engineering['molds'][0]['parts'] = [{'id': 'legacy-name:["上壳",1]', 'name': '改名上壳'}]
    cleaned = prefill_molding_from_engineering(engineering, original, remove_missing_only=True)
    result = prefill_molding_from_engineering(engineering, cleaned)
    assert result['injection_lines'][0]['engineering_parts'][0]['name'] == '改名上壳'
    assert result['injection_lines'][0]['remark'] == '旧备注'
def test_detached_stable_identity_preserves_all_local_metadata_and_ignores_deleted_source():
    detached = {"line_id": "kept", "engineering_source_key": "legacy-key", "engineering_mold_id": "m1", "engineering_sync_disabled": True, "engineering_synced_fields": [], "engineering_parts": [], "item": "独立", "net_weight_g": 77}
    engineering = {"molds": [{"mold_id": "m1", "mold_no": "renamed", "item": "新名", "net_weight_g": 999, "parts": [{"name": "新部件"}]}]}
    refreshed = prefill_molding_from_engineering(engineering, {"injection_lines": [detached]})
    assert refreshed["injection_lines"] == [detached]
    refreshed["injection_lines"][0]["engineering_source_missing"] = True
    removed = prefill_molding_from_engineering({"molds": []}, refreshed)
    assert removed["injection_lines"] == [detached]


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


def test_split_engineering_row_stays_editable_without_creating_a_third_projection() -> None:
    engineering = {"molds": [{"mold_no": "M12", "chinese_name": "挂钩", "color": "Orange"}]}
    first = prefill_molding_from_engineering(engineering, {"injection_lines": []})
    original = first["injection_lines"][0]
    original["engineering_sync_disabled"] = True
    original["engineering_synced_fields"] = []
    original["item"] = "挂钩左件"
    original["mold_no"] = "M12-A"
    clone = {
        **original,
        "engineering_source_key": "",
        "engineering_sync_disabled": True,
        "engineering_synced_fields": [],
        "item": "挂钩右件",
        "mold_no": "M12-B",
    }
    first["injection_lines"].append(clone)

    refreshed = prefill_molding_from_engineering(
        {"molds": [{"mold_no": "M12", "chinese_name": "工程名称已改变", "color": "Blue"}]},
        first,
    )

    assert len(refreshed["injection_lines"]) == 2
    assert refreshed["injection_lines"][0]["item"] == "挂钩左件"
    assert refreshed["injection_lines"][0]["mold_no"] == "M12-A"
    assert refreshed["injection_lines"][0]["engineering_synced_fields"] == []
    assert refreshed["injection_lines"][1]["item"] == "挂钩右件"
    assert refreshed["injection_lines"][1]["mold_no"] == "M12-B"


def test_disney_mold_no_prefills_matching_molding_row() -> None:
    result = prefill_molding_from_engineering(
        {"molds": [{"mold_no": "M01", "chinese_name": "车面", "disney_mold_no": "D-M01"}]},
        {"injection_lines": []},
    )

    row = result["injection_lines"][0]
    assert row["disney_mold_no"] == "D-M01"
    assert "disney_mold_no" in row["engineering_synced_fields"]


def test_removed_engineering_mold_retains_projected_row_for_explicit_resolution() -> None:
    molding = prefill_molding_from_engineering(
        {"molds": [{"mold_no": "M01", "chinese_name": "工程行"}]},
        {"injection_lines": [{"item": "手工行"}]},
    )

    refreshed = prefill_molding_from_engineering({"molds": []}, molding)

    assert refreshed["injection_lines"][0]["engineering_source_missing"] is True
    assert refreshed["injection_lines"][1] == {"item": "手工行"}


def test_deletion_only_sync_preserves_inputs_order_and_does_not_add_new_sources() -> None:
    molding = prefill_molding_from_engineering(
        {"molds": [{"mold_no": "M01", "item": "保留"}, {"mold_no": "M02", "item": "删除"}]},
        {"injection_lines": []},
    )
    surviving, removed = molding["injection_lines"]
    surviving.update({"material": "ABS", "grade": "750SW", "quantity": 7})
    manual = {"item": "手工行", "engineering_sync_disabled": True}
    molding["injection_lines"] = [manual, surviving, removed]
    result = prefill_molding_from_engineering(
        {"molds": [{"mold_no": "M01", "item": "保留", "quantity": 2}, {"mold_no": "M03", "item": "新增"}]},
        molding, remove_missing_only=True,
    )
    assert result["injection_lines"] == [manual, surviving, {**removed, "engineering_source_missing": True}]
    assert len(molding["injection_lines"]) == 3


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
