"""Authoritative names for the consolidated SQLite application store."""

from __future__ import annotations


CONSOLIDATED_DB_NAME = "companion.db"

# (legacy filename, legacy table, consolidated table)
LEGACY_TABLE_MAPPINGS: tuple[tuple[str, str, str], ...] = (
    ("memories.db", "memories", "memories"),
    ("vectors.db", "memories", "memory_vectors"),
    ("moods.db", "moods", "moods"),
    ("personality.db", "personalities", "personalities"),
    ("unified.db", "affection", "affection"),
    ("relationship_events.db", "relationship_events", "relationship_events"),
    ("open_loops.db", "open_loops", "open_loops"),
    ("life_summaries.db", "life_summaries", "life_summaries"),
    ("identity.db", "identity", "identity"),
    ("long_term.db", "facts", "facts"),
)

LEGACY_DB_NAMES = tuple(dict.fromkeys(item[0] for item in LEGACY_TABLE_MAPPINGS))

