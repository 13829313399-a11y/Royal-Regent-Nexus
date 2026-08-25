from types import SimpleNamespace

from app.services.internal_quote_artifacts import internal_quote_export_file_name


def test_internal_quote_export_name_uses_quote_product_and_export_date():
    quote = SimpleNamespace(
        quote_no="IQ/20260820:001",
        product_name='灯光公仔 <大陆版> / "蓝色"',
    )

    assert internal_quote_export_file_name(quote, "2026-08-20 14:35:22") == (
        "IQ_20260820_001_灯光公仔 _大陆版_ _ _蓝色_2026-08-20.xlsx"
    )


def test_internal_quote_export_name_keeps_extension_and_date_with_long_product_name():
    quote = SimpleNamespace(
        quote_no="IQ-20260820-LONG",
        product_name="长产品名" * 100,
    )

    file_name = internal_quote_export_file_name(quote, "2026-08-20 14:35:22")

    assert len(file_name) <= 255
    assert file_name.endswith("_2026-08-20.xlsx")
