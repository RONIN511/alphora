import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Literal

import requests
from openai import OpenAI, AsyncOpenAI

from .utils import (
    build_image_part,
    build_audio_part,
    build_video_part,
    normalize_binary_content,
)


Mode = Literal["generic", "openai"]


@dataclass
class EndpointConfig:
    url: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    timeout: int = 60
    mode: Mode = "generic"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


class MultiModalHTTPClient:
    """
    多模态生成器：通过 HTTP 调用外部模型生成图片/音频/视频。

    - generic: 任意 HTTP POST，返回 JSON 或二进制
    - openai: OpenAI 风格 images/audio 端点
    """

    def __init__(
        self,
        image: Optional[EndpointConfig] = None,
        audio: Optional[EndpointConfig] = None,
        video: Optional[EndpointConfig] = None,
        default_headers: Optional[Dict[str, str]] = None,
    ):
        self.image = image or EndpointConfig()
        self.audio = audio or EndpointConfig()
        self.video = video or EndpointConfig()
        self.default_headers = default_headers or {}

    def generate_image(self, prompt: str, **kwargs) -> dict:
        return self._request_and_build(
            kind="image",
            config=self.image,
            prompt=prompt,
            **kwargs,
        )

    def generate_audio(self, prompt: str, **kwargs) -> dict:
        return self._request_and_build(
            kind="audio",
            config=self.audio,
            prompt=prompt,
            **kwargs,
        )

    def generate_video(self, prompt: str, **kwargs) -> dict:
        return self._request_and_build(
            kind="video",
            config=self.video,
            prompt=prompt,
            **kwargs,
        )

    async def agenerate_image(self, prompt: str, **kwargs) -> dict:
        if self.image.mode == "openai":
            return await self._openai_generate_image(self.image, prompt, **kwargs)
        return await asyncio.to_thread(self.generate_image, prompt, **kwargs)

    async def agenerate_audio(self, prompt: str, **kwargs) -> dict:
        if self.audio.mode == "openai":
            return await self._openai_generate_audio(self.audio, prompt, **kwargs)
        return await asyncio.to_thread(self.generate_audio, prompt, **kwargs)

    async def agenerate_video(self, prompt: str, **kwargs) -> dict:
        if self.video.mode == "openai":
            raise NotImplementedError("OpenAI official API does not support video generation.")
        return await asyncio.to_thread(self.generate_video, prompt, **kwargs)

    def _request_and_build(self, kind: str, config: EndpointConfig, prompt: str, **kwargs) -> dict:
        if not config.url:
            if config.mode == "openai":
                return self._openai_generate(kind, config, prompt, **kwargs)
            raise ValueError(f"{kind} endpoint is not configured.")

        headers = {**self.default_headers, **(config.headers or {})}
        payload = self._build_payload(kind, config.mode, prompt, **kwargs)
        resp = requests.post(config.url, json=payload, headers=headers, timeout=config.timeout)

        content_type = (resp.headers.get("content-type") or "").lower()
        if content_type.startswith(("image/", "audio/", "video/")):
            b64, url = normalize_binary_content(resp.content, content_type.split(";")[0])
            return self._build_part(kind, url=url, mime=content_type.split(";")[0])

        # Try JSON
        try:
            data = resp.json()
        except Exception:
            return self._build_part(kind, url=str(resp.text))

        url_or_b64 = self._extract_payload(kind, config.mode, data)
        return self._build_part(kind, url_or_b64=url_or_b64)

    def _build_payload(self, kind: str, mode: Mode, prompt: str, **kwargs) -> Dict[str, Any]:
        if mode == "openai":
            if kind == "image":
                payload = {
                    "prompt": prompt,
                    "response_format": "b64_json",
                }
            elif kind == "audio":
                payload = {
                    "input": prompt,
                    "format": "wav",
                }
            else:
                payload = {"prompt": prompt}
        else:
            payload = {"prompt": prompt}

        payload.update(kwargs)
        return payload

    def _extract_payload(self, kind: str, mode: Mode, data: Dict[str, Any]) -> str:
        if mode == "openai":
            if kind == "image":
                items = data.get("data") or []
                if items and "b64_json" in items[0]:
                    return items[0]["b64_json"]
                if items and "url" in items[0]:
                    return items[0]["url"]
            if kind == "audio":
                audio = data.get("audio")
                if isinstance(audio, dict):
                    return audio.get("url") or audio.get("b64") or audio.get("base64") or ""
        for key in ("b64", "base64", "data", "content", "image", "audio", "video", "url"):
            if key in data and data[key]:
                val = data[key]
                if isinstance(val, list) and val:
                    return val[0]
                if isinstance(val, dict):
                    return val.get("url") or val.get("b64") or val.get("base64") or ""
                return val
        return ""

    def _build_part(self, kind: str, url_or_b64: Optional[str] = None, url: Optional[str] = None, mime: Optional[str] = None) -> dict:
        if url is None:
            url = url_or_b64 or ""
        if kind == "image":
            return build_image_part(url, mime or "image/png")
        if kind == "audio":
            return build_audio_part(url, mime or "audio/wav")
        if kind == "video":
            return build_video_part(url, mime or "video/mp4")
        raise ValueError(f"Unknown kind: {kind}")

    def _openai_client(self, config: EndpointConfig) -> OpenAI:
        return OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            default_headers={**self.default_headers, **(config.headers or {})},
        )

    def _openai_async_client(self, config: EndpointConfig) -> AsyncOpenAI:
        return AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            default_headers={**self.default_headers, **(config.headers or {})},
        )

    def _openai_generate(self, kind: str, config: EndpointConfig, prompt: str, **kwargs) -> dict:
        if kind == "image":
            return self._openai_generate_image(config, prompt, **kwargs)
        if kind == "audio":
            return self._openai_generate_audio(config, prompt, **kwargs)
        if kind == "video":
            raise NotImplementedError("OpenAI official API does not support video generation.")
        raise ValueError(f"Unknown kind: {kind}")

    def _openai_generate_image(self, config: EndpointConfig, prompt: str, **kwargs) -> dict:
        client = self._openai_client(config)
        model = kwargs.pop("model", None) or config.model or "gpt-image-1"
        response = client.images.generate(
            model=model,
            prompt=prompt,
            **kwargs,
        )
        data = response.model_dump()
        url_or_b64 = self._extract_payload("image", "openai", data)
        return self._build_part("image", url_or_b64=url_or_b64)

    async def _openai_generate_image(self, config: EndpointConfig, prompt: str, **kwargs) -> dict:
        client = self._openai_async_client(config)
        model = kwargs.pop("model", None) or config.model or "gpt-image-1"
        response = await client.images.generate(
            model=model,
            prompt=prompt,
            **kwargs,
        )
        data = response.model_dump()
        url_or_b64 = self._extract_payload("image", "openai", data)
        return self._build_part("image", url_or_b64=url_or_b64)

    def _openai_generate_audio(self, config: EndpointConfig, prompt: str, **kwargs) -> dict:
        client = self._openai_client(config)
        model = kwargs.pop("model", None) or config.model or "gpt-4o-mini-tts"
        voice = kwargs.pop("voice", None)
        if not voice:
            raise ValueError("OpenAI audio generation requires 'voice' parameter.")
        response = client.audio.speech.create(
            model=model,
            voice=voice,
            input=prompt,
            **kwargs,
        )
        content_type = "audio/wav"
        b64, url = normalize_binary_content(response.content, content_type)
        return self._build_part("audio", url=url, mime=content_type)

    async def _openai_generate_audio(self, config: EndpointConfig, prompt: str, **kwargs) -> dict:
        client = self._openai_async_client(config)
        model = kwargs.pop("model", None) or config.model or "gpt-4o-mini-tts"
        voice = kwargs.pop("voice", None)
        if not voice:
            raise ValueError("OpenAI audio generation requires 'voice' parameter.")
        response = await client.audio.speech.create(
            model=model,
            voice=voice,
            input=prompt,
            **kwargs,
        )
        content_type = "audio/wav"
        b64, url = normalize_binary_content(response.content, content_type)
        return self._build_part("audio", url=url, mime=content_type)
