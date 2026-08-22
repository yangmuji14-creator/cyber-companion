"""Cross-platform secret storage with legacy plaintext compatibility.

The application never requires a secure backend to start. New credentials are
stored in the operating system backend when available; otherwise callers keep
the existing ``api_key`` field. Reading always falls back to that legacy field,
so upgrades cannot strand an existing installation.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import subprocess
import sys
import threading
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from loguru import logger

from core.runtime.paths import resolve_runtime_paths


SERVICE_NAME = "CyberCompanion"


class SecretBackend(Protocol):
    name: str
    available: bool

    def get(self, reference: str) -> str: ...
    def set(self, reference: str, value: str) -> None: ...
    def delete(self, reference: str) -> None: ...


class UnavailableBackend:
    name = "legacy-plaintext"
    available = False

    def get(self, reference: str) -> str:
        return ""

    def set(self, reference: str, value: str) -> None:
        raise RuntimeError("secure secret storage is unavailable")

    def delete(self, reference: str) -> None:
        return None


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _windows_dpapi(data: bytes, *, decrypt: bool) -> bytes:
    """Protect or unprotect bytes for the current Windows user."""
    buffer = ctypes.create_string_buffer(data)
    in_blob = _DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    out_blob = _DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if decrypt:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        )
    else:
        ok = crypt32.CryptProtectData(
            ctypes.byref(in_blob), SERVICE_NAME, None, None, None, 0, ctypes.byref(out_blob)
        )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


class WindowsDpapiBackend:
    name = "windows-dpapi"
    available = sys.platform == "win32"

    def __init__(self, config_dir: Path):
        self._path = config_dir / "secrets.dpapi"
        self._lock = threading.RLock()

    def _read(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        encrypted = base64.b64decode(self._path.read_bytes(), validate=True)
        payload = _windows_dpapi(encrypted, decrypt=True)
        parsed = json.loads(payload.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}

    def _write(self, values: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8")
        encrypted = base64.b64encode(_windows_dpapi(payload, decrypt=False))
        temp = self._path.with_suffix(".tmp")
        temp.write_bytes(encrypted)
        temp.replace(self._path)

    def get(self, reference: str) -> str:
        with self._lock:
            return str(self._read().get(reference) or "")

    def set(self, reference: str, value: str) -> None:
        with self._lock:
            values = self._read()
            values[reference] = value
            self._write(values)

    def delete(self, reference: str) -> None:
        with self._lock:
            values = self._read()
            if reference in values:
                del values[reference]
                self._write(values)


class MacOSKeychainBackend:
    name = "macos-keychain"
    available = sys.platform == "darwin" and bool(shutil.which("security"))

    @staticmethod
    def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["security", *args], capture_output=True, text=True, timeout=10, check=False
        )

    def get(self, reference: str) -> str:
        result = self._run(["find-generic-password", "-a", reference, "-s", SERVICE_NAME, "-w"])
        return result.stdout.strip() if result.returncode == 0 else ""

    def set(self, reference: str, value: str) -> None:
        result = self._run([
            "add-generic-password", "-U", "-a", reference, "-s", SERVICE_NAME, "-w", value,
        ])
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Keychain write failed")

    def delete(self, reference: str) -> None:
        self._run(["delete-generic-password", "-a", reference, "-s", SERVICE_NAME])


class LinuxSecretServiceBackend:
    name = "linux-secret-service"
    available = sys.platform.startswith("linux") and bool(shutil.which("secret-tool"))

    @staticmethod
    def _run(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["secret-tool", *args], input=input_text, capture_output=True,
            text=True, timeout=10, check=False,
        )

    def get(self, reference: str) -> str:
        result = self._run(["lookup", "service", SERVICE_NAME, "account", reference])
        return result.stdout.strip() if result.returncode == 0 else ""

    def set(self, reference: str, value: str) -> None:
        result = self._run(
            ["store", f"--label={SERVICE_NAME}", "service", SERVICE_NAME, "account", reference],
            input_text=value,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Secret Service write failed")

    def delete(self, reference: str) -> None:
        self._run(["clear", "service", SERVICE_NAME, "account", reference])


@dataclass(frozen=True)
class SecretStoreStatus:
    backend: str
    available: bool


class SecretManager:
    """Small failure-contained facade around one platform backend."""

    def __init__(self, backend: SecretBackend):
        self.backend = backend

    @property
    def status(self) -> SecretStoreStatus:
        return SecretStoreStatus(self.backend.name, bool(self.backend.available))

    def get(self, reference: str) -> str:
        if not self.backend.available or not reference:
            return ""
        try:
            return self.backend.get(reference)
        except Exception as exc:
            logger.warning("Secret read failed via {}: {}", self.backend.name, exc)
            return ""

    def set(self, reference: str, value: str) -> bool:
        if not self.backend.available or not reference or not value:
            return False
        try:
            self.backend.set(reference, value)
            return self.backend.get(reference) == value
        except Exception as exc:
            logger.warning("Secret write failed via {}: {}", self.backend.name, exc)
            return False

    def delete(self, reference: str) -> bool:
        if not self.backend.available or not reference:
            return False
        try:
            self.backend.delete(reference)
            return True
        except Exception as exc:
            logger.warning("Secret delete failed via {}: {}", self.backend.name, exc)
            return False


_managers: dict[Path, SecretManager] = {}
_manager_lock = threading.Lock()


def _select_backend(config_dir: Path) -> SecretBackend:
    if sys.platform == "win32":
        return WindowsDpapiBackend(config_dir)
    if sys.platform == "darwin" and MacOSKeychainBackend.available:
        return MacOSKeychainBackend()
    if sys.platform.startswith("linux") and LinuxSecretServiceBackend.available:
        return LinuxSecretServiceBackend()
    return UnavailableBackend()


def get_secret_manager(config_dir: str | Path | None = None) -> SecretManager:
    path = Path(config_dir or resolve_runtime_paths().config_dir).expanduser().resolve()
    with _manager_lock:
        if path not in _managers:
            _managers[path] = SecretManager(_select_backend(path))
        return _managers[path]


def model_secret_ref(model_key: str) -> str:
    return f"model/{model_key.strip()}"


def vision_secret_ref() -> str:
    return "vision/default"


def resolve_config_secret(
    config: dict | None,
    *,
    env_value: str = "",
    manager: SecretManager | None = None,
) -> str:
    values = config if isinstance(config, dict) else {}
    if env_value:
        return env_value
    reference = str(values.get("api_key_ref") or "")
    if reference:
        secret = (manager or get_secret_manager()).get(reference)
        if secret:
            return secret
    return str(values.get("api_key") or "")


def protect_config_secret(
    config: dict,
    reference: str,
    *,
    value: str | None = None,
    manager: SecretManager | None = None,
) -> tuple[dict, bool]:
    """Return a protected config, or a legacy-compatible plaintext config."""
    result = dict(config)
    candidate = str(result.get("api_key") or "") if value is None else str(value or "")
    existing_ref = str(result.get("api_key_ref") or "")
    secret_manager = manager or get_secret_manager()

    if not candidate:
        if existing_ref and secret_manager.get(existing_ref):
            result["api_key"] = ""
            return result, True
        return result, False

    if secret_manager.set(reference, candidate):
        result["api_key_ref"] = reference
        result["api_key"] = ""
        return result, True

    # Never discard the working credential when the platform store fails.
    result["api_key"] = candidate
    result.pop("api_key_ref", None)
    return result, False


def migrate_settings_secrets(
    settings: dict,
    *,
    manager: SecretManager | None = None,
) -> tuple[dict, dict[str, int | str | bool]]:
    """Best-effort migration of legacy model and vision credentials."""
    result = json.loads(json.dumps(settings))
    secret_manager = manager or get_secret_manager()
    protected = 0
    plaintext = 0
    changed = False

    models = result.get("models", {})
    if isinstance(models, dict):
        for key, config in models.items():
            if not isinstance(config, dict):
                continue
            legacy = str(config.get("api_key") or "")
            if legacy:
                updated, secure = protect_config_secret(
                    config, model_secret_ref(str(key)), manager=secret_manager
                )
                if secure:
                    models[key] = updated
                    changed = changed or updated != config
                    protected += 1
                else:
                    plaintext += 1
            elif config.get("api_key_ref"):
                protected += 1 if secret_manager.get(str(config["api_key_ref"])) else 0

    vision = result.get("advanced", {}).get("vision_model")
    if isinstance(vision, dict):
        legacy = str(vision.get("api_key") or "")
        if legacy:
            updated, secure = protect_config_secret(
                vision, vision_secret_ref(), manager=secret_manager
            )
            if secure:
                result.setdefault("advanced", {})["vision_model"] = updated
                changed = changed or updated != vision
                protected += 1
            else:
                plaintext += 1
        elif vision.get("api_key_ref"):
            protected += 1 if secret_manager.get(str(vision["api_key_ref"])) else 0

    return result, {
        "changed": changed,
        "backend": secret_manager.status.backend,
        "available": secret_manager.status.available,
        "protected": protected,
        "plaintext": plaintext,
    }
