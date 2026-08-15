from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_document_studio_flags_are_default_off() -> None:
    settings = Settings(_env_file=None)

    assert settings.ai_document_studio_enabled is False
    assert settings.ai_document_cloud_ocr_enabled is False
    assert settings.ai_document_reconcile_enabled is False
    assert settings.ai_document_reconcile_model == "qwen3.7-plus"
    assert settings.document_office_renderer_enabled is False
    assert settings.document_office_renderer_network_isolation_verified is False
    assert settings.ai_document_ocr_model == "qwen3.5-ocr"
    assert settings.ai_document_ocr_region == "cn-beijing"
    assert settings.ai_document_ocr_max_pages == 50
    assert settings.ai_document_ocr_max_bytes == 20 * 1024 * 1024
    assert settings.ai_document_ocr_max_concurrency == 2
    assert settings.ai_document_signed_url_ttl_seconds == 300
    assert settings.document_office_renderer_command == "libreoffice"


def test_backend_image_contains_local_document_conversion_dependencies() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile.backend").read_text(encoding="utf-8")

    for package in (
        "libreoffice-writer",
        "fonts-noto-cjk",
        "tesseract-ocr-eng",
        "tesseract-ocr-chi-sim",
        "tesseract-ocr-chi-tra",
    ):
        assert package in dockerfile


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ai_document_ocr_max_pages", 51),
        ("ai_document_ocr_max_bytes", 20 * 1024 * 1024 + 1),
        ("ai_document_ocr_max_concurrency", 5),
        ("ai_document_signed_url_ttl_seconds", 601),
        ("document_office_renderer_command", "libreoffice --headless"),
        ("document_office_renderer_network_isolation_command", "unshare --net"),
    ],
)
def test_document_studio_setting_limits_are_closed(name: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})
