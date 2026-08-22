"""Safe image-sticker packs shared by the Web UI and adapters."""

from __future__ import annotations

import random
import shutil
import zipfile
from collections import deque
from pathlib import Path


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_STICKER_SIZE = 8 * 1024 * 1024
MAX_UNPACKED_SIZE = 100 * 1024 * 1024
EMOTION_ALIASES = {
    "ecstatic": "happy", "content": "happy", "calm": "neutral",
    "tired": "sad", "depressed": "sad", "lonely": "sad",
    "anxious": "confused", "frustrated": "angry", "excited": "happy",
    "love": "loved", "grateful": "happy", "neutral": "neutral",
}


class StickerService:
    """Discover, import and select stickers without allowing path traversal."""

    def __init__(self, data_dir: str | Path, builtins_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) / "stickers"
        self.builtins_dir = Path(builtins_dir) if builtins_dir else None
        self._recent: deque[str] = deque(maxlen=8)

    @staticmethod
    def _safe_component(value: str) -> str:
        value = str(value or "").strip()
        if not value or value in {".", ".."} or any(c in value for c in "\\/:"):
            raise ValueError("invalid sticker path")
        return value

    def _roots(self) -> list[tuple[str, Path]]:
        roots: list[tuple[str, Path]] = []
        if self.builtins_dir and self.builtins_dir.exists():
            roots.append(("builtin", self.builtins_dir))
        if self.data_dir.exists():
            roots.extend((p.name, p) for p in self.data_dir.iterdir() if p.is_dir())
        return roots

    def list_stickers(self) -> list[dict]:
        result: list[dict] = []
        for pack, root in self._roots():
            for emotion_dir in sorted(p for p in root.iterdir() if p.is_dir()):
                images = [p for p in sorted(emotion_dir.iterdir())
                          if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
                if images:
                    result.append({
                        "pack": pack,
                        "emotion": emotion_dir.name,
                        "images": [p.name for p in images],
                    })
        return result

    def resolve(self, pack: str, emotion: str, filename: str) -> Path:
        pack = self._safe_component(pack)
        emotion = self._safe_component(emotion)
        filename = self._safe_component(filename)
        if Path(filename).suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError("unsupported sticker type")
        for name, root in self._roots():
            if name != pack:
                continue
            candidate = (root / emotion / filename).resolve()
            if candidate.parent == (root / emotion).resolve() and candidate.is_file():
                return candidate
        raise FileNotFoundError("sticker not found")

    def choose(self, mood: str, *, pack: str = "builtin") -> dict | None:
        target = EMOTION_ALIASES.get(str(mood or "").lower(), str(mood or "neutral").lower())
        groups = [g for g in self.list_stickers() if g["pack"] == pack]
        if not groups:
            groups = [g for g in self.list_stickers() if g["pack"] == "builtin"]
        preferred = [g for g in groups if g["emotion"].lower() == target]
        group = random.choice(preferred or groups) if (preferred or groups) else None
        if not group:
            return None
        candidates = [f for f in group["images"]
                      if f"{group['pack']}/{group['emotion']}/{f}" not in self._recent]
        filename = random.choice(candidates or group["images"])
        key = f"{group['pack']}/{group['emotion']}/{filename}"
        self._recent.append(key)
        return {
            "pack": group["pack"], "emotion": group["emotion"],
            "filename": filename,
            "url": f"/api/stickers/file/{group['pack']}/{group['emotion']}/{filename}",
        }

    def import_zip(self, source: str | Path, pack_name: str) -> dict:
        pack_name = self._safe_component(pack_name)
        target = (self.data_dir / pack_name).resolve()
        if target.parent != self.data_dir.resolve():
            raise ValueError("invalid pack name")
        target.mkdir(parents=True, exist_ok=True)
        count = 0
        unpacked = 0
        with zipfile.ZipFile(source) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = Path(info.filename)
                if name.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                if info.file_size > MAX_STICKER_SIZE:
                    raise ValueError("sticker image is too large")
                unpacked += max(0, info.file_size)
                if unpacked > MAX_UNPACKED_SIZE:
                    raise ValueError("sticker pack is too large")
                parts = name.parts
                emotion = parts[-2] if len(parts) >= 2 else "neutral"
                filename = parts[-1]
                try:
                    emotion = self._safe_component(emotion)
                    filename = self._safe_component(filename)
                except ValueError:
                    continue
                destination = (target / emotion / filename).resolve()
                if destination.parent.parent != target:
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, destination.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                count += 1
        return {"pack": pack_name, "images": count}
