"""Prepare a self-contained Windows CPython runtime for portable releases.

This is a release-engineering tool. End users receive the finished zip and do
not run this script or download Python packages.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PYTHON_VERSION = "3.12.10"
MIRRORS = (
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple",
    "https://pypi.org/simple",
)
PYTHON_ARCHIVE_URLS = (
    "https://registry.npmmirror.com/-/binary/python/{version}/python-{version}-embed-amd64.zip",
    "https://www.python.org/ftp/python/{version}/python-{version}-embed-amd64.zip",
)


def _download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mu-ReleaseBuilder/1"})
    partial = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(request, timeout=30) as response, partial.open("wb") as output:
        shutil.copyfileobj(response, output)
    if not zipfile.is_zipfile(partial):
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"下载内容不是有效的 ZIP: {url}")
    os.replace(partial, target)


def _python_archive(
    python_version: str,
    download_cache: Path,
    supplied_archive: Path | None,
) -> Path:
    if supplied_archive:
        archive = supplied_archive.resolve()
        if not archive.is_file() or not zipfile.is_zipfile(archive):
            raise RuntimeError(f"指定的 Python 运行时压缩包无效: {archive}")
        return archive

    download_cache.mkdir(parents=True, exist_ok=True)
    archive = download_cache / f"python-{python_version}-embed-amd64.zip"
    if archive.is_file() and zipfile.is_zipfile(archive):
        return archive
    archive.unlink(missing_ok=True)

    failures: list[str] = []
    for template in PYTHON_ARCHIVE_URLS:
        url = template.format(version=python_version)
        try:
            print(f"下载 Python 运行时: {url}")
            _download(url, archive)
            return archive
        except Exception as exc:
            failures.append(f"{url}: {exc}")
            archive.with_suffix(archive.suffix + ".part").unlink(missing_ok=True)
    raise RuntimeError("Python 运行时下载失败:\n" + "\n".join(failures))


def prepare(
    output: Path,
    python_version: str,
    index_url: str = "",
    wheelhouse: Path | None = None,
    python_archive: Path | None = None,
    download_cache: Path | None = None,
) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("Windows runtime must be prepared on Windows")
    host_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    target_minor = ".".join(python_version.split(".")[:2])
    if host_minor != target_minor:
        raise RuntimeError(f"构建 Python {python_version} 需要 Python {target_minor} 构建机，当前为 {host_minor}")

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    cache = (download_cache or ROOT / "build" / "downloads").resolve()
    archive = _python_archive(python_version, cache, python_archive)

    # Build beside the destination and only replace it after every check passes.
    # A failed download or dependency install therefore keeps the last runtime.
    staging_parent = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    staging = staging_parent / "runtime"
    staging.mkdir()
    try:
        with zipfile.ZipFile(archive) as source:
            source.extractall(staging)

        minor_tag = target_minor.replace(".", "")
        pth = staging / f"python{minor_tag}._pth"
        if not pth.exists():
            raise RuntimeError(f"嵌入式运行时缺少 {pth.name}")
        lines = [line for line in pth.read_text(encoding="utf-8").splitlines() if line.strip() != "#import site"]
        if "Lib\\site-packages" not in lines:
            lines.append("Lib\\site-packages")
        if "import site" not in lines:
            lines.append("import site")
        pth.write_text("\n".join(lines) + "\n", encoding="utf-8")

        site_packages = staging / "Lib" / "site-packages"
        site_packages.mkdir(parents=True)
        indexes = (index_url,) if index_url else MIRRORS
        last_error = 1
        install_prefix = [
            sys.executable, "-m", "pip", "install",
            "--disable-pip-version-check", "--no-compile", "--ignore-installed",
            "--only-binary", ":all:",
            "--target", str(site_packages),
        ]
        if wheelhouse:
            wheelhouse = wheelhouse.resolve()
            if not wheelhouse.is_dir():
                raise RuntimeError(f"离线 wheel 目录不存在: {wheelhouse}")
            command = install_prefix + ["--no-index", "--find-links", str(wheelhouse), "-r", str(ROOT / "requirements.txt")]
            last_error = subprocess.run(command, cwd=str(ROOT)).returncode
        for index in (() if wheelhouse else indexes):
            command = [
                *install_prefix,
                "--index-url", index,
                "--retries", "1", "--timeout", "30",
                "-r", str(ROOT / "requirements.txt"),
            ]
            last_error = subprocess.run(command, cwd=str(ROOT)).returncode
            if last_error == 0:
                break
        if last_error:
            raise RuntimeError("核心依赖安装失败")

        runtime_python = staging / "python.exe"
        check = subprocess.run(
            [str(runtime_python), "-c", "import aiohttp, litellm, numpy, pydantic, dotenv, loguru; print('runtime ok')"],
            capture_output=True, text=True,
        )
        if check.returncode:
            raise RuntimeError(f"运行时自检失败: {check.stderr.strip()}")

        previous = output.with_name(f".{output.name}.previous")
        if previous.exists():
            shutil.rmtree(previous)
        if output.exists():
            output.replace(previous)
        try:
            staging.replace(output)
        except Exception:
            if previous.exists() and not output.exists():
                previous.replace(output)
            raise
        if previous.exists():
            shutil.rmtree(previous)
        return output
    finally:
        shutil.rmtree(staging_parent, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="准备 Windows 便携 Python 运行时")
    parser.add_argument("--output", type=Path, default=Path("build/windows-runtime"))
    parser.add_argument("--python-version", default=DEFAULT_PYTHON_VERSION)
    parser.add_argument("--index-url", default="")
    parser.add_argument("--wheelhouse", type=Path, help="已下载的离线 wheel 目录")
    parser.add_argument("--python-archive", type=Path, help="已下载的官方嵌入式 Python ZIP")
    parser.add_argument("--download-cache", type=Path, default=Path("build/downloads"))
    args = parser.parse_args()
    output = prepare(
        args.output,
        args.python_version,
        args.index_url,
        args.wheelhouse,
        args.python_archive,
        args.download_cache,
    )
    print(f"Windows 运行时已准备: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
