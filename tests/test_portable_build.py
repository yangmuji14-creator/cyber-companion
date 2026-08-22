import zipfile
import hashlib
import json

import pytest

from scripts.build_portable import build


def test_portable_build_contains_code_runtime_and_no_user_data(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "python.exe").write_bytes(b"placeholder")

    archive = build(runtime, tmp_path / "out", "test")

    assert archive.exists()
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    assert checksum.exists()
    assert checksum.read_text(encoding="ascii").split()[0] == hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        manifest = json.loads(bundle.read("Mu/portable.json"))
    assert "Mu/app/main.py" in names
    assert "Mu/app/webui/static/index.html" in names
    assert "Mu/runtime/python.exe" in names
    assert "Mu/启动慕.cmd" in names
    assert manifest["target_platform"] == "windows"
    assert not any(name.startswith("Mu/data/") for name in names)
    assert not any("credentials" in name for name in names)
    assert not any("__tests__" in name for name in names)


def test_portable_build_accepts_unix_runtime_layout(tmp_path):
    runtime = tmp_path / "runtime"
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin" / "python").write_bytes(b"placeholder")

    archive = build(runtime, tmp_path / "out", "test", "linux")

    with zipfile.ZipFile(archive) as bundle:
        manifest = json.loads(bundle.read("Mu/portable.json"))
        assert manifest["target_platform"] == "linux"
        assert "Mu/runtime/bin/python" in bundle.namelist()
        assert "Mu/start.sh" in bundle.namelist()


def test_portable_build_rejects_wrong_runtime_layout(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "python.exe").write_bytes(b"placeholder")

    with pytest.raises(ValueError, match="linux runtime"):
        build(runtime, tmp_path / "out", "test", "linux")
