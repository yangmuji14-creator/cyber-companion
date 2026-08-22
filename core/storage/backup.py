"""Portable, consistent local data backups for Mu (慕)."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from .constants import CONSOLIDATED_DB_NAME, LEGACY_DB_NAMES


BACKUP_FORMAT_VERSION = 2
SUPPORTED_BACKUP_FORMAT_VERSIONS = {1, BACKUP_FORMAT_VERSION}
MAX_BACKUPS = 10
_RESTORABLE_PREFIXES = ("data/", "config/")
PENDING_RESTORE_DIRNAME = ".pending_restore"
PENDING_RESTORE_ARCHIVE = "backup.zip"
PENDING_RESTORE_MARKER = "request.json"


class BackupValidationError(ValueError):
    """The archive is not a Mu backup that can be restored."""


def _snapshot_database(source: Path, destination: Path) -> None:
    """Copy a live SQLite database through SQLite's backup API, including WAL data."""
    source_conn = sqlite3.connect(source)
    target_conn = sqlite3.connect(destination)
    try:
        source_conn.backup(target_conn)
    finally:
        # sqlite3 connection context managers commit/rollback but do not close.
        # Explicit close releases the snapshot on Windows before it is zipped.
        target_conn.close()
        source_conn.close()


def _prune_old_backups(directory: Path) -> None:
    backups = sorted(
        [*directory.glob("mu-*.zip"), *directory.glob("cyber-companion-*.zip")],
        key=lambda item: item.stat().st_mtime,
    )
    for old_backup in backups[:-MAX_BACKUPS]:
        old_backup.unlink(missing_ok=True)


def create_backup(data_dir: Path, config_dir: Path) -> Path:
    """Create a portable ZIP without copying volatile WAL/SHM sidecar files.

    SQLite files are snapshotted transactionally. Configuration, chat history and
    identity files are included as-is. Credentials and log files are deliberately
    excluded: they are secrets or disposable runtime state, not user content.
    """
    data_dir = Path(data_dir)
    config_dir = Path(config_dir)
    backup_dir = data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    _prune_old_backups(backup_dir)

    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    filename = f"mu-{datetime.now():%Y%m%d-%H%M%S-%f}.zip"
    backup_path = backup_dir / filename
    manifest: dict[str, object] = {
        "format_version": BACKUP_FORMAT_VERSION,
        "created_at": created_at,
        "included": [],
        "excluded": ["data/credentials", "data/logs", "data/uploads", "*.db-wal", "*.db-shm"],
    }

    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        databases = sorted(data_dir.glob("*.db"))
        if (data_dir / CONSOLIDATED_DB_NAME).exists():
            databases = [
                database for database in databases
                if database.name not in LEGACY_DB_NAMES
            ]
        for database in databases:
            temp_snapshot = backup_dir / f".{database.name}.snapshot"
            try:
                _snapshot_database(database, temp_snapshot)
                archive.write(temp_snapshot, arcname=f"data/{database.name}")
                manifest["included"].append(f"data/{database.name}")
            finally:
                temp_snapshot.unlink(missing_ok=True)

        for path in (data_dir / "conversations.json",):
            if path.exists():
                archive.write(path, arcname=f"data/{path.name}")
                manifest["included"].append(f"data/{path.name}")

        for directory_name in ("chat_history", "identities", "life_summaries", "avatars"):
            directory = data_dir / directory_name
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if path.is_file():
                    relative = path.relative_to(data_dir).as_posix()
                    archive.write(path, arcname=f"data/{relative}")
                    manifest["included"].append(f"data/{relative}")

        for filename in ("personas.json", "settings.json", "mcp_servers.json"):
            path = config_dir / filename
            if path.exists():
                archive.write(path, arcname=f"config/{filename}")
                manifest["included"].append(f"config/{filename}")

        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return backup_path


def inspect_backup(archive_path: Path) -> dict:
    """Validate an archive before any restore action and return its manifest."""
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if "manifest.json" not in names:
                raise BackupValidationError("missing manifest")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format_version") not in SUPPORTED_BACKUP_FORMAT_VERSIONS:
                raise BackupValidationError("unsupported backup format")
            for name in names:
                if name == "manifest.json":
                    continue
                normalized = Path(name)
                if normalized.is_absolute() or ".." in normalized.parts:
                    raise BackupValidationError("unsafe archive path")
                if not name.startswith(_RESTORABLE_PREFIXES):
                    raise BackupValidationError("unexpected archive content")
            return manifest
    except zipfile.BadZipFile as e:
        raise BackupValidationError("invalid zip archive") from e


def pending_restore_status(data_dir: Path) -> dict | None:
    """Return queued offline restore metadata, if it is still valid."""
    pending_dir = Path(data_dir) / PENDING_RESTORE_DIRNAME
    marker_path = pending_dir / PENDING_RESTORE_MARKER
    archive_path = pending_dir / PENDING_RESTORE_ARCHIVE
    if not marker_path.exists() or not archive_path.exists():
        return None
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        manifest = inspect_backup(archive_path)
    except (OSError, json.JSONDecodeError, BackupValidationError):
        return None
    return {**marker, "manifest": manifest, "pending": True}


def schedule_restore(archive_path: Path, data_dir: Path) -> dict:
    """Queue a validated archive for restore before the next application start."""
    archive_path = Path(archive_path)
    manifest = inspect_backup(archive_path)
    pending_dir = Path(data_dir) / PENDING_RESTORE_DIRNAME
    pending_dir.mkdir(parents=True, exist_ok=True)
    staged_archive = pending_dir / f".{PENDING_RESTORE_ARCHIVE}.tmp"
    final_archive = pending_dir / PENDING_RESTORE_ARCHIVE
    marker_path = pending_dir / PENDING_RESTORE_MARKER
    marker_tmp = pending_dir / f".{PENDING_RESTORE_MARKER}.tmp"

    shutil.copyfile(archive_path, staged_archive)
    os.replace(staged_archive, final_archive)
    marker = {
        "scheduled_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_name": archive_path.name,
    }
    marker_tmp.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(marker_tmp, marker_path)
    return {**marker, "manifest": manifest, "pending": True}


def apply_pending_restore(data_dir: Path, config_dir: Path) -> dict | None:
    """Apply a queued restore while no application database connections are open."""
    pending_dir = Path(data_dir) / PENDING_RESTORE_DIRNAME
    archive_path = pending_dir / PENDING_RESTORE_ARCHIVE
    marker_path = pending_dir / PENDING_RESTORE_MARKER
    if not archive_path.exists() or not marker_path.exists():
        return None

    result = restore_backup(archive_path, data_dir, config_dir)
    marker_path.unlink(missing_ok=True)
    archive_path.unlink(missing_ok=True)
    try:
        pending_dir.rmdir()
    except OSError:
        pass
    return result


def restore_backup(archive_path: Path, data_dir: Path, config_dir: Path) -> dict:
    """Restore a validated archive while the application is offline.

    A safety backup is created before any replacement. Files are extracted into
    a staging directory and atomically moved into place one by one.
    """
    archive_path = Path(archive_path)
    data_dir = Path(data_dir)
    config_dir = Path(config_dir)
    manifest = inspect_backup(archive_path)
    safety_backup = create_backup(data_dir, config_dir)
    restored: list[str] = []

    with tempfile.TemporaryDirectory(prefix="cc-restore-", dir=str(data_dir.parent)) as temp_dir:
        staging = Path(temp_dir)
        with zipfile.ZipFile(archive_path) as archive:
            for name in archive.namelist():
                if name == "manifest.json" or name.endswith("/"):
                    continue
                relative = Path(name)
                staged = staging / relative
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(archive.read(name))

        staged_data = staging / "data"
        staged_names = {
            path.name for path in staged_data.glob("*.db")
        } if staged_data.exists() else set()
        has_consolidated = CONSOLIDATED_DB_NAME in staged_names
        has_legacy = bool(staged_names.intersection(LEGACY_DB_NAMES))

        # A v1 backup contains only legacy domain databases. Remove the current
        # consolidated store so the next startup imports into a clean database.
        if has_legacy and not has_consolidated:
            for suffix in ("", "-wal", "-shm"):
                Path(f"{data_dir / CONSOLIDATED_DB_NAME}{suffix}").unlink(
                    missing_ok=True
                )
        elif has_consolidated:
            # A v2 backup is authoritative; stale top-level legacy files must
            # not be imported after the restored consolidated store opens.
            for legacy_name in LEGACY_DB_NAMES:
                for suffix in ("", "-wal", "-shm"):
                    Path(f"{data_dir / legacy_name}{suffix}").unlink(
                        missing_ok=True
                    )

        for root_name, destination_root in (("data", data_dir), ("config", config_dir)):
            source_root = staging / root_name
            if not source_root.exists():
                continue
            for source in source_root.rglob("*"):
                if not source.is_file():
                    continue
                relative = source.relative_to(source_root)
                destination = destination_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, destination)
                restored.append(f"{root_name}/{relative.as_posix()}")

    return {
        "restored": restored,
        "manifest": manifest,
        "safety_backup": str(safety_backup),
    }
