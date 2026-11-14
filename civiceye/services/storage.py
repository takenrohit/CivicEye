"""Image validation and storage.

- Content is validated by decoding with Pillow (not by extension or client MIME).
- Images are re-encoded, which drops EXIF (including GPS) and any trailing payload.
- Stored names are random; user filenames are never used on disk.
- Files live outside static/ and are served only through authorised routes.
"""
from __future__ import annotations

import io
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG": ("image/jpeg", ".jpg"), "PNG": ("image/png", ".png"), "WEBP": ("image/webp", ".webp")}


class UploadError(ValueError):
    pass


@dataclass
class StoredImage:
    stored_name: str
    mime_type: str
    width: int
    height: int
    size_bytes: int


def _read_limited(file_storage, max_bytes: int) -> bytes:
    data = file_storage.stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UploadError(f"Image is larger than {max_bytes // (1024 * 1024)} MB.")
    if not data:
        raise UploadError("Uploaded file is empty.")
    return data


def validate_and_store_image(file_storage, upload_dir: str, config) -> StoredImage:
    data = _read_limited(file_storage, config["MAX_IMAGE_BYTES"])
    Image.MAX_IMAGE_PIXELS = config["MAX_IMAGE_PIXELS"]
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise UploadError("File is not a valid JPEG, PNG or WebP image.") from exc

    if fmt not in ALLOWED_FORMATS:
        raise UploadError("Only JPEG, PNG or WebP images are accepted.")
    w, h = img.size
    if min(w, h) < config["MIN_IMAGE_SIDE"] or max(w, h) > config["MAX_IMAGE_SIDE"]:
        raise UploadError(f"Image dimensions {w}×{h} are outside the accepted range.")

    img = ImageOps.exif_transpose(img)  # apply orientation, then drop all metadata on save
    mime, ext = ALLOWED_FORMATS[fmt]
    if fmt == "JPEG" and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    out = io.BytesIO()
    save_kwargs = {"quality": 90} if fmt in ("JPEG", "WEBP") else {}
    img.save(out, format=fmt, **save_kwargs)  # no exif= argument → metadata not written
    payload = out.getvalue()

    os.makedirs(upload_dir, exist_ok=True)
    name = secrets.token_hex(16) + ext
    path = safe_path(upload_dir, name)
    with open(path, "xb") as fh:
        fh.write(payload)
    return StoredImage(name, mime, img.size[0], img.size[1], len(payload))


def safe_path(base_dir: str, name: str) -> Path:
    """Resolve a stored filename strictly inside base_dir (path-traversal guard)."""
    base = Path(base_dir).resolve()
    target = (base / name).resolve()
    if target.parent != base:
        raise UploadError("Invalid storage path.")
    return target
