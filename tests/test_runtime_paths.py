from pathlib import Path
import os
import subprocess
import sys

from core.runtime.paths import bootstrap_example_config, resolve_runtime_paths


def test_source_paths_remain_project_local(tmp_path):
    paths = resolve_runtime_paths(resource_dir=tmp_path / "app", environ={})
    assert paths.home_dir == (tmp_path / "app").resolve()
    assert paths.data_dir == paths.home_dir / "data"
    assert paths.portable is False


def test_portable_paths_use_bundle_userdata(tmp_path):
    bundle = tmp_path / "bundle"
    paths = resolve_runtime_paths(
        resource_dir=bundle / "app",
        environ={
            "CC_PORTABLE": "1",
            "CC_PORTABLE_ROOT": str(bundle),
        },
    )
    assert paths.portable is True
    assert paths.resource_dir == (bundle / "app").resolve()
    assert paths.home_dir == (bundle / "userdata").resolve()
    assert paths.config_dir == paths.home_dir / "config"


def test_explicit_home_overrides_platform_defaults(tmp_path):
    paths = resolve_runtime_paths(
        resource_dir=tmp_path / "app",
        environ={"CC_HOME": str(tmp_path / "custom-home")},
    )
    assert paths.home_dir == (tmp_path / "custom-home").resolve()


def test_packaged_windows_uses_appdata(tmp_path):
    paths = resolve_runtime_paths(
        resource_dir=tmp_path / "app",
        environ={"CC_PACKAGED": "1", "APPDATA": str(tmp_path / "Roaming")},
        platform_name="win32",
        user_home=tmp_path / "home",
    )
    assert paths.home_dir == (tmp_path / "Roaming" / "CyberCompanion").resolve()


def test_packaged_macos_uses_application_support(tmp_path):
    paths = resolve_runtime_paths(
        resource_dir=tmp_path / "app",
        environ={"CC_PACKAGED": "1"},
        platform_name="darwin",
        user_home=tmp_path / "home",
    )
    assert paths.home_dir == (
        tmp_path / "home" / "Library" / "Application Support" / "CyberCompanion"
    ).resolve()


def test_packaged_linux_respects_xdg_data_home(tmp_path):
    paths = resolve_runtime_paths(
        resource_dir=tmp_path / "app",
        environ={"CC_PACKAGED": "1", "XDG_DATA_HOME": str(tmp_path / "xdg-data")},
        platform_name="linux",
        user_home=tmp_path / "home",
    )
    assert paths.home_dir == (tmp_path / "xdg-data" / "CyberCompanion").resolve()


def test_portable_bootstrap_copies_examples_only_once(tmp_path):
    resource = tmp_path / "app"
    config = resource / "config"
    config.mkdir(parents=True)
    (config / "settings.example.json").write_text('{"advanced": {}}', encoding="utf-8")
    (config / "personas.example.json").write_text('{"personas": []}', encoding="utf-8")
    (config / "mcp_servers.example.json").write_text('{"servers": []}', encoding="utf-8")
    paths = resolve_runtime_paths(
        resource_dir=resource,
        environ={"CC_PORTABLE": "1", "CC_PORTABLE_ROOT": str(tmp_path)},
    )

    bootstrap_example_config(paths)
    settings = paths.config_dir / "settings.json"
    assert settings.read_text(encoding="utf-8") == '{"advanced": {}}'

    settings.write_text('{"advanced": {"keep": true}}', encoding="utf-8")
    bootstrap_example_config(paths)
    assert settings.read_text(encoding="utf-8") == '{"advanced": {"keep": true}}'


def test_main_import_reads_dotenv_from_portable_home(tmp_path):
    bundle = tmp_path / "bundle"
    home = bundle / "userdata"
    home.mkdir(parents=True)
    (home / ".env").write_text("CC_TEST_RUNTIME_KEY=portable-only\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "CC_PORTABLE": "1",
            "CC_PORTABLE_ROOT": str(bundle),
            "CC_RESOURCE_DIR": str(Path(__file__).resolve().parents[1]),
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", "import os, main; print(main.ROOT); print(os.getenv('CC_TEST_RUNTIME_KEY'))"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert str(bundle / "userdata") in result.stdout
    assert "portable-only" in result.stdout


def test_llm_import_does_not_search_parent_dotenv(tmp_path):
    nested = tmp_path / "parent" / "child"
    nested.mkdir(parents=True)
    (tmp_path / "parent" / ".env").write_text("CC_PARENT_SECRET=must-not-load\n", encoding="utf-8")
    env = os.environ.copy()
    env.pop("LITELLM_MODE", None)
    env.pop("CC_PARENT_SECRET", None)
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import os,sys; sys.path.insert(0, {str(root)!r}); import core.llm.base; print(os.getenv('CC_PARENT_SECRET', ''))",
        ],
        cwd=nested,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""
