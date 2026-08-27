from pathlib import Path

import pytest
from app.core.config import Settings
from pydantic import ValidationError

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_document_tools_use_direct_runtime_settings() -> None:
    settings = Settings(_env_file=None)

    assert settings.document_tools_enabled is True
    assert settings.document_office_renderer_enabled is False
    assert settings.document_office_renderer_network_isolation_verified is False
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
        ("document_tool_max_file_bytes", 100 * 1024 * 1024 + 1),
        ("document_tool_max_pdf_pages", 201),
        ("document_office_renderer_command", "libreoffice --headless"),
        ("document_office_renderer_network_isolation_command", "unshare --net"),
    ],
)
def test_document_studio_setting_limits_are_closed(name: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})
