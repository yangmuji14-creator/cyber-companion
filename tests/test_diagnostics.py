import json
import sqlite3
from types import SimpleNamespace

from core.runtime.diagnostics import run_diagnostics, sanitize_settings
from core.security.secrets import SecretManager


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


def _components():
    return SimpleNamespace(
        registry=SimpleNamespace(available_models=["main"], default_model="main"),
        vision_manager=SimpleNamespace(main_is_multimodal=False),
        mcp_manager=SimpleNamespace(connected_count=3),
    )


def test_run_diagnostics_reports_database_and_secure_model(tmp_path):
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    data_dir.mkdir()
    database = data_dir / "companion.db"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version=3")
    manager = SecretManager(MemoryBackend({"model/main": "secret", "vision/default": "vision"}))
    settings = {
        "default_model": "main",
        "models": {"main": {"api_key": "", "api_key_ref": "model/main"}},
        "advanced": {"vision_model": {
            "model_name": "vision", "api_key": "", "api_key_ref": "vision/default",
        }},
    }

    report = run_diagnostics(
        _components(), data_dir=data_dir, config_dir=config_dir,
        settings=settings, secret_manager=manager,
    )

    checks = {item["id"]: item for item in report["checks"]}
    assert checks["database"]["status"] == "ok"
    assert checks["database"]["details"]["version"] == 3
    assert checks["model"]["status"] == "ok"
    assert checks["vision"]["status"] == "ok"
    assert checks["secrets"]["status"] == "ok"
    assert report["overall"] == "ok"


def test_sanitize_settings_redacts_nested_credentials():
    settings = {
        "models": {"main": {"api_key": "very-secret", "api_key_ref": "model/main"}},
        "advanced": {"token": "private", "normal": "visible"},
    }

    sanitized = sanitize_settings(settings)

    assert sanitized["models"]["main"]["api_key"] == "[已配置]"
    assert sanitized["models"]["main"]["api_key_ref"] == "model/main"
    assert sanitized["advanced"]["token"] == "[已配置]"
    assert sanitized["advanced"]["normal"] == "visible"
    assert "very-secret" not in json.dumps(sanitized)
