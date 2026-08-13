import base64
import io
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from app.schemas.ai.attachment import (
    AICloudProcessingConsent,
    AIImageAttachmentInput,
)
from app.schemas.ai.chat import AIChatRequest
from app.services.ai import attachment_service
from app.services.ai.attachment_service import (
    AIAttachmentErrorCode,
    AIAttachmentValidationError,
    clear_prepared_attachments,
    prepare_image_attachments,
)
from app.services.ai.providers.base import ProviderImageContent
from PIL import Image
from pydantic import ValidationError

_MIME_BY_FORMAT = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}


def _synthetic_image(
    image_format: str = "PNG",
    *,
    size: tuple[int, int] = (8, 6),
    exif: Image.Exif | None = None,
) -> tuple[bytes, str]:
    image = Image.new("RGB", size, color=(17, 83, 149))
    output = io.BytesIO()
    save_kwargs = {"exif": exif} if exif is not None else {}
    try:
        image.save(output, format=image_format, **save_kwargs)
        raw = output.getvalue()
    finally:
        output.close()
        image.close()
    media_type = _MIME_BY_FORMAT[image_format]
    return raw, f"data:{media_type};base64,{base64.b64encode(raw).decode('ascii')}"


def _animated_png() -> tuple[bytes, str]:
    first = Image.new("RGB", (4, 4), color=(255, 0, 0))
    second = Image.new("RGB", (4, 4), color=(0, 0, 255))
    output = io.BytesIO()
    try:
        first.save(
            output,
            format="PNG",
            save_all=True,
            append_images=[second],
            duration=100,
            loop=0,
        )
        raw = output.getvalue()
    finally:
        output.close()
        first.close()
        second.close()
    return raw, f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}"


def _input(
    data_url: str,
    *,
    attachment_id: str = "image-1",
    media_type: str = "image/png",
) -> AIImageAttachmentInput:
    return AIImageAttachmentInput.model_validate(
        {
            "id": attachment_id,
            "media_type": media_type,
            "data_url": data_url,
        }
    )


def _prepare(
    attachments: list[AIImageAttachmentInput],
    **overrides: int,
):
    limits = {
        "max_count": 3,
        "max_bytes": 4 * 1024 * 1024,
        "max_total_bytes": 12 * 1024 * 1024,
        "max_encoded_chars": 17_000_000,
        "max_pixels": 16_000_000,
        "max_total_pixels": 24_000_000,
    }
    limits.update(overrides)
    return prepare_image_attachments(attachments, **limits)


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "WEBP"])
def test_real_decode_magic_and_safe_reencode_accept_supported_images(
    image_format: str,
) -> None:
    _, data_url = _synthetic_image(image_format)
    media_type = _MIME_BY_FORMAT[image_format]
    prepared = _prepare([_input(data_url, media_type=media_type)])
    try:
        assert len(prepared) == 1
        assert prepared[0].media_type == media_type
        assert (prepared[0].width, prepared[0].height) == (8, 6)
        assert prepared[0].source == "USER_PROVIDED"
        with Image.open(io.BytesIO(prepared[0].data)) as decoded:
            decoded.load()
            assert decoded.size == (8, 6)
    finally:
        clear_prepared_attachments(prepared)


def test_declared_mime_data_url_magic_and_pillow_must_all_match() -> None:
    raw, _ = _synthetic_image("PNG")
    fake_jpeg = f"data:image/jpeg;base64,{base64.b64encode(raw).decode('ascii')}"

    with pytest.raises(AIAttachmentValidationError) as exc_info:
        _prepare([_input(fake_jpeg, media_type="image/jpeg")])

    assert exc_info.value.code == AIAttachmentErrorCode.MEDIA_TYPE_MISMATCH
    assert "data:image" not in repr(exc_info.value)


def test_png_zip_polyglot_trailing_payload_is_rejected_before_decode() -> None:
    raw, _ = _synthetic_image("PNG")
    polyglot = raw + b"PK\x03\x04synthetic-zip-payload"
    data_url = "data:image/png;base64," + base64.b64encode(polyglot).decode(
        "ascii"
    )

    with pytest.raises(AIAttachmentValidationError) as exc_info:
        _prepare([_input(data_url)])

    assert exc_info.value.code == AIAttachmentErrorCode.INVALID_IMAGE
    assert "synthetic-zip-payload" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("data_url", "expected_code"),
    [
        ("data:image/png;base64,", AIAttachmentErrorCode.EMPTY),
        (
            "data:image/png;base64,%%%not-base64%%%",
            AIAttachmentErrorCode.INVALID_DATA_URL,
        ),
        (
            "data:image/png;base64,"
            + base64.b64encode(b"\x89PNG\r\n\x1a\ncorrupt").decode("ascii"),
            AIAttachmentErrorCode.INVALID_IMAGE,
        ),
    ],
)
def test_empty_invalid_base64_and_corrupt_images_are_rejected_without_echo(
    data_url: str,
    expected_code: AIAttachmentErrorCode,
) -> None:
    attachment = _input(data_url)
    assert "data:image" not in repr(attachment)

    with pytest.raises(AIAttachmentValidationError) as exc_info:
        _prepare([attachment])

    assert exc_info.value.code == expected_code
    assert data_url not in str(exc_info.value)
    assert data_url not in repr(exc_info.value)


def test_animated_allowed_format_is_rejected() -> None:
    _, data_url = _animated_png()

    with pytest.raises(AIAttachmentValidationError) as exc_info:
        _prepare([_input(data_url)])

    assert exc_info.value.code == AIAttachmentErrorCode.ANIMATED_IMAGE


def test_per_image_and_request_pixel_limits_are_fail_closed() -> None:
    _, large_url = _synthetic_image(size=(101, 101))
    with pytest.raises(AIAttachmentValidationError) as exc_info:
        _prepare([_input(large_url)], max_pixels=10_000)
    assert exc_info.value.code == AIAttachmentErrorCode.PIXEL_LIMIT


def test_remaining_request_pixel_budget_rejects_before_next_full_load(
    monkeypatch,
) -> None:
    _, first_url = _synthetic_image(size=(10, 10))
    _, second_url = _synthetic_image(size=(11, 10))
    loaded_sizes: list[tuple[int, int]] = []
    original_load = Image.Image.load

    def tracked_load(image, *args, **kwargs):
        loaded_sizes.append(image.size)
        return original_load(image, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "load", tracked_load)
    attachments = [
        _input(first_url, attachment_id="image-1"),
        _input(second_url, attachment_id="image-2"),
    ]

    with pytest.raises(AIAttachmentValidationError) as exc_info:
        _prepare(
            attachments,
            max_pixels=1_000,
            max_total_pixels=150,
        )

    assert exc_info.value.code == AIAttachmentErrorCode.PIXEL_LIMIT
    assert (10, 10) in loaded_sizes
    assert (11, 10) not in loaded_sizes

    _, data_url = _synthetic_image(size=(10, 10))
    attachments = [
        _input(data_url, attachment_id=f"image-{index}") for index in range(3)
    ]
    with pytest.raises(AIAttachmentValidationError) as exc_info:
        _prepare(attachments, max_total_pixels=250)
    assert exc_info.value.code == AIAttachmentErrorCode.PIXEL_LIMIT


def test_raw_single_total_and_encoded_limits_are_enforced() -> None:
    raw, data_url = _synthetic_image(size=(32, 32))
    with pytest.raises(AIAttachmentValidationError) as exc_info:
        _prepare([_input(data_url)], max_bytes=len(raw) - 1)
    assert exc_info.value.code == AIAttachmentErrorCode.TOO_LARGE

    attachments = [
        _input(data_url, attachment_id="image-1"),
        _input(data_url, attachment_id="image-2"),
    ]
    with pytest.raises(AIAttachmentValidationError) as exc_info:
        _prepare(attachments, max_total_bytes=(len(raw) * 2) - 1)
    assert exc_info.value.code == AIAttachmentErrorCode.TOO_LARGE

    with pytest.raises(AIAttachmentValidationError) as exc_info:
        _prepare(attachments, max_encoded_chars=(len(data_url) * 2) - 1)
    assert exc_info.value.code == AIAttachmentErrorCode.TOO_LARGE


def test_duplicate_and_more_than_three_attachment_ids_are_rejected() -> None:
    _, data_url = _synthetic_image()
    duplicate = [_input(data_url), _input(data_url)]
    with pytest.raises(AIAttachmentValidationError) as exc_info:
        _prepare(duplicate)
    assert exc_info.value.code == AIAttachmentErrorCode.DUPLICATE_ID

    attachment_dict = {
        "id": "image-1",
        "media_type": "image/png",
        "data_url": data_url,
    }
    with pytest.raises(ValidationError):
        AIChatRequest.model_validate(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": "识别图片"}],
                    }
                ],
                "attachments": [
                    {**attachment_dict, "id": f"image-{index}"}
                    for index in range(4)
                ],
            }
        )


def test_exif_is_removed_and_mutable_buffers_are_zeroed() -> None:
    exif = Image.Exif()
    exif[0x010E] = "synthetic-private-metadata"
    _, data_url = _synthetic_image("JPEG", exif=exif)
    prepared = _prepare([_input(data_url, media_type="image/jpeg")])
    item = prepared[0]
    buffer_reference = item.data
    assert "synthetic-private-metadata" not in repr(item)
    assert "bytearray" not in repr(item)

    with Image.open(io.BytesIO(item.data)) as decoded:
        assert len(decoded.getexif()) == 0
        assert not decoded.info.get("exif")

    provider_part = ProviderImageContent(
        attachment_id=item.attachment_id,
        media_type=item.media_type,
        data=item.data,
    )
    assert "bytearray" not in repr(provider_part)
    item.clear()
    assert item.cleared is True
    assert buffer_reference == bytearray()


def test_image_processing_has_a_global_two_slot_concurrency_limit(monkeypatch) -> None:
    _, data_url = _synthetic_image()
    active = 0
    maximum_active = 0
    lock = threading.Lock()
    two_entered = threading.Event()
    release = threading.Event()

    def fake_prepare_one(
        attachment,
        *,
        max_bytes,
        max_pixels,
        remaining_total_pixels,
    ):
        nonlocal active, maximum_active
        del max_bytes, max_pixels, remaining_total_pixels
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            if active == 2:
                two_entered.set()
        assert release.wait(timeout=2)
        with lock:
            active -= 1
        return attachment_service.PreparedImageAttachment(
            attachment_id=attachment.id,
            media_type=attachment.media_type,
            width=1,
            height=1,
            original_bytes=1,
            data=bytearray(b"x"),
        )

    monkeypatch.setattr(attachment_service, "_prepare_one", fake_prepare_one)

    def prepare(index: int):
        return _prepare([_input(data_url, attachment_id=f"image-{index}")])

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(prepare, index) for index in range(4)]
        reached_two = two_entered.wait(timeout=2)
        observed_maximum = maximum_active
        release.set()
        results = [future.result(timeout=2) for future in futures]

    for prepared in results:
        clear_prepared_attachments(prepared)
    assert reached_two is True
    assert observed_maximum == 2
    assert maximum_active == 2


@pytest.mark.parametrize(
    "payload",
    [
        {
            "accepted": False,
            "notice_version": "aliyun-cn-beijing-v1",
            "attachment_ids": ["image-1"],
        },
        {
            "accepted": 1,
            "notice_version": "aliyun-cn-beijing-v1",
            "attachment_ids": ["image-1"],
        },
        {
            "accepted": True,
            "notice_version": "wrong-version",
            "attachment_ids": ["image-1"],
        },
    ],
)
def test_cloud_processing_consent_is_strict_and_versioned(payload: dict) -> None:
    with pytest.raises(ValidationError):
        AICloudProcessingConsent.model_validate(payload)

    consent = AICloudProcessingConsent.model_validate(
        {
            "accepted": True,
            "notice_version": "aliyun-cn-beijing-v1",
            "attachment_ids": ["image-1"],
        }
    )
    assert consent.accepted is True
