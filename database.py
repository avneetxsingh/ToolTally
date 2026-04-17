# -- database.py ------------------------------------------------------
# Offline-first persistence for ToolTally.
#
# Public API consumed by UI:
#     lookup_user(user_id)           -> dict | None
#     get_all_users()                -> list[dict]
#     add_user(user_id, name, role)  -> dict | None
#     delete_user(user_id)           -> bool
#     log_action(user_db_id, tool_name, action, detected_tool, confidence)
#     get_logs(limit=40)             -> list[dict]
#
# Strategy:
# - SQLite is the source of truth for local reads/writes.
# - Supabase sync runs in a background thread for pending rows.
# --------------------------------------------------------------------

from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone

from config import (
    SUPABASE_URL,
    SUPABASE_KEY,
    VERBOSE_LOGS,
    LOCAL_DB_PATH,
    SUPABASE_USERS_TABLE,
    SUPABASE_LOGS_TABLE,
    SYNC_ENABLED,
    SYNC_INTERVAL_SECS,
    SYNC_MAX_RETRIES,
)


def _log(msg: str) -> None:
    if VERBOSE_LOGS:
        print(f"[DB] {msg}")


def _utc_now() -> str:
    # Store UTC timestamp in a stable string format.
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_db_lock = threading.Lock()
_sync_wakeup = threading.Event()
_sync_started = False


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_parent_dir() -> None:
    parent = os.path.dirname(LOCAL_DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _ensure_schema() -> None:
    _ensure_parent_dir()
    with _db_lock:
        conn = _connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT,
                    remote_id TEXT,
                    sync_status TEXT NOT NULL DEFAULT 'pending',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    synced_at TEXT
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_uuid TEXT NOT NULL UNIQUE,
                    user_db_id INTEGER,
                    user_name TEXT,
                    tool TEXT,
                    action TEXT,
                    detected_tool TEXT,
                    confidence REAL,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    sync_status TEXT NOT NULL DEFAULT 'pending',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    synced_at TEXT,
                    FOREIGN KEY(user_db_id) REFERENCES users(id) ON DELETE SET NULL
                )
                """
            )

            # Migrations for older local DBs created before sync fields existed.
            user_add_cols = [
                ("updated_at", "TEXT"),
                ("remote_id", "TEXT"),
                ("sync_status", "TEXT NOT NULL DEFAULT 'pending'"),
                ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
                ("last_error", "TEXT"),
                ("synced_at", "TEXT"),
            ]
            for col, ddl in user_add_cols:
                if not _table_has_column(conn, "users", col):
                    conn.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")

            logs_add_cols = [
                ("event_uuid", "TEXT"),
                ("sync_status", "TEXT NOT NULL DEFAULT 'pending'"),
                ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
                ("last_error", "TEXT"),
                ("synced_at", "TEXT"),
            ]
            for col, ddl in logs_add_cols:
                if not _table_has_column(conn, "logs", col):
                    conn.execute(f"ALTER TABLE logs ADD COLUMN {col} {ddl}")

            # Backfill event_uuid for rows created before this column existed.
            conn.execute(
                """
                UPDATE logs
                SET event_uuid = lower(hex(randomblob(16)))
                WHERE event_uuid IS NULL OR event_uuid = ''
                """
            )

            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_event_uuid ON logs(event_uuid)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_sync_status ON logs(sync_status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_sync_status ON users(sync_status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)"
            )
            conn.commit()
        finally:
            conn.close()


_sb = None
try:
    from supabase import create_client

    try:
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        _log("Supabase client initialized")
    except Exception as e:
        _sb = None
        _log(f"Supabase client create failed: {e}")
except Exception:
    _sb = None
    _log("supabase package unavailable; running local-only")


def _strip_public_user(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "role": row["role"],
    }


def _start_sync_worker_if_needed() -> None:
    global _sync_started
    if _sync_started or not SYNC_ENABLED:
        return
    _sync_started = True
    t = threading.Thread(target=_sync_loop, daemon=True, name="db-sync")
    t.start()
    _log("background sync worker started")


def _mark_user_synced(local_id: int, remote_id=None) -> None:
    with _db_lock:
        conn = _connect()
        try:
            conn.execute(
                """
                UPDATE users
                SET sync_status='synced',
                    retry_count=0,
                    last_error=NULL,
                    synced_at=?,
                    remote_id=COALESCE(?, remote_id)
                WHERE id=?
                """,
                (_utc_now(), str(remote_id) if remote_id is not None else None, local_id),
            )
            conn.commit()
        finally:
            conn.close()


def _mark_user_failed(local_id: int, error: str) -> None:
    with _db_lock:
        conn = _connect()
        try:
            conn.execute(
                """
                UPDATE users
                SET sync_status='failed',
                    retry_count=retry_count + 1,
                    last_error=?
                WHERE id=?
                """,
                (error[:500], local_id),
            )
            conn.commit()
        finally:
            conn.close()


def _mark_log_synced(local_id: int) -> None:
    with _db_lock:
        conn = _connect()
        try:
            conn.execute(
                """
                UPDATE logs
                SET sync_status='synced',
                    retry_count=0,
                    last_error=NULL,
                    synced_at=?
                WHERE id=?
                """,
                (_utc_now(), local_id),
            )
            conn.commit()
        finally:
            conn.close()


def _mark_log_failed(local_id: int, error: str) -> None:
    with _db_lock:
        conn = _connect()
        try:
            conn.execute(
                """
                UPDATE logs
                SET sync_status='failed',
                    retry_count=retry_count + 1,
                    last_error=?
                WHERE id=?
                """,
                (error[:500], local_id),
            )
            conn.commit()
        finally:
            conn.close()


def _sync_pending_users() -> None:
    if _sb is None:
        return

    with _db_lock:
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT id, user_id, name, role
                FROM users
                WHERE sync_status IN ('pending', 'failed')
                  AND retry_count < ?
                ORDER BY id
                LIMIT 50
                """,
                (SYNC_MAX_RETRIES,),
            ).fetchall()
        finally:
            conn.close()

    for r in rows:
        payload = {
            "user_id": r["user_id"],
            "name": r["name"],
            "role": r["role"],
        }
        try:
            res = (
                _sb.table(SUPABASE_USERS_TABLE)
                .upsert(payload, on_conflict="user_id")
                .execute()
            )
            remote_id = None
            if getattr(res, "data", None):
                remote_id = res.data[0].get("id")
            _mark_user_synced(r["id"], remote_id=remote_id)
        except Exception as e:
            _mark_user_failed(r["id"], str(e))


def _sync_pending_logs() -> None:
    if _sb is None:
        return

    with _db_lock:
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT id, user_db_id, user_name, tool, action, detected_tool, confidence, timestamp
                FROM logs
                WHERE sync_status IN ('pending', 'failed')
                  AND retry_count < ?
                ORDER BY id
                LIMIT 100
                """,
                (SYNC_MAX_RETRIES,),
            ).fetchall()
        finally:
            conn.close()

    for r in rows:
        payload = {
            "user_db_id": r["user_db_id"],
            "user_name": r["user_name"],
            "tool": r["tool"],
            "action": r["action"],
            "detected_tool": r["detected_tool"],
            "confidence": r["confidence"],
            "timestamp": r["timestamp"],
        }
        try:
            _sb.table(SUPABASE_LOGS_TABLE).insert(payload).execute()
            _mark_log_synced(r["id"])
        except Exception as e:
            _mark_log_failed(r["id"], str(e))


def _pull_users_from_supabase() -> None:
    # Best-effort remote -> local hydration for users created elsewhere.
    if _sb is None:
        return

    try:
        res = (
            _sb.table(SUPABASE_USERS_TABLE)
            .select("id,user_id,name,role")
            .order("id")
            .limit(500)
            .execute()
        )
        rows = getattr(res, "data", None) or []
    except Exception:
        return

    if not rows:
        return

    with _db_lock:
        conn = _connect()
        try:
            for r in rows:
                user_id = str(r.get("user_id", "")).strip()
                if not user_id:
                    continue
                cur = conn.execute(
                    "SELECT id, sync_status FROM users WHERE user_id=?",
                    (user_id,),
                ).fetchone()
                if cur is not None and cur["sync_status"] == "pending":
                    # Preserve local unsynced edits; they will push upstream.
                    continue

                now = _utc_now()
                if cur is None:
                    conn.execute(
                        """
                        INSERT INTO users
                            (user_id, name, role, created_at, updated_at, remote_id,
                             sync_status, retry_count, last_error, synced_at)
                        VALUES (?, ?, ?, ?, ?, ?, 'synced', 0, NULL, ?)
                        """,
                        (
                            user_id,
                            str(r.get("name", "")),
                            str(r.get("role", "user")),
                            now,
                            now,
                            str(r.get("id")) if r.get("id") is not None else None,
                            now,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE users
                        SET name=?,
                            role=?,
                            updated_at=?,
                            remote_id=?,
                            sync_status='synced',
                            retry_count=0,
                            last_error=NULL,
                            synced_at=?
                        WHERE id=?
                        """,
                        (
                            str(r.get("name", "")),
                            str(r.get("role", "user")),
                            now,
                            str(r.get("id")) if r.get("id") is not None else None,
                            now,
                            cur["id"],
                        ),
                    )
            conn.commit()
        finally:
            conn.close()


def _sync_loop() -> None:
    while True:
        try:
            _sync_pending_users()
            _sync_pending_logs()
            _pull_users_from_supabase()
        except Exception as e:
            _log(f"sync loop error: {e}")

        wait_secs = max(1, int(SYNC_INTERVAL_SECS))
        _sync_wakeup.wait(timeout=wait_secs)
        _sync_wakeup.clear()


def _request_sync() -> None:
    if not SYNC_ENABLED:
        return
    _sync_wakeup.set()


def _sync_bootstrap() -> None:
    _ensure_schema()
    _start_sync_worker_if_needed()


_sync_bootstrap()


# ====================================================================
# Public API
# ====================================================================
def lookup_user(user_id):
    user_id = str(user_id).strip()
    if not user_id:
        return None

    with _db_lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT id,user_id,name,role FROM users WHERE user_id=? LIMIT 1",
                (user_id,),
            ).fetchone()
        finally:
            conn.close()
    user = _strip_public_user(row)
    if user is not None:
        return user
    return None


def get_all_users():
    with _db_lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT id,user_id,name,role FROM users ORDER BY name COLLATE NOCASE"
            ).fetchall()
        finally:
            conn.close()
    return [dict(r) for r in rows]


def add_user(user_id, name, role="user"):
    user_id = str(user_id).strip()
    name = str(name).strip()
    if role not in ("user", "admin"):
        role = "user"
    if not user_id or not name:
        return None

    now = _utc_now()
    with _db_lock:
        conn = _connect()
        try:
            exists = conn.execute(
                "SELECT id FROM users WHERE user_id=? LIMIT 1", (user_id,)
            ).fetchone()
            if exists is not None:
                return None
            cur = conn.execute(
                """
                INSERT INTO users (user_id,name,role,created_at,updated_at,sync_status)
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (user_id, name, role, now, now),
            )
            local_id = cur.lastrowid
            conn.commit()
            row = conn.execute(
                "SELECT id,user_id,name,role FROM users WHERE id=?",
                (local_id,),
            ).fetchone()
        finally:
            conn.close()

    _request_sync()
    return _strip_public_user(row)


def delete_user(user_id):
    user_id = str(user_id).strip()
    if not user_id:
        return False

    deleted = False
    with _db_lock:
        conn = _connect()
        try:
            cur = conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
            deleted = cur.rowcount > 0
            conn.commit()
        finally:
            conn.close()

    if deleted and _sb is not None:
        # Best effort remote delete; local delete remains authoritative.
        try:
            _sb.table(SUPABASE_USERS_TABLE).delete().eq("user_id", user_id).execute()
        except Exception as e:
            _log(f"remote delete_user failed for {user_id}: {e}")
    return deleted


def log_action(user_db_id, tool_name, action, detected_tool=None, confidence=None):
    user_name = ""
    with _db_lock:
        conn = _connect()
        try:
            if user_db_id is not None:
                u = conn.execute(
                    "SELECT name FROM users WHERE id=? LIMIT 1", (user_db_id,)
                ).fetchone()
                if u is not None:
                    user_name = u["name"] or ""

            event_uuid = str(uuid.uuid4())
            ts = _utc_now()
            cur = conn.execute(
                """
                INSERT INTO logs
                    (event_uuid,user_db_id,user_name,tool,action,detected_tool,confidence,timestamp,
                     sync_status,retry_count,last_error,synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, NULL, NULL)
                """,
                (
                    event_uuid,
                    user_db_id,
                    user_name,
                    tool_name,
                    action,
                    detected_tool,
                    confidence,
                    ts,
                ),
            )
            local_id = cur.lastrowid
            conn.commit()
            row = conn.execute("SELECT * FROM logs WHERE id=?", (local_id,)).fetchone()
        finally:
            conn.close()

    _request_sync()
    return dict(row) if row is not None else None


def get_logs(limit=40):
    try:
        limit_int = int(limit)
    except Exception:
        limit_int = 40
    if limit_int <= 0:
        limit_int = 40

    with _db_lock:
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT id,user_db_id,user_name,tool,action,detected_tool,confidence,timestamp
                FROM logs
                ORDER BY datetime(timestamp) DESC, id DESC
                LIMIT ?
                """,
                (limit_int,),
            ).fetchall()
        finally:
            conn.close()
    return [dict(r) for r in rows]
