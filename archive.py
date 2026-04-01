"""
Achievement archive — dual backend persistence.

STORAGE_MODE=local  → SQLite database (handles concurrency, works in containers)
STORAGE_MODE=cloud  → DynamoDB (serverless, production AWS)

Public API is identical regardless of backend.
"""

import json
import sqlite3
from datetime import datetime

from config import DB_PATH, DYNAMODB_TABLE, STORAGE_MODE

# ---------------------------------------------------------------------------
# SQLite backend (local mode)
# ---------------------------------------------------------------------------

_DB_INIT = False


def _get_db() -> sqlite3.Connection:
    """Return a SQLite connection, creating the table on first call."""
    global _DB_INIT
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    if not _DB_INIT:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                reward TEXT NOT NULL,
                trigger_text TEXT,
                audio_files TEXT NOT NULL DEFAULT '[]'
            )
        """)
        conn.commit()
        _DB_INIT = True
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "timestamp": row["timestamp"],
        "title": row["title"],
        "description": row["description"],
        "reward": row["reward"],
        "trigger": row["trigger_text"],
        "audio_files": json.loads(row["audio_files"]),
    }


def _local_save(achievement: dict, trigger: str | None, audio_files: list[str] | None) -> dict:
    conn = _get_db()
    ts = datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO achievements (timestamp, title, description, reward, trigger_text, audio_files) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            ts,
            achievement.get("title", ""),
            achievement.get("description", ""),
            achievement.get("reward", ""),
            trigger,
            json.dumps(audio_files or []),
        ),
    )
    conn.commit()
    return {
        "id": cur.lastrowid,
        "timestamp": ts,
        "title": achievement.get("title", ""),
        "description": achievement.get("description", ""),
        "reward": achievement.get("reward", ""),
        "trigger": trigger,
        "audio_files": audio_files or [],
    }


def _local_load_all() -> list[dict]:
    conn = _get_db()
    rows = conn.execute("SELECT * FROM achievements ORDER BY id").fetchall()
    return [_row_to_dict(r) for r in rows]


def _local_get(entry_id: int) -> dict | None:
    conn = _get_db()
    row = conn.execute("SELECT * FROM achievements WHERE id = ?", (entry_id,)).fetchone()
    return _row_to_dict(row) if row else None


def _local_update_audio(entry_id: int, audio_files: list[str]) -> None:
    conn = _get_db()
    conn.execute(
        "UPDATE achievements SET audio_files = ? WHERE id = ?",
        (json.dumps(audio_files), entry_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# DynamoDB backend (cloud mode)
# ---------------------------------------------------------------------------


def _get_table():
    import boto3

    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(DYNAMODB_TABLE)


def _dynamo_save(achievement: dict, trigger: str | None, audio_files: list[str] | None) -> dict:
    table = _get_table()

    # Atomic counter for auto-increment ID
    resp = table.update_item(
        Key={"id": 0},
        UpdateExpression="ADD #c :inc",
        ExpressionAttributeNames={"#c": "counter"},
        ExpressionAttributeValues={":inc": 1},
        ReturnValues="UPDATED_NEW",
    )
    new_id = int(resp["Attributes"]["counter"])

    ts = datetime.now().isoformat()
    item = {
        "id": new_id,
        "timestamp": ts,
        "title": achievement.get("title", ""),
        "description": achievement.get("description", ""),
        "reward": achievement.get("reward", ""),
        "trigger_text": trigger or "",
        "audio_files": audio_files or [],
    }
    table.put_item(Item=item)

    item["trigger"] = trigger
    del item["trigger_text"]
    return item


def _dynamo_load_all() -> list[dict]:
    table = _get_table()
    resp = table.scan()
    items = resp.get("Items", [])
    # Filter out the counter item and sort by id
    entries = []
    for item in items:
        if item["id"] == 0:
            continue
        item["trigger"] = item.pop("trigger_text", None) or None
        entries.append(item)
    return sorted(entries, key=lambda x: x["id"])


def _dynamo_get(entry_id: int) -> dict | None:
    table = _get_table()
    resp = table.get_item(Key={"id": entry_id})
    item = resp.get("Item")
    if not item or item["id"] == 0:
        return None
    item["trigger"] = item.pop("trigger_text", None) or None
    return item


def _dynamo_update_audio(entry_id: int, audio_files: list[str]) -> None:
    table = _get_table()
    table.update_item(
        Key={"id": entry_id},
        UpdateExpression="SET audio_files = :af",
        ExpressionAttributeValues={":af": audio_files},
    )


# ---------------------------------------------------------------------------
# Public API — dispatches based on STORAGE_MODE
# ---------------------------------------------------------------------------


def save(achievement: dict, trigger: str | None = None, audio_files: list[str] | None = None) -> dict:
    """Append an achievement to the archive. Returns the saved entry."""
    if STORAGE_MODE == "cloud":
        return _dynamo_save(achievement, trigger, audio_files)
    return _local_save(achievement, trigger, audio_files)


def load_all() -> list[dict]:
    """Load all archived achievements."""
    if STORAGE_MODE == "cloud":
        return _dynamo_load_all()
    return _local_load_all()


def get(entry_id: int) -> dict | None:
    """Get a single achievement by ID."""
    if STORAGE_MODE == "cloud":
        return _dynamo_get(entry_id)
    return _local_get(entry_id)


def update_audio(entry_id: int, audio_files: list[str]) -> None:
    """Update the audio_files for an existing archive entry."""
    if STORAGE_MODE == "cloud":
        _dynamo_update_audio(entry_id, audio_files)
    else:
        _local_update_audio(entry_id, audio_files)
