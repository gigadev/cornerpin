"""Checking and preparing uploads (ADR-025).

Photos are decoded and re-encoded: that applies the camera's rotation, drops all metadata (phone
photos carry GPS position and device details) and caps the longest side, so pages stay light on
a weak signal. Documents are stored as uploaded, after checking what they really are."""

import io
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PHOTO_BYTES = 15 * 1024 * 1024
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_PHOTO_EDGE = 2560
CHUNK = 1024 * 1024

# Pillow format -> (content type, extension)
PHOTO_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
# Leading bytes -> (content type, extension)
DOCUMENT_SIGNATURES = (
    (b"%PDF-", ("application/pdf", "pdf")),
    (b"\xff\xd8\xff", ("image/jpeg", "jpg")),
    (b"\x89PNG\r\n\x1a\n", ("image/png", "png")),
)


class UnsupportedUpload(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


@dataclass(frozen=True)
class PreparedPhoto:
    data: bytes
    content_type: str
    extension: str
    width: int
    height: int


@dataclass(frozen=True)
class CheckedDocument:
    data: bytes
    content_type: str
    extension: str


async def read_limited(upload: UploadFile, limit: int) -> bytes:
    """The whole upload, or 413 as soon as it passes `limit` bytes."""
    buffer = bytearray()
    while chunk := await upload.read(CHUNK):
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"That file is larger than {limit // (1024 * 1024)} MB",
            )
    return bytes(buffer)


def prepare_photo(data: bytes) -> PreparedPhoto:
    try:
        with Image.open(io.BytesIO(data)) as original:
            fmt = original.format or ""
            if fmt not in PHOTO_FORMATS:
                raise UnsupportedUpload("Photos must be JPEG, PNG or WebP")
            image = ImageOps.exif_transpose(original)
            image.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise UnsupportedUpload("That file isn't a photo we can read") from exc

    image.thumbnail((MAX_PHOTO_EDGE, MAX_PHOTO_EDGE))
    content_type, extension = PHOTO_FORMATS[fmt]
    out = io.BytesIO()
    if fmt == "JPEG":
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.save(out, "JPEG", quality=88, optimize=True, progressive=True)
    elif fmt == "PNG":
        image.save(out, "PNG", optimize=True)
    else:
        image.save(out, "WEBP", quality=85)
    width, height = image.size
    return PreparedPhoto(out.getvalue(), content_type, extension, width, height)


def check_document(data: bytes) -> CheckedDocument:
    for signature, (content_type, extension) in DOCUMENT_SIGNATURES:
        if data.startswith(signature):
            return CheckedDocument(data, content_type, extension)
    raise UnsupportedUpload("Documents must be PDF, JPEG or PNG")
