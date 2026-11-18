import time
import secrets
import sqlite3
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Depends
from .config import DATABASE_PATH, AUTH_USERNAME, AUTH_PASSWORD, AUTH_SESSION_EXPIRE_HOURS

def _get_db():
    conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_auth_table():
    with _get_db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL
        )
        """)
        conn.commit()

def verify_credentials(username: str, password: str) -> bool:
    # 恒定时间比较防时序攻击
    user_ok = secrets.compare_digest(username.strip(), AUTH_USERNAME.strip())
    pass_ok = secrets.compare_digest(password.strip(), AUTH_PASSWORD.strip())
    return user_ok and pass_ok

def create_session(username: str) -> str:
    init_auth_table()
    token = secrets.token_urlsafe(32)
    now = time.time()
    expires_at = now + (AUTH_SESSION_EXPIRE_HOURS * 3600)
    with _get_db() as conn:
        conn.execute(
            "INSERT INTO auth_sessions (token, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, username, now, expires_at)
        )
        conn.commit()
    return token

def validate_token(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    init_auth_table()
    now = time.time()
    with _get_db() as conn:
        row = conn.execute(
            "SELECT token, username, created_at, expires_at FROM auth_sessions WHERE token = ? AND expires_at > ?",
            (token, now)
        ).fetchone()
        if row:
            return dict(row)
    return None

def revoke_session(token: str):
    if not token:
        return
    with _get_db() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
        conn.commit()

def get_token_from_request(request: Request) -> Optional[str]:
    # 1. 优先从 Header: Authorization: Bearer <token> 获取
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    
    # 2. 从 Cookie 获取
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token.strip()

    # 3. 从 URL Query 参数获取（便于图片、缩略图等静态资源认证）
    query_token = request.query_params.get("auth_token")
    if query_token:
        return query_token.strip()

    return None

async def require_auth(request: Request) -> Dict[str, Any]:
    token = get_token_from_request(request)
    session = validate_token(token) if token else None
    if not session:
        raise HTTPException(status_code=401, detail="用户未登录或会话已过期，请先登录")
    return session
