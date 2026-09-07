from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_document_translation_proxy_has_route_specific_half_hour_timeout():
    config = (REPOSITORY_ROOT / "nginx.prod.conf").read_text(encoding="utf-8")
    translation_start = config.index(
        "location ~ ^/api/tools/(?:document-translation|pdf-translation)$"
    )
    generic_api_start = config.index("location /api/")

    assert translation_start < generic_api_start
    translation_block = config[translation_start:generic_api_start]
    assert "proxy_send_timeout 1800s;" in translation_block
    assert "proxy_read_timeout 1800s;" in translation_block


def test_customer_order_proxy_accepts_real_batches_and_long_running_excel_work():
    config = (REPOSITORY_ROOT / "nginx.prod.conf").read_text(encoding="utf-8")
    customer_order_start = config.index("location ~ ^/api/customer-orders/")
    generic_api_start = config.index("location /api/")
    customer_order_block = config[customer_order_start:generic_api_start]

    assert "client_max_body_size 128m;" in config
    assert customer_order_start < generic_api_start
    assert "proxy_send_timeout 600s;" in customer_order_block
    assert "proxy_read_timeout 600s;" in customer_order_block


def test_local_document_conversion_proxy_timeout_matches_browser_clients():
    config = (REPOSITORY_ROOT / "nginx.prod.conf").read_text(encoding="utf-8")
    conversion_start = config.index(
        "location ~ ^/api/tools/(?:pdf-to-excel|pdf-to-word|word-to-pdf|pdf-split)$"
    )
    generic_api_start = config.index("location /api/")

    assert conversion_start < generic_api_start
    conversion_block = config[conversion_start:generic_api_start]
    assert "proxy_send_timeout 900s;" in conversion_block
    assert "proxy_read_timeout 900s;" in conversion_block
