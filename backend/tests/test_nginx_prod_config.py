from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_customer_order_proxy_accepts_real_batches_and_long_running_excel_work():
    config = (REPOSITORY_ROOT / "nginx.prod.conf").read_text(encoding="utf-8")
    customer_order_start = config.index("location ~ ^/api/customer-orders/")
    generic_api_start = config.index("location /api/")
    customer_order_block = config[customer_order_start:generic_api_start]

    assert "client_max_body_size 128m;" in config
    assert customer_order_start < generic_api_start
    assert "proxy_send_timeout 600s;" in customer_order_block
    assert "proxy_read_timeout 600s;" in customer_order_block


def test_pdf_rename_has_scoped_long_timeout_and_batch_upload_budget():
    config = (REPOSITORY_ROOT / "nginx.prod.conf").read_text(encoding="utf-8")
    start = config.index("location ~ ^/api/tools/pdf-rename/(?:preview|execute)$")
    generic = config.index("location /api/")
    block = config[start:generic]
    assert start < generic
    assert "client_max_body_size 205m;" in block
    assert "proxy_send_timeout 900s;" in block
    assert "proxy_read_timeout 900s;" in block
    assert "proxy_read_timeout 30s;" in config[generic:]
