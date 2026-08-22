"""Cross-platform application paths.

The source checkout keeps its historical ``config/``, ``data/`` and ``logs/``
layout for backwards compatibility. Packaged builds set ``CC_PORTABLE=1`` and
store writable state in a sibling ``userdata/`` directory instead. A future
desktop installer can set ``CC_HOME`` without changing any business module.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "CyberCompanion"


@dataclass(frozen=True)
class RuntimePaths:
    """Read-only resources and writable user state for one application run."""

    resource_dir: Path
    home_dir: Path
    data_dir: Path
    config_dir: Path
    logs_dir: Path
    cache_dir: Path
    portable: bool = False


def _source_dir() -> Path:
    # core/runtime/paths.py -> project root
    return Path(__file__).resolve().parents[2]


def _platform_home(
    *,
    environ: dict[str, str] | None = None,
    platform_name: str | None = None,
    user_home: str | Path | None = None,
) -> Path:
    """Return a platform default using injectable inputs for release tests."""
    env = os.environ if environ is None else environ
    current_platform = platform_name or sys.platform
    home = Path(user_home).expanduser() if user_home is not None else Path.home()
    override = env.get("CC_HOME", "").strip()
    if override:
        return Path(override).expanduser()

    if current_platform == "win32":
        base = env.get("APPDATA") or env.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_NAME
        return home / "AppData" / "Roaming" / APP_NAME
    if current_platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME

    base = env.get("XDG_DATA_HOME", "").strip()
    return (Path(base).expanduser() if base else home / ".local" / "share") / APP_NAME


def resolve_runtime_paths(
    *,
    resource_dir: str | Path | None = None,
    environ: dict[str, str] | None = None,
    platform_name: str | None = None,
    user_home: str | Path | None = None,
) -> RuntimePaths:
    """Resolve paths without creating files.

    ``environ`` is injectable so path behavior can be tested without mutating
    process-global environment variables.
    """
    env = os.environ if environ is None else environ
    resources = Path(resource_dir or env.get("CC_RESOURCE_DIR") or _source_dir()).expanduser().resolve()
    portable = env.get("CC_PORTABLE", "").lower() in {"1", "true", "yes", "on"}

    if portable:
        portable_root = Path(env.get("CC_PORTABLE_ROOT") or resources.parent).expanduser().resolve()
        home = Path(env.get("CC_HOME") or portable_root / "userdata").expanduser().resolve()
    elif env.get("CC_HOME"):
        home = Path(env["CC_HOME"]).expanduser().resolve()
    elif env.get("CC_PACKAGED", "").lower() in {"1", "true", "yes", "on"}:
        home = _platform_home(
            environ=env,
            platform_name=platform_name,
            user_home=user_home,
        ).resolve()
    else:
        # Source checkout compatibility: existing user data stays untouched.
        home = resources

    return RuntimePaths(
        resource_dir=resources,
        home_dir=home,
        data_dir=home / "data",
        config_dir=home / "config",
        logs_dir=home / "logs",
        cache_dir=home / "cache",
        portable=portable,
    )


def ensure_user_directories(paths: RuntimePaths) -> None:
    """Create writable directories at the application boundary."""
    for directory in (paths.home_dir, paths.data_dir, paths.config_dir, paths.logs_dir, paths.cache_dir):
        directory.mkdir(parents=True, exist_ok=True)


def bootstrap_example_config(paths: RuntimePaths) -> None:
    """Copy packaged examples into a portable user's config on first launch."""
    if not paths.portable:
        return
    ensure_user_directories(paths)
    examples = {
        "settings.example.json": "settings.json",
        "personas.example.json": "personas.json",
        "mcp_servers.example.json": "mcp_servers.json",
    }
    for source_name, target_name in examples.items():
        source = paths.resource_dir / "config" / source_name
        target = paths.config_dir / target_name
        if source.exists() and not target.exists():
            target.write_bytes(source.read_bytes())
