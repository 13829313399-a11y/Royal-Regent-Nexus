import base64
import binascii
import hashlib
import io
import re
import threading
import warnings
from dataclasses import dataclass, field
from enum import StrEnum

from PIL import Image, ImageOps, UnidentifiedImageError

from app.schemas.ai.attachment import AIImageAttachmentInput, AIImageMediaType

_DATA_URL_HEADER = re.compile(
    r"^data:(image/(?:png|jpeg|webp));base64$",
)
_PIL_FORMAT_TO_MEDIA_TYPE: dict[str, AIImageMediaType] = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}
_IMAGE_PROCESSING_SLOTS = threading.BoundedSemaphore(value=2)
_PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"


class AIAttachmentErrorCode(StrEnum):
    TOO_MANY = "AI_ATTACHMENT_TOO_MANY"
    DUPLICATE_ID = "AI_ATTACHMENT_DUPLICATE_ID"
    EMPTY = "AI_ATTACHMENT_EMPTY"
    INVALID_DATA_URL = "AI_ATTACHMENT_INVALID_DATA_URL"
    TOO_LARGE = "AI_ATTACHMENT_TOO_LARGE"
    MEDIA_TYPE_MISMATCH = "AI_ATTACHMENT_MEDIA_TYPE_MISMATCH"
    INVALID_IMAGE = "AI_ATTACHMENT_INVALID_IMAGE"
    ANIMATED_IMAGE = "AI_ATTACHMENT_ANIMATED_IMAGE"
    PIXEL_LIMIT = "AI_ATTACHMENT_PIXEL_LIMIT"


class AIAttachmentValidationError(ValueError):
    def __init__(self, code: AIAttachmentErrorCode, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


def _zero_buffer(buffer: bytearray) -> None:
    if buffer:
        buffer[:] = b"\x00" * len(buffer)
        buffer.clear()


@dataclass(slots=True)
class PreparedImageAttachment:
    attachment_id: str
    media_type: AIImageMediaType
    width: int
    height: int
    original_bytes: int
    data: bytearray = field(repr=False)
    source: str = "USER_PROVIDED"
    _sha256: str | None = field(default=None, repr=False)
    _cleared: bool = False

    @property
    def cleared(self) -> bool:
        return self._cleared

    def clear(self) -> None:
        if self._cleared:
            return
        _zero_buffer(self.data)
        self._sha256 = None
        self._cleared = True


def clear_prepared_attachments(
    attachments: tuple[PreparedImageAttachment, ...] | list[PreparedImageAttachment],
) -> None:
    for attachment in attachments:
        attachment.clear()


def discard_raw_attachment_inputs(
    attachments: list[AIImageAttachmentInput],
) -> None:
    """Release immutable request strings as early as Pydantic permits.

    Python strings cannot be zeroed in place. Replacing the field drops the
    application's reference; decoded and re-encoded bytes use explicit mutable
    buffers that are zeroed separately.
    """

    for attachment in attachments:
        attachment.data_url = ""


def _decode_data_url(
    attachment: AIImageAttachmentInput,
    *,
    max_bytes: int,
) -> bytearray:
    try:
        header, encoded = attachment.data_url.split(",", 1)
    except ValueError as exc:
        raise AIAttachmentValidationError(
            AIAttachmentErrorCode.INVALID_DATA_URL,
            "图片数据格式不正确。",
        ) from exc

    header_match = _DATA_URL_HEADER.fullmatch(header)
    if header_match is None or header_match.group(1) != attachment.media_type:
        raise AIAttachmentValidationError(
            AIAttachmentErrorCode.MEDIA_TYPE_MISMATCH,
            "图片声明类型与数据类型不一致。",
        )
    if not encoded:
        raise AIAttachmentValidationError(
            AIAttachmentErrorCode.EMPTY,
            "图片不能为空。",
        )

    decoded: bytes | None = None
    try:
        decoded = base64.b64decode(encoded, validate=True)
        raw = bytearray(decoded)
    except (binascii.Error, ValueError) as exc:
        raise AIAttachmentValidationError(
            AIAttachmentErrorCode.INVALID_DATA_URL,
            "图片数据格式不正确。",
        ) from exc
    finally:
        decoded = None

    if not raw:
        _zero_buffer(raw)
        raise AIAttachmentValidationError(
            AIAttachmentErrorCode.EMPTY,
            "图片不能为空。",
        )
    if len(raw) > max_bytes:
        _zero_buffer(raw)
        raise AIAttachmentValidationError(
            AIAttachmentErrorCode.TOO_LARGE,
            "单张图片不能超过允许的大小。",
        )
    return raw


def _media_type_from_magic(raw: bytearray) -> AIImageMediaType | None:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def _has_exact_container_boundary(
    raw: bytearray,
    media_type: AIImageMediaType,
) -> bool:
    if media_type == "image/png":
        return raw.endswith(_PNG_IEND)
    if media_type == "image/jpeg":
        return raw.endswith(b"\xff\xd9")
    if len(raw) < 12:
        return False
    riff_payload_size = int.from_bytes(raw[4:8], byteorder="little", signed=False)
    return len(raw) == riff_payload_size + 8


def _safe_image_copy(image: Image.Image) -> Image.Image:
    transposed = ImageOps.exif_transpose(image)
    try:
        target_mode = "RGBA" if "A" in transposed.getbands() else "RGB"
        converted = transposed.convert(target_mode)
        try:
            clean = Image.new(target_mode, converted.size)
            clean.paste(converted)
            return clean
        finally:
            converted.close()
    finally:
        if transposed is not image:
            transposed.close()


def _encode_clean_image(
    image: Image.Image,
    media_type: AIImageMediaType,
) -> bytearray:
    output = io.BytesIO()
    try:
        if media_type == "image/png":
            image.save(output, format="PNG", compress_level=6, optimize=False)
        elif media_type == "image/jpeg":
            image.save(
                output,
                format="JPEG",
                quality=90,
                optimize=False,
            )
        else:
            image.save(output, format="WEBP", lossless=True, method=4)
        view = output.getbuffer()
        try:
            return bytearray(view)
        finally:
            view.release()
    finally:
        output.close()


def _prepare_one(
    attachment: AIImageAttachmentInput,
    *,
    max_bytes: int,
    max_pixels: int,
    remaining_total_pixels: int,
) -> PreparedImageAttachment:
    raw = _decode_data_url(attachment, max_bytes=max_bytes)
    sanitized: bytearray | None = None
    clean_image: Image.Image | None = None
    try:
        magic_media_type = _media_type_from_magic(raw)
        if magic_media_type is None or magic_media_type != attachment.media_type:
            raise AIAttachmentValidationError(
                AIAttachmentErrorCode.MEDIA_TYPE_MISMATCH,
                "图片声明类型与真实类型不一致。",
            )
        if not _has_exact_container_boundary(raw, attachment.media_type):
            raise AIAttachmentValidationError(
                AIAttachmentErrorCode.INVALID_IMAGE,
                "图片容器包含不允许的尾随数据。",
            )

        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as probe:
                pillow_media_type = _PIL_FORMAT_TO_MEDIA_TYPE.get(probe.format or "")
                if pillow_media_type != attachment.media_type:
                    raise AIAttachmentValidationError(
                        AIAttachmentErrorCode.MEDIA_TYPE_MISMATCH,
                        "图片声明类型与解码类型不一致。",
                    )
                if bool(getattr(probe, "is_animated", False)) or int(
                    getattr(probe, "n_frames", 1)
                ) != 1:
                    raise AIAttachmentValidationError(
                        AIAttachmentErrorCode.ANIMATED_IMAGE,
                        "不接受动画图片。",
                    )
                width, height = probe.size
                pixel_count = width * height
                if (
                    width <= 0
                    or height <= 0
                    or pixel_count > max_pixels
                    or pixel_count > remaining_total_pixels
                ):
                    raise AIAttachmentValidationError(
                        AIAttachmentErrorCode.PIXEL_LIMIT,
                        "图片像素超过允许的上限。",
                    )
                probe.verify()

            with Image.open(io.BytesIO(raw)) as decoded_image:
                decoded_image.load()
                clean_image = _safe_image_copy(decoded_image)

        sanitized = _encode_clean_image(clean_image, attachment.media_type)
        if not sanitized or len(sanitized) > max_bytes:
            raise AIAttachmentValidationError(
                AIAttachmentErrorCode.TOO_LARGE,
                "图片安全处理后的大小超过允许上限。",
            )

        with Image.open(io.BytesIO(sanitized)) as verified:
            verified.load()
            if _PIL_FORMAT_TO_MEDIA_TYPE.get(verified.format or "") != attachment.media_type:
                raise AIAttachmentValidationError(
                    AIAttachmentErrorCode.INVALID_IMAGE,
                    "图片安全处理失败。",
                )
            if verified.info.get("exif") or len(verified.getexif()) > 0:
                raise AIAttachmentValidationError(
                    AIAttachmentErrorCode.INVALID_IMAGE,
                    "图片元数据清理失败。",
                )

        prepared = PreparedImageAttachment(
            attachment_id=attachment.id,
            media_type=attachment.media_type,
            width=width,
            height=height,
            original_bytes=len(raw),
            data=sanitized,
            _sha256=hashlib.sha256(raw).hexdigest(),
        )
        sanitized = None
        return prepared
    except AIAttachmentValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise AIAttachmentValidationError(
            AIAttachmentErrorCode.INVALID_IMAGE,
            "图片已损坏或无法安全解码。",
        ) from exc
    finally:
        if clean_image is not None:
            clean_image.close()
        _zero_buffer(raw)
        if sanitized is not None:
            _zero_buffer(sanitized)


def prepare_image_attachments(
    attachments: list[AIImageAttachmentInput],
    *,
    max_count: int,
    max_bytes: int,
    max_total_bytes: int,
    max_encoded_chars: int,
    max_pixels: int,
    max_total_pixels: int,
) -> tuple[PreparedImageAttachment, ...]:
    if len(attachments) > max_count:
        raise AIAttachmentValidationError(
            AIAttachmentErrorCode.TOO_MANY,
            "每次最多上传三张图片。",
        )

    if sum(len(attachment.data_url) for attachment in attachments) > max_encoded_chars:
        raise AIAttachmentValidationError(
            AIAttachmentErrorCode.TOO_LARGE,
            "本次图片数据总量超过允许上限。",
        )

    attachment_ids = [attachment.id for attachment in attachments]
    if len(set(attachment_ids)) != len(attachment_ids):
        raise AIAttachmentValidationError(
            AIAttachmentErrorCode.DUPLICATE_ID,
            "图片标识不能重复。",
        )

    prepared: list[PreparedImageAttachment] = []
    prepared_bytes = 0
    prepared_pixels = 0
    try:
        for attachment in attachments:
            with _IMAGE_PROCESSING_SLOTS:
                item = _prepare_one(
                    attachment,
                    max_bytes=max_bytes,
                    max_pixels=max_pixels,
                    remaining_total_pixels=max_total_pixels - prepared_pixels,
                )
            prepared_bytes += item.original_bytes
            prepared_pixels += item.width * item.height
            if prepared_bytes > max_total_bytes:
                item.clear()
                raise AIAttachmentValidationError(
                    AIAttachmentErrorCode.TOO_LARGE,
                    "本次图片数据总量超过允许上限。",
                )
            prepared.append(item)
        return tuple(prepared)
    except Exception:
        clear_prepared_attachments(prepared)
        raise
