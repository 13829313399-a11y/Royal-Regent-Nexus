from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_document_translation_proxy_has_route_specific_half_hour_timeout():
    config = (REPOSITORY_ROOT / "nginx.prod.conf").read_text(encoding="utf-8")
    translation_start = config.index(
        "location ~ ^/api/tools/document-translation(?:/artifact)?$"
    )
    generic_api_start = config.index("location /api/")

    assert translation_start < generic_api_start
    translation_block = config[translation_start:generic_api_start]
    assert "proxy_send_timeout 1800s;" in translation_block
    assert "proxy_read_timeout 1800s;" in translation_block
