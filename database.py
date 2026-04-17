# ── database.py ──────────────────────────────────────────────────────
# Supabase-backed persistence for ToolTally.
#
# Your UI expects these functions:
#     lookup_user(user_id)           → dict | None
#     get_all_users()                → list[dict]
#     add_user(user_id, name, role)  → dict | None
#     delete_user(user_id)           → bool
#     log_action(user_db_id, tool_name, action, detected_tool, confidence)
#     get_logs(limit=40)             → list[dict]
#
# Expected Supabase tables (see README.md for the SQL):
#
#     users:
#         id          bigint  primary key  (auto)
#         user_id     text    unique       — the thing typed on keypad
#         name        text
#         role        text    default 'user'   — 'user' or 'admin'
#         created_at  timestamptz default now()
#
#     logs:
#         id             bigint primary key (auto)
#         user_db_id     bigint references users(id)
#         user_name      text                  — denormalised for cheap reads
#         tool           text
#         action         text                  — 'take' or 'place'
#         detected_tool  text
#         confidence     float8
#         timestamp      timestamptz default now()
#
# If the `supabase` package is not installed OR the network is down,
# this module falls back to an in-memory stub so the UI still runs.
# ─────────────────────────────────────────────────────────────────────

from datetime import datetime

from config import SUPABASE_URL, SUPABASE_KEY, VERBOSE_LOGS


def _log(msg):
    if VERBOSE_LOGS:
        print(f"[DB] {msg}")


# ── Try to import supabase ──────────────────────────────────────────
_sb = None
try:
    from supabase import create_client
    try:
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        _log("connected to Supabase")
    except Exception as e:
        _log(f"Supabase client create failed: {e} — using in-memory stub")
        _sb = None
except ImportError:
    _log("supabase package not installed — using in-memory stub")
    _sb = None


# ═══════════════════════════════════════════════════════════════════
#  In-memory stub (only used if Supabase unavailable)
# ═══════════════════════════════════════════════════════════════════
_STUB_USERS = [
    {"id": 1, "user_id": "1234", "name": "Demo User",  "role": "user"},
    {"id": 2, "user_id": "9999", "name": "Admin",      "role": "admin"},
]
_STUB_LOGS  = []
_STUB_NEXT_USER_ID = 3
_STUB_NEXT_LOG_ID  = 1


# ═══════════════════════════════════════════════════════════════════
#  Users
# ═══════════════════════════════════════════════════════════════════
def lookup_user(user_id):
    """Return the user dict for a given typed ID, or None."""
    user_id = str(user_id).strip()
    if _sb is None:
        for u in _STUB_USERS:
            if u["user_id"] == user_id:
                return dict(u)
        return None

    try:
        res = (_sb.table("users")
                  .select("id,user_id,name,role")
                  .eq("user_id", user_id)
                  .limit(1)
                  .execute())
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        _log(f"lookup_user error: {e}")
        return None


def get_all_users():
    if _sb is None:
        return [dict(u) for u in _STUB_USERS]
    try:
        res = (_sb.table("users")
                  .select("id,user_id,name,role")
                  .order("name")
                  .execute())
        return res.data or []
    except Exception as e:
        _log(f"get_all_users error: {e}")
        return []


def add_user(user_id, name, role="user"):
    user_id = str(user_id).strip()
    name    = str(name).strip()
    if role not in ("user", "admin"):
        role = "user"

    if _sb is None:
        global _STUB_NEXT_USER_ID
        if any(u["user_id"] == user_id for u in _STUB_USERS):
            return None
        u = {"id": _STUB_NEXT_USER_ID,
             "user_id": user_id, "name": name, "role": role}
        _STUB_NEXT_USER_ID += 1
        _STUB_USERS.append(u)
        return dict(u)

    try:
        res = (_sb.table("users")
                  .insert({"user_id": user_id, "name": name, "role": role})
                  .execute())
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        _log(f"add_user error: {e}")
        return None


def delete_user(user_id):
    user_id = str(user_id).strip()
    if _sb is None:
        before = len(_STUB_USERS)
        _STUB_USERS[:] = [u for u in _STUB_USERS if u["user_id"] != user_id]
        return len(_STUB_USERS) < before

    try:
        _sb.table("users").delete().eq("user_id", user_id).execute()
        return True
    except Exception as e:
        _log(f"delete_user error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
#  Logs
# ═══════════════════════════════════════════════════════════════════
def log_action(user_db_id, tool_name, action,
               detected_tool=None, confidence=None):
    """Append a row to the logs table."""
    if _sb is None:
        global _STUB_NEXT_LOG_ID
        user_name = next((u["name"] for u in _STUB_USERS
                          if u["id"] == user_db_id), "")
        row = {
            "id": _STUB_NEXT_LOG_ID,
            "user_db_id":    user_db_id,
            "user_name":     user_name,
            "tool":          tool_name,
            "action":        action,
            "detected_tool": detected_tool,
            "confidence":    confidence,
            "timestamp":     datetime.utcnow().isoformat(timespec="seconds"),
        }
        _STUB_NEXT_LOG_ID += 1
        _STUB_LOGS.append(row)
        return row

    try:
        # Look up the user's display name for denormalised logging.
        user_name = ""
        try:
            ures = (_sb.table("users")
                       .select("name").eq("id", user_db_id).limit(1)
                       .execute())
            if ures.data:
                user_name = ures.data[0].get("name", "")
        except Exception:
            pass

        payload = {
            "user_db_id":    user_db_id,
            "user_name":     user_name,
            "tool":          tool_name,
            "action":        action,
            "detected_tool": detected_tool,
            "confidence":    confidence,
        }
        res = _sb.table("logs").insert(payload).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        _log(f"log_action error: {e}")
        return None


def get_logs(limit=40):
    if _sb is None:
        return list(reversed(_STUB_LOGS[-limit:]))

    try:
        res = (_sb.table("logs")
                  .select("*")
                  .order("timestamp", desc=True)
                  .limit(limit)
                  .execute())
        return res.data or []
    except Exception as e:
        _log(f"get_logs error: {e}")
        return []
