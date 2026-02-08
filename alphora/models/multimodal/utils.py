import base64
import mimetypes
from typing import Tuple, Optional, Union


def to_data_url(mime: str, b64: str) -> str:
    return f"data:{mime};base64,{b64}"


def _ensure_b64(data: Union[bytes, str]) -> str:
    if isinstance(data, bytes):
        return base64.b64encode(data).decode("ascii")
    return data


def _guess_mime(path_or_mime: str, default_mime: str) -> str:
    if "/" in path_or_mime:
        return path_or_mime
    mime, _ = mimetypes.guess_type(path_or_mime)
    return mime or default_mime


def _normalize_url(b64_or_url: str, mime: str) -> str:
    if b64_or_url.startswith("data:") or b64_or_url.startswith("http"):
        return b64_or_url
    return to_data_url(mime, b64_or_url)


def build_image_part(b64_or_url: str, mime: str = "image/png") -> dict:
    url = _normalize_url(b64_or_url, mime)
    return {"type": "image_url", "image_url": {"url": url}}


def build_audio_part(b64_or_url: str, mime: str = "audio/wav") -> dict:
    url = _normalize_url(b64_or_url, mime)
    return {"type": "audio", "audio": {"url": url}}


def build_video_part(b64_or_url: str, mime: str = "video/mp4") -> dict:
    url = _normalize_url(b64_or_url, mime)
    return {"type": "video", "video": {"url": url}}


def normalize_binary_content(
    data: Union[bytes, str],
    mime: str,
) -> Tuple[str, str]:
    b64 = _ensure_b64(data)
    url = to_data_url(mime, b64)
    return b64, url
