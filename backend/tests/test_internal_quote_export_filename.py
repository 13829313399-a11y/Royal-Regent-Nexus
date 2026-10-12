from types import SimpleNamespace

import pytest

from app.services.internal_quote_artifacts import internal_quote_export_file_name


def test_internal_quote_export_name_uses_quote_product_and_export_date():
    quote = SimpleNamespace(
        quote_no="IQ/20260820:001",
        product_name='灯光公仔 <大陆版> / "蓝色"',
        module_version="v3",
    )

    assert internal_quote_export_file_name(quote, "2026-08-20 14:35:22") == (
        "IQ_20260820_001_灯光公仔 _大陆版_ _ _蓝色_2026-08-20.xlsx"
    )


def test_internal_quote_export_name_keeps_extension_and_date_with_long_product_name():
    quote = SimpleNamespace(
        quote_no="IQ-20260820-LONG",
        product_name="长产品名" * 100,
        module_version="v3",
    )

    file_name = internal_quote_export_file_name(quote, "2026-08-20 14:35:22")

    assert len(file_name) <= 255
    assert file_name.endswith("_2026-08-20.xlsx")


@pytest.mark.parametrize("version_label,expected", [("R2/正式", "R2_正式"), ("", "V1")])
def test_direct_issue_export_name_includes_cleaned_option_version(version_label, expected):
    quote = SimpleNamespace(
        quote_no="IQ-001", product_name="产品", module_version="v4",
        version_label=version_label,
    )

    assert internal_quote_export_file_name(quote, "2026-10-12 12:00:00") == (
        f"IQ-001_产品_{expected}_2026-10-12.xlsx"
    )
