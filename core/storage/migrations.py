"""Schema tracking and transactional legacy-database consolidation."""

from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from loguru import logger

from .constants import CONSOLIDATED_DB_NAME, LEGACY_TABLE_MAPPINGS


SCHEMA_VERSION = 3


@dataclass
class ConsolidationReport:
    target: Path
    migrated: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    archived_to: Path | None = None


def apply_schema_migrations(conn: sqlite3.Connection) -> None:
    """Apply append-only metadata migrations to a managed SQLite database."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS legacy_database_migrations (
            source_file TEXT NOT NULL,
            source_table TEXT NOT NULL,
            target_table TEXT NOT NULL,
            source_rows INTEGER NOT NULL,
            inserted_rows INTEGER NOT NULL,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (source_file, source_table)
        )
        """
    )
    # v3: diaries belong to the persona that authored them. Existing rows keep
    # an empty persona_id and remain visible through the compatibility path.
    if _table_exists(conn, "main", "life_summaries"):
        columns = set(_table_columns(conn, "main", "life_summaries"))
        if "persona_id" not in columns:
            conn.execute(
                "ALTER TABLE life_summaries "
                "ADD COLUMN persona_id TEXT NOT NULL DEFAULT ''"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_summaries_user_persona "
            "ON life_summaries(user_id, persona_id, created_at)"
        )
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
        (SCHEMA_VERSION,),
    )
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _table_exists(conn: sqlite3.Connection, schema: str, table: str) -> bool:
    row = conn.execute(
        f"SELECT 1 FROM {_quote_identifier(schema)}.sqlite_master "
        "WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, schema: str, table: str) -> list[str]:
    return [
        row[1]
        for row in conn.execute(
            f"PRAGMA {_quote_identifier(schema)}.table_info({_quote_identifier(table)})"
        ).fetchall()
    ]


def _create_target_from_legacy(
    conn: sqlite3.Connection,
    schema: str,
    source_table: str,
    target_table: str,
) -> None:
    if _table_exists(conn, "main", target_table):
        return
    row = conn.execute(
        f"SELECT sql FROM {_quote_identifier(schema)}.sqlite_master "
        "WHERE type='table' AND name=?",
        (source_table,),
    ).fetchone()
    if not row or not row[0] or "(" not in row[0]:
        raise sqlite3.DatabaseError(
            f"missing schema for {schema}.{source_table}"
        )
    definition = row[0][row[0].find("("):]
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {_quote_identifier(target_table)} {definition}"
    )


def _copy_legacy_table(
    conn: sqlite3.Connection,
    schema: str,
    source_file: str,
    source_table: str,
    target_table: str,
) -> tuple[int, int]:
    _create_target_from_legacy(conn, schema, source_table, target_table)
    source_columns = _table_columns(conn, schema, source_table)
    target_columns = set(_table_columns(conn, "main", target_table))
    columns = [column for column in source_columns if column in target_columns]
    if not columns:
        raise sqlite3.DatabaseError(
            f"no compatible columns for {source_file}:{source_table}"
        )
    source_rows = int(conn.execute(
        f"SELECT COUNT(*) FROM {_quote_identifier(schema)}."
        f"{_quote_identifier(source_table)}"
    ).fetchone()[0])
    quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
    before = conn.total_changes
    conn.execute(
        f"INSERT OR IGNORE INTO {_quote_identifier(target_table)} ({quoted_columns}) "
        f"SELECT {quoted_columns} FROM {_quote_identifier(schema)}."
        f"{_quote_identifier(source_table)}"
    )
    inserted_rows = conn.total_changes - before
    conn.execute(
        """
        INSERT INTO legacy_database_migrations
            (source_file, source_table, target_table, source_rows, inserted_rows)
        VALUES (?, ?, ?, ?, ?)
        """,
        (source_file, source_table, target_table, source_rows, inserted_rows),
    )
    return source_rows, inserted_rows


def _archive_legacy_files(data_dir: Path, source_files: list[Path]) -> Path | None:
    if not source_files:
        return None
    archive_dir = (
        data_dir / "legacy_databases" /
        datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    )
    archive_dir.mkdir(parents=True, exist_ok=False)
    moved = False
    for source in source_files:
        for candidate in (source, Path(f"{source}-wal"), Path(f"{source}-shm")):
            if not candidate.exists():
                continue
            try:
                shutil.move(str(candidate), archive_dir / candidate.name)
                moved = True
            except OSError as e:
                logger.warning(f"Could not archive legacy database {candidate}: {e}")
    if not moved:
        archive_dir.rmdir()
        return None
    return archive_dir


def consolidate_legacy_databases(
    data_dir: str | Path,
    *,
    archive: bool = True,
) -> ConsolidationReport:
    """Import known legacy SQLite stores into one database transactionally.

    A new installation is created through a temporary database and atomically
    renamed. Existing consolidated stores receive each legacy source at most
    once, tracked by ``legacy_database_migrations``. Source files are archived
    only after commit and ``PRAGMA integrity_check`` succeed.
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / CONSOLIDATED_DB_NAME
    sources = [
        (data_dir / filename, filename, source_table, target_table)
        for filename, source_table, target_table in LEGACY_TABLE_MAPPINGS
        if (data_dir / filename).exists()
    ]
    report = ConsolidationReport(target=target)
    if not sources:
        return report

    is_new = not target.exists()
    work_target = target.with_name(f".{target.name}.migrating") if is_new else target
    if is_new:
        for candidate in (
            work_target, Path(f"{work_target}-wal"), Path(f"{work_target}-shm")
        ):
            candidate.unlink(missing_ok=True)

    conn = sqlite3.connect(work_target, timeout=30)
    attached: list[str] = []
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        if is_new:
            conn.execute("PRAGMA journal_mode=DELETE")
        apply_schema_migrations(conn)
        conn.commit()

        pending = []
        for source_path, filename, source_table, target_table in sources:
            migrated = conn.execute(
                "SELECT 1 FROM legacy_database_migrations "
                "WHERE source_file=? AND source_table=?",
                (filename, source_table),
            ).fetchone()
            if migrated:
                report.skipped.append(filename)
                continue
            alias = f"legacy_{len(attached)}"
            conn.execute(
                f"ATTACH DATABASE ? AS {_quote_identifier(alias)}",
                (str(source_path),),
            )
            attached.append(alias)
            pending.append((alias, filename, source_table, target_table))

        if pending:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for alias, filename, source_table, target_table in pending:
                    if not _table_exists(conn, alias, source_table):
                        raise sqlite3.DatabaseError(
                            f"legacy database {filename} is missing table {source_table}"
                        )
                    source_rows, inserted = _copy_legacy_table(
                        conn, alias, filename, source_table, target_table,
                    )
                    if is_new and inserted != source_rows:
                        raise sqlite3.DatabaseError(
                            f"row-count mismatch for {filename}: "
                            f"source={source_rows}, inserted={inserted}"
                        )
                    report.migrated[filename] = source_rows
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise sqlite3.DatabaseError(
                f"consolidated database integrity check failed: {integrity}"
            )
        apply_schema_migrations(conn)
        conn.commit()
    except Exception:
        if is_new:
            conn.close()
            work_target.unlink(missing_ok=True)
        raise
    finally:
        if conn:
            try:
                # Closing the main connection also closes all ATTACHed source
                # handles. On Windows this is more reliable than DETACH when
                # a cursor has recently read sqlite_master.
                conn.close()
            except sqlite3.Error:
                pass

    if is_new:
        os.replace(work_target, target)
    if archive:
        report.archived_to = _archive_legacy_files(
            data_dir, [source[0] for source in sources],
        )
    if report.migrated:
        logger.info(
            f"Consolidated {len(report.migrated)} legacy databases into {target.name}"
        )
    return report
