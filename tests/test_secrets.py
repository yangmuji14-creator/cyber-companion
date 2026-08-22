import json
import sys

import pytest

from core.security.secrets import (
    SecretManager,
    WindowsDpapiBackend,
    migrate_settings_secrets,
    model_secret_ref,
    protect_config_secret,
    resolve_config_secret,
    vision_secret_ref,
)


class MemoryBackend:
    name = "memory"
    available = True

    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, reference):
        return self.values.get(reference, "")

    def set(self, reference, value):
        self.values[reference] = value

    def delete(self, reference):
        self.values.pop(reference, None)


class FailingBackend(MemoryBackend):
    name = "failing"

    def set(self, reference, value):
        raise RuntimeError("backend unavailable")


def test_protect_and_resolve_config_secret():
    manager = SecretManager(MemoryBackend())

    protected, secure = protect_config_secret(
        {"api_key": "secret", "model_name": "demo"},
        model_secret_ref("main"),
        manager=manager,
    )

    assert secure is True
    assert protected["api_key"] == ""
    assert protected["api_key_ref"] == "model/main"
    assert resolve_config_secret(protected, manager=manager) == "secret"


def test_failed_secret_write_keeps_legacy_plaintext():
    manager = SecretManager(FailingBackend())

    protected, secure = protect_config_secret(
        {"api_key": "keep-working"}, "model/main", manager=manager,
    )

    assert secure is False
    assert protected == {"api_key": "keep-working"}


def test_missing_secure_reference_falls_back_to_legacy_value():
    manager = SecretManager(MemoryBackend())
    config = {"api_key_ref": "model/missing", "api_key": "legacy"}

    assert resolve_config_secret(config, manager=manager) == "legacy"
    assert resolve_config_secret(config, env_value="environment", manager=manager) == "environment"


def test_migrate_settings_protects_model_and_vision_without_mutating_input():
    manager = SecretManager(MemoryBackend())
    settings = {
        "models": {"main": {"model_name": "demo", "api_key": "model-key"}},
        "advanced": {"vision_model": {"model_name": "vision", "api_key": "vision-key"}},
    }

    migrated, report = migrate_settings_secrets(settings, manager=manager)

    assert settings["models"]["main"]["api_key"] == "model-key"
    assert migrated["models"]["main"]["api_key_ref"] == model_secret_ref("main")
    assert migrated["models"]["main"]["api_key"] == ""
    assert migrated["advanced"]["vision_model"]["api_key_ref"] == vision_secret_ref()
    assert report == {
        "changed": True,
        "backend": "memory",
        "available": True,
        "protected": 2,
        "plaintext": 0,
    }


def test_registry_loads_api_key_reference(tmp_path, monkeypatch):
    import core.llm.registry as registry_module

    manager = SecretManager(MemoryBackend({"model/secure": "resolved-key"}))
    monkeypatch.setattr(registry_module, "get_secret_manager", lambda _path=None: manager)
    monkeypatch.delenv("SECURE_API_KEY", raising=False)
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "default_model": "secure",
        "models": {"secure": {
            "provider": "openai",
            "model_name": "demo-model",
            "base_url": "https://example.test/v1",
            "api_key": "",
            "api_key_ref": "model/secure",
        }},
    }), encoding="utf-8")

    registry = registry_module.LLMRegistry(settings_file)

    assert registry.get().api_key == "resolved-key"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI only")
def test_windows_dpapi_backend_round_trip(tmp_path):
    backend = WindowsDpapiBackend(tmp_path)

    backend.set("model/main", "dpapi-secret")

    assert backend.get("model/main") == "dpapi-secret"
    raw = (tmp_path / "secrets.dpapi").read_text(encoding="ascii")
    assert "dpapi-secret" not in raw
    backend.delete("model/main")
    assert backend.get("model/main") == ""
