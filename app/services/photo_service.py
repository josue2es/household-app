"""
Photo service — saves the photos that prove a task was done.

Phone photos are 3-8 MB each. We shrink them to at most PHOTO_MAX_SIDE
pixels on the longest side and re-encode them as JPEG (~200-400 KB),
which is plenty to judge a cleaning job and keeps data/ small.

Pure Python (Pillow only, no NiceGUI dependency), like vision_service.py.
"""
import io
import logging
import secrets
from datetime import date
from pathlib import Path

from PIL import Image, ImageOps

from app.database import PHOTOS_DIR

log = logging.getLogger("household.photos")

PHOTO_MAX_SIDE = 1600
JPEG_QUALITY = 80


class PhotoError(Exception):
    """The uploaded file couldn't be read as a photo. `str()` is a message for the user."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


def save_photo(image_bytes: bytes, day: date, check_id: int) -> str:
    """
    Shrink and save a photo. Returns its path relative to PHOTOS_DIR,
    e.g. "2026-10-12/check-7-a1b2c3d4.jpg".

    Blocking (decoding a 12 MP photo takes a moment): call it through
    `run.io_bound` from the UI so other users aren't frozen meanwhile.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as original:
            # Phones store photos sideways plus an "orientation" tag;
            # exif_transpose applies the tag so the photo shows upright.
            image = ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    except Exception as e:  # Pillow raises several unrelated types for bad files
        raise PhotoError("No se pudo leer la foto (¿es una imagen JPG o PNG?)",
                         f"{type(e).__name__}: {e}") from e

    # The random part makes every file name new, so a retaken photo never
    # shows the old one from the browser's cache.
    relative = f"{day.isoformat()}/check-{check_id}-{secrets.token_hex(4)}.jpg"
    path = PHOTOS_DIR / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue())
    log.info("Saved %s (%d KB, from %d KB)", relative,
             len(buffer.getvalue()) // 1024, len(image_bytes) // 1024)
    return relative


def photo_file(relative: str) -> Path | None:
    """Absolute path of a saved photo, or None if it's missing or outside PHOTOS_DIR."""
    path = (PHOTOS_DIR / relative).resolve()
    if not path.is_relative_to(PHOTOS_DIR.resolve()) or not path.is_file():
        return None
    return path


def delete_photo(relative: str | None) -> None:
    """Delete a saved photo. Does nothing if it's already gone."""
    if not relative:
        return
    path = photo_file(relative)
    if path is not None:
        path.unlink(missing_ok=True)
