import sqlite3
import time
import threading
from typing import Optional, Dict, Any, List, Set
from pathlib import Path
from .config import DATABASE_PATH, DEFAULT_TRACKER_INTERVAL

_db_lock = threading.Lock()

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False, timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db_lock:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 下载防重表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                chat_name TEXT,
                message_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                file_path TEXT,
                status TEXT DEFAULT 'completed',
                downloaded_at REAL,
                migrated_at REAL,
                migrated_to TEXT,
                UNIQUE(chat_id, message_id)
            )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dl_chat_msg ON downloads(chat_id, message_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dl_status ON downloads(status)")

            # 2. 跟踪监控会话表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracked_chats (
                chat_id INTEGER PRIMARY KEY,
                chat_name TEXT NOT NULL,
                interval_seconds INTEGER DEFAULT 1800,
                last_checked_at REAL DEFAULT 0,
                last_message_id INTEGER DEFAULT 0,
                auto_download INTEGER DEFAULT 1,
                is_active INTEGER DEFAULT 1,
                use_mcp INTEGER DEFAULT 0,
                new_videos_found INTEGER DEFAULT 0,
                created_at REAL
            )
            """)

            # 3. 系统配置表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """)

            conn.commit()

# ==================== 下载防重记录 ====================

def record_download(chat_id: int, chat_name: str, message_id: int, file_name: str, 
                    file_size: int = 0, file_path: str = "", status: str = "completed"):
    now = time.time()
    with _db_lock:
        with get_connection() as conn:
            conn.execute("""
            INSERT INTO downloads (chat_id, chat_name, message_id, file_name, file_size, file_path, status, downloaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, message_id) DO UPDATE SET
                chat_name = excluded.chat_name,
                file_name = excluded.file_name,
                file_size = CASE WHEN excluded.file_size > 0 THEN excluded.file_size ELSE downloads.file_size END,
                file_path = CASE WHEN excluded.file_path != '' THEN excluded.file_path ELSE downloads.file_path END,
                status = excluded.status
            """, (chat_id, chat_name, message_id, file_name, file_size, str(file_path), status, now))
            conn.commit()

def batch_record_downloads(items: List[Dict[str, Any]]):
    if not items:
        return
    now = time.time()
    with _db_lock:
        with get_connection() as conn:
            cursor = conn.cursor()
            for it in items:
                cursor.execute("""
                INSERT INTO downloads (chat_id, chat_name, message_id, file_name, file_size, file_path, status, downloaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, message_id) DO UPDATE SET
                    chat_name = excluded.chat_name,
                    file_name = excluded.file_name,
                    file_size = CASE WHEN excluded.file_size > 0 THEN excluded.file_size ELSE downloads.file_size END,
                    file_path = CASE WHEN excluded.file_path != '' THEN excluded.file_path ELSE downloads.file_path END,
                    status = excluded.status
                """, (
                    it["chat_id"],
                    it.get("chat_name", ""),
                    it["message_id"],
                    it["file_name"],
                    it.get("file_size", 0),
                    str(it.get("file_path", "")),
                    it.get("status", "completed"),
                    now
                ))
            conn.commit()

def is_downloaded(chat_id: int, message_id: int) -> bool:
    with _db_lock:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM downloads WHERE chat_id = ? AND message_id = ? AND status IN ('completed', 'migrated')",
                (chat_id, message_id)
            ).fetchone()
            return row is not None

def get_downloaded_message_ids(chat_id: int) -> Set[int]:
    with _db_lock:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT message_id FROM downloads WHERE chat_id = ? AND status IN ('completed', 'migrated')",
                (chat_id,)
            ).fetchall()
            return {r["message_id"] for r in rows}

def batch_mark_migrated(updates: List[Dict[str, Any]]):
    """
    updates: [{'chat_id': int, 'message_id': int, 'new_path': str}]
    """
    if not updates:
        return
    now = time.time()
    with _db_lock:
        with get_connection() as conn:
            cursor = conn.cursor()
            for u in updates:
                cursor.execute("""
                UPDATE downloads 
                SET status = 'migrated', migrated_to = ?, file_path = ?, migrated_at = ?
                WHERE chat_id = ? AND message_id = ?
                """, (u["new_path"], u["new_path"], now, u["chat_id"], u["message_id"]))
            conn.commit()

def search_downloads(chat_id: Optional[int] = None, status: Optional[str] = None, 
                     query: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM downloads WHERE 1=1"
    params = []
    if chat_id is not None:
        sql += " AND chat_id = ?"
        params.append(chat_id)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if query:
        sql += " AND (file_name LIKE ? OR chat_name LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%"])
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with _db_lock:
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

def get_downloads_stats() -> Dict[str, Any]:
    with _db_lock:
        with get_connection() as conn:
            total_count = conn.execute("SELECT COUNT(1) FROM downloads").fetchone()[0]
            completed_count = conn.execute("SELECT COUNT(1) FROM downloads WHERE status = 'completed'").fetchone()[0]
            migrated_count = conn.execute("SELECT COUNT(1) FROM downloads WHERE status = 'migrated'").fetchone()[0]
            total_size = conn.execute("SELECT SUM(file_size) FROM downloads").fetchone()[0] or 0
            
            # 按会话统计
            chat_stats = conn.execute("""
                SELECT chat_id, chat_name, COUNT(1) as file_count, SUM(file_size) as total_size,
                       SUM(CASE WHEN status='migrated' THEN 1 ELSE 0 END) as migrated_count
                FROM downloads
                GROUP BY chat_id
                ORDER BY file_count DESC
            """).fetchall()

            return {
                "total_records": total_count,
                "completed_count": completed_count,
                "migrated_count": migrated_count,
                "total_size_bytes": total_size,
                "chat_stats": [dict(r) for r in chat_stats]
            }

# ==================== 跟踪追更会话 ====================

def get_tracked_chats() -> List[Dict[str, Any]]:
    with _db_lock:
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM tracked_chats ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

def get_tracked_chat(chat_id: int) -> Optional[Dict[str, Any]]:
    with _db_lock:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM tracked_chats WHERE chat_id = ?", (chat_id,)).fetchone()
            return dict(row) if row else None

def set_tracked_chat(chat_id: int, chat_name: str, interval_seconds: int = DEFAULT_TRACKER_INTERVAL,
                     auto_download: int = 1, is_active: int = 1, use_mcp: int = 0) -> Dict[str, Any]:
    now = time.time()
    with _db_lock:
        with get_connection() as conn:
            conn.execute("""
            INSERT INTO tracked_chats (chat_id, chat_name, interval_seconds, auto_download, is_active, use_mcp, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                chat_name = excluded.chat_name,
                interval_seconds = excluded.interval_seconds,
                auto_download = excluded.auto_download,
                is_active = excluded.is_active,
                use_mcp = excluded.use_mcp
            """, (chat_id, chat_name, interval_seconds, auto_download, is_active, use_mcp, now))
            conn.commit()
    return get_tracked_chat(chat_id) or {}

def toggle_tracked_chat(chat_id: int, is_active: Optional[bool] = None) -> bool:
    with _db_lock:
        with get_connection() as conn:
            row = conn.execute("SELECT is_active FROM tracked_chats WHERE chat_id = ?", (chat_id,)).fetchone()
            if not row:
                return False
            new_val = (1 - row["is_active"]) if is_active is None else (1 if is_active else 0)
            conn.execute("UPDATE tracked_chats SET is_active = ? WHERE chat_id = ?", (new_val, chat_id))
            conn.commit()
            return bool(new_val)

def remove_tracked_chat(chat_id: int) -> bool:
    with _db_lock:
        with get_connection() as conn:
            conn.execute("DELETE FROM tracked_chats WHERE chat_id = ?", (chat_id,))
            conn.commit()
            return True

def update_track_progress(chat_id: int, last_message_id: int = 0, new_count: int = 0):
    now = time.time()
    with _db_lock:
        with get_connection() as conn:
            conn.execute("""
            UPDATE tracked_chats 
            SET last_checked_at = ?,
                last_message_id = CASE WHEN ? > last_message_id THEN ? ELSE last_message_id END,
                new_videos_found = new_videos_found + ?
            WHERE chat_id = ?
            """, (now, last_message_id, last_message_id, new_count, chat_id))
            conn.commit()
