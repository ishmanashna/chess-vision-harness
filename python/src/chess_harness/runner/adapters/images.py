"""JPEG downscale for vision provider payloads only."""

from __future__ import annotations

import io
from typing import Optional

from PIL import Image


def compress_png_for_provider(
    png_bytes: bytes,
    *,
    max_side: int = 384,
    quality: int = 85,
) -> bytes:
    """Return JPEG bytes scaled so the longest side is at most *max_side*."""
    side = max(32, int(max_side))
    with Image.open(io.BytesIO(png_bytes)) as img:
        rgb = img.convert("RGB")
        width, height = rgb.size
        longest = max(width, height)
        if longest > side:
            scale = side / float(longest)
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            rgb = rgb.resize(new_size, Image.Resampling.LANCZOS)
        out = io.BytesIO()
        rgb.save(out, format="JPEG", quality=max(1, min(95, int(quality))), optimize=True)
        return out.getvalue()


def png_to_jpeg_data_url(
    png_bytes: bytes,
    *,
    max_side: Optional[int] = 384,
    quality: int = 85,
) -> str:
    import base64

    jpeg = compress_png_for_provider(
        png_bytes,
        max_side=max_side or 384,
        quality=quality,
    )
    encoded = base64.standard_b64encode(jpeg).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
