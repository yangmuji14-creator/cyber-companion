"""TTS 语音回复模块（文字转语音输出）

对齐 PawzoChat 的「AI 语音（TTS）」能力：角色可用 `[语音]`（或 `[voice]`，
可选情绪后缀如 `[语音-happy]`）标记把回复文字合成为语音，Web 端渲染为可播放
语音气泡。当前支持 OpenAI 兼容 TTS 后端（POST {base_url}/v1/audio/speech）。

内容：
- TTSProvider：服务商配置（名 / 类型 / api_key / base_url / model / voice）
- load_providers / save_providers：配置持久化到 CONFIG_DIR/tts_providers.json
- TTSManager.synthesize(text, voice) -> bytes：调用 /v1/audio/speech 返回音频
- parse_voice_markers(text)：解析回复里的语音标记，返回（显示文本, 是否带语音）
- strip_voice_markers(text)：去掉标记，返回纯显示文本

刻意保持与 webui/server.py 解耦：不 import server，仅接收 CONFIG_DIR 路径，
便于单测与复用。
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

# 语音标记：[语音]、[voice]、[语音-happy]、[voice-sad] 等
_VOICE_RE = re.compile(r"\[(?:语音|voice)(?:-[a-zA-Z\u4e00-\u9fff]+)?\]", re.IGNORECASE)


@dataclass
class TTSProvider:
    name: str
    type: str = "openai"
    api_key: str = ""
    base_url: str = "https://api.openai.com"
    model: str = "tts-1"
    voice: str = "alloy"
    enabled: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "TTSProvider":
        return cls(
            name=str(d.get("name", "")).strip(),
            type=str(d.get("type", "openai") or "openai"),
            api_key=str(d.get("api_key", "") or ""),
            base_url=(str(d.get("base_url", "") or "").strip() or "https://api.openai.com"),
            model=str(d.get("model", "tts-1") or "tts-1"),
            voice=str(d.get("voice", "alloy") or "alloy"),
            enabled=bool(d.get("enabled", True)),
            extra=dict(d.get("extra", {}) or {}),
        )

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "base_url": self.base_url,
            "model": self.model,
            "voice": self.voice,
            "enabled": self.enabled,
        }
        if self.api_key:
            d["api_key"] = self.api_key
        if self.extra:
            d["extra"] = self.extra
        return d


def parse_voice_markers(text: str) -> tuple[str, bool]:
    """解析回复里的语音标记。

    Returns:
        (显示文本, 是否包含语音标记)。显示文本 = 去掉所有语音标记后的纯文字。
    """
    if not text:
        return "", False
    has_voice = bool(_VOICE_RE.search(text))
    display = _VOICE_RE.sub("", text).strip()
    return display, has_voice


def strip_voice_markers(text: str) -> str:
    """去掉语音标记，返回纯显示文本。"""
    return _VOICE_RE.sub("", text or "").strip()


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


class TTSStore:
    """TTS 服务商配置持久化（CONFIG_DIR/tts_providers.json）。"""

    def __init__(self, config_dir: str | Path):
        self.path = Path(config_dir) / "tts_providers.json"

    def load_providers(self) -> list[TTSProvider]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"load tts providers failed: {e}")
            return []
        providers = []
        for item in data.get("providers", []) or []:
            try:
                providers.append(TTSProvider.from_dict(item))
            except Exception as e:
                logger.warning(f"skip bad tts provider: {e}")
        return providers

    def save_providers(self, providers: list[TTSProvider]) -> None:
        _atomic_write(
            self.path,
            json.dumps(
                {"providers": [p.to_dict() for p in providers]},
                ensure_ascii=False,
                indent=2,
            ),
        )

    def active_provider(self) -> TTSProvider | None:
        providers = self.load_providers()
        for p in providers:
            if p.enabled:
                return p
        return None


class TTSManager:
    """TTS 合成器：调用 OpenAI 兼容 /v1/audio/speech。"""

    def __init__(self, store: TTSStore, timeout: float = 30.0):
        self._store = store
        self._timeout = timeout

    async def synthesize(
        self,
        text: str,
        provider: TTSProvider | None = None,
        voice: str | None = None,
    ) -> bytes:
        """合成语音，返回音频字节（mp3）。无有效 provider 时抛 ValueError。"""
        prov = provider or self._store.active_provider()
        if prov is None:
            raise ValueError("未配置语音服务商")
        if not prov.api_key:
            raise ValueError("语音服务商未配置 API Key")
        if not text.strip():
            raise ValueError("语音内容为空")

        import httpx

        url = f"{prov.base_url.rstrip('/')}/v1/audio/speech"
        payload = {
            "model": prov.model,
            "input": text,
            "voice": voice or prov.voice,
            "response_format": "mp3",
        }
        headers = {
            "Authorization": f"Bearer {prov.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                raise ValueError(
                    f"TTS 接口返回 {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.content
            if not data:
                raise ValueError("TTS 接口返回空音频")
            return data
