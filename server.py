import os
import sys
import json
import re
import time
import socket
import datetime
import threading
import subprocess
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List

import psutil
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.config import (
    TDL_BIN, BASE_DOWNLOAD_DIR, META_DIR, CHATS_JSON, BOT_COUNTS_JSON,
    STATS_FILE, QUEUE_FILE, DEFAULT_PROXY, SERVER_PORT, MCP_GATEWAY_URL,
    DATABASE_PATH, SESSION_CACHE_DIR, THUMB_CACHE_DIR, DEFAULT_TRACKER_INTERVAL
)
from core.db import (
    init_db, record_download, batch_record_downloads, is_downloaded,
    get_downloaded_message_ids, batch_mark_migrated, search_downloads,
    get_downloads_stats, get_tracked_chats, get_tracked_chat, set_tracked_chat,
    toggle_tracked_chat, remove_tracked_chat, update_track_progress
)
from core.migrator import scan_and_index_existing_files, get_migration_summary, migrate_files
from core.tracker import tracker_engine

app = FastAPI(title="tdl Telegram Downloader WebUI & Watchdog")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TDL_EXE = TDL_BIN
LOG_FILE = Path(os.path.expanduser(r"~\.tdl\log\latest.log"))
WEB_DIR = Path(__file__).parent / "web"


import cv2
from PIL import Image
from fastapi.responses import FileResponse

SESSION_CACHE_DIR = META_DIR / "session_cache"
THUMB_CACHE_DIR = META_DIR / "thumb_cache"
SESSION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)

JPEG_HEADER = (
    b"\xff\xd8\xff\xe0\x00\x10\x4a\x46\x49"
    b"\x46\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00\x43\x00\x28\x1c"
    b"\x1e\x23\x1e\x19\x28\x23\x21\x23\x2d\x2b\x28\x30\x3c\x64\x41\x3c\x37\x37"
    b"\x3c\x7b\x58\x5d\x49\x64\x91\x80\x99\x96\x8f\x80\x8c\x8a\xa0\xb4\xe6\xc3"
    b"\xa0\xaa\xda\xad\x8a\x8c\xc8\xff\xcb\xda\xee\xf5\xff\xff\xff\x9b\xc1\xff"
    b"\xff\xff\xfa\xff\xe6\xfd\xff\xf8\xff\xdb\x00\x43\x01\x2b\x2d\x2d\x3c\x35"
    b"\x3c\x76\x41\x41\x76\xf8\xa5\x8c\xa5\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8"
    b"\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8"
    b"\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8\xf8"
    b"\xf8\xf8\xf8\xf8\xf8\xff\xc0\x00\x11\x08\x00\x00\x00\x00\x03\x01\x22\x00"
    b"\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01"
    b"\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08"
    b"\x09\x0a\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05"
    b"\x04\x04\x00\x00\x01\x7d\x01\x02\x03\x00\x04\x11\x05\x12\x21\x31\x41\x06"
    b"\x13\x51\x61\x07\x22\x71\x14\x32\x81\x91\xa1\x08\x23\x42\xb1\xc1\x15\x52"
    b"\xd1\xf0\x24\x33\x62\x72\x82\x09\x0a\x16\x17\x18\x19\x1a\x25\x26\x27\x28"
    b"\x29\x2a\x34\x35\x36\x37\x38\x39\x3a\x43\x44\x45\x46\x47\x48\x49\x4a\x53"
    b"\x54\x55\x56\x57\x58\x59\x5a\x63\x64\x65\x66\x67\x68\x69\x6a\x73\x74\x75"
    b"\x76\x77\x78\x79\x7a\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96"
    b"\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6"
    b"\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6"
    b"\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4"
    b"\xf5\xf6\xf7\xf8\xf9\xfa\xff\xc4\x00\x1f\x01\x00\x03\x01\x01\x01\x01\x01"
    b"\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08"
    b"\x09\x0a\x0b\xff\xc4\x00\xb5\x11\x00\x02\x01\x02\x04\x04\x03\x04\x07\x05"
    b"\x04\x04\x00\x01\x02\x77\x00\x01\x02\x03\x11\x04\x05\x21\x31\x06\x12\x41"
    b"\x51\x07\x61\x71\x13\x22\x32\x81\x08\x14\x42\x91\xa1\xb1\xc1\x09\x23\x33"
    b"\x52\xf0\x15\x62\x72\xd1\x0a\x16\x24\x34\xe1\x25\xf1\x17\x18\x19\x1a\x26"
    b"\x27\x28\x29\x2a\x35\x36\x37\x38\x39\x3a\x43\x44\x45\x46\x47\x48\x49\x4a"
    b"\x53\x54\x55\x56\x57\x58\x59\x5a\x63\x64\x65\x66\x67\x68\x69\x6a\x73\x74"
    b"\x75\x76\x77\x78\x79\x7a\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94"
    b"\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4"
    b"\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4"
    b"\xd5\xd6\xd7\xd8\xd9\xda\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf2\xf3\xf4"
    b"\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00"
    b"\x3f\x00"
)
JPEG_FOOTER = b"\xff\xd9"

def stripped_thumb_to_base64(raw_b64: str) -> Optional[str]:
    import base64, io
    from PIL import Image, ImageFilter
    try:
        raw = base64.b64decode(raw_b64)
        if len(raw) < 3 or raw[0] != 1:
            return None
        buf = bytearray(JPEG_HEADER)
        buf[164] = raw[1]
        buf[166] = raw[2]
        jpg_bytes = bytes(buf) + raw[3:] + JPEG_FOOTER

        # 利用 PIL 进行高质量插值平滑与锐化，消除马赛克感
        im = Image.open(io.BytesIO(jpg_bytes))
        w, h = im.size
        # 放大4倍获得平滑的高保真视觉
        target_w = max(180, w * 5)
        target_h = max(240, h * 5)
        up = im.resize((target_w, target_h), Image.Resampling.LANCZOS)
        up = up.filter(ImageFilter.UnsharpMask(radius=1.2, percent=130, threshold=2))
        
        out_buf = io.BytesIO()
        up.save(out_buf, format="JPEG", quality=92)
        return "data:image/jpeg;base64," + base64.b64encode(out_buf.getvalue()).decode('ascii')
    except Exception:
        try:
            return "data:image/jpeg;base64," + base64.b64encode(jpg_bytes).decode('ascii')
        except Exception:
            return None

def file_has_raw_metadata(json_file: Path) -> bool:
    if not json_file.exists() or json_file.stat().st_size < 100:
        return False
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            d = json.load(f)
        msgs = d.get("messages", [])
        return any(bool(m.get("raw")) for m in msgs[:10])
    except Exception:
        return False

def sync_session_cache():
    try:
        src = Path(os.path.expanduser(r"~\.tdl\data\default"))
        if src.exists():
            dst = SESSION_CACHE_DIR / "default"
            shutil.copy2(src, dst)
            return True
    except Exception:
        pass
    return False

def sanitize_name(name: str) -> str:
    if not name:
        return "Unknown_Chat"
    clean = re.sub(r'[\\/*?:"<>|]', '_', name)
    return clean.strip() or "Chat"

def check_tcp_port(host="192.168.8.11", port=7890, timeout=1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, OSError):
        return False

# ==================== 全局状态、速度与配额监控守护 ====================
class SystemMonitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.speed_bytes_sec = 0.0
        self.speed_human = "0 KB/s"
        self.last_io_bytes = 0
        self.last_io_time = time.time()
        
        self.file_speed_tracker = {}
        
        self.today_str = datetime.date.today().isoformat()
        self.today_downloaded_bytes = 0
        self.daily_limit_gb = 100.0
        self.daily_limit_reached = False
        
        self.auto_retry_enabled = True
        self.retry_count = 0
        self.last_retry_time = 0
        self.watchdog_status = "就绪"

        self.load_stats()

    def load_stats(self):
        if STATS_FILE.exists():
            try:
                with open(STATS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("date") == self.today_str:
                    self.today_downloaded_bytes = data.get("today_downloaded_bytes", 0)
                else:
                    self.today_downloaded_bytes = 0
                self.daily_limit_gb = data.get("daily_limit_gb", 100.0)
                self.auto_retry_enabled = data.get("auto_retry_enabled", True)
            except Exception:
                pass

    def save_stats(self):
        try:
            data = {
                "date": self.today_str,
                "today_downloaded_bytes": self.today_downloaded_bytes,
                "daily_limit_gb": self.daily_limit_gb,
                "auto_retry_enabled": self.auto_retry_enabled
            }
            with open(STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def check_date_rollover(self):
        now_date = datetime.date.today().isoformat()
        if now_date != self.today_str:
            self.today_str = now_date
            self.today_downloaded_bytes = 0
            self.daily_limit_reached = False
            self.save_stats()

    def update_per_file_speeds(self, active_folder: Optional[str]):
        if not active_folder:
            active_folder = "学生会员"
        
        chat_dir = BASE_DOWNLOAD_DIR / sanitize_name(active_folder)
        if not chat_dir.exists():
            return

        now = time.time()
        current_tmps = set()
        total_tmp_delta_bytes = 0
        total_dt = 1.0

        try:
            for entry in os.scandir(chat_dir):
                if entry.is_file() and entry.name.endswith(".tmp"):
                    current_tmps.add(entry.name)
                    stat = entry.stat()
                    curr_size = stat.st_size
                    
                    prev = self.file_speed_tracker.get(entry.name)
                    if prev:
                        dt = max(0.2, now - prev["last_time"])
                        total_dt = dt
                        delta = max(0, curr_size - prev["last_size"])
                        total_tmp_delta_bytes += delta
                        rate = delta / dt
                        
                        if rate >= 1024 * 1024:
                            rate_human = f"{rate / (1024 * 1024):.2f} MB/s"
                        elif rate >= 1024:
                            rate_human = f"{rate / 1024:.1f} KB/s"
                        else:
                            rate_human = "0 KB/s" if delta == 0 else f"{rate:.0f} B/s"
                            
                        self.file_speed_tracker[entry.name] = {
                            "last_size": curr_size,
                            "last_time": now,
                            "speed_bytes_sec": rate,
                            "speed_human": rate_human
                        }
                    else:
                        self.file_speed_tracker[entry.name] = {
                            "last_size": curr_size,
                            "last_time": now,
                            "speed_bytes_sec": 0.0,
                            "speed_human": "连接缓冲中..."
                        }
        except Exception:
            pass

        for name in list(self.file_speed_tracker.keys()):
            if name not in current_tmps:
                del self.file_speed_tracker[name]

        if total_tmp_delta_bytes > 0:
            calc_speed = total_tmp_delta_bytes / max(0.2, total_dt)
            if calc_speed > self.speed_bytes_sec:
                self.speed_bytes_sec = calc_speed
                if calc_speed >= 1024 * 1024:
                    self.speed_human = f"{calc_speed / (1024 * 1024):.2f} MB/s"
                elif calc_speed >= 1024:
                    self.speed_human = f"{calc_speed / 1024:.1f} KB/s"

    def update_speed_and_quota(self, proc, active_folder: Optional[str]):
        now = time.time()
        self.check_date_rollover()
        self.update_per_file_speeds(active_folder)

        if proc:
            try:
                io = proc.io_counters()
                curr_write = io.write_bytes
                if self.last_io_bytes > 0:
                    dt = max(0.1, now - self.last_io_time)
                    delta_bytes = max(0, curr_write - self.last_io_bytes)
                    raw_speed = delta_bytes / dt
                    
                    self.speed_bytes_sec = raw_speed
                    if raw_speed >= 1024 * 1024:
                        self.speed_human = f"{raw_speed / (1024 * 1024):.2f} MB/s"
                    elif raw_speed >= 1024:
                        self.speed_human = f"{raw_speed / 1024:.1f} KB/s"
                    elif raw_speed == 0 and len(self.file_speed_tracker) > 0:
                        pass
                    else:
                        self.speed_human = "0 KB/s"

                    self.today_downloaded_bytes += delta_bytes
                    self.save_stats()

                self.last_io_bytes = curr_write
                self.last_io_time = now

                if self.daily_limit_gb > 0:
                    max_bytes = self.daily_limit_gb * (1024 ** 3)
                    if self.today_downloaded_bytes >= max_bytes:
                        self.daily_limit_reached = True
                        self.watchdog_status = f"已达今日限额 ({self.daily_limit_gb} GB)，已自动暂停"
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        return
            except Exception:
                pass
        else:
            self.last_io_bytes = 0
            self.speed_bytes_sec = 0.0
            self.speed_human = "0 KB/s"
            self.file_speed_tracker.clear()

monitor = SystemMonitor()

def get_tdl_process():
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'create_time', 'cmdline']):
        try:
            if p.info['name'] and p.info['name'].lower() == 'tdl.exe':
                return p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None

def extract_videos_json(full_json: Path, videos_json: Path):
    if not full_json.exists():
        return []
    try:
        with open(full_json, "r", encoding="utf-8") as f:
            d = json.load(f)
        msgs = d.get("messages", [])
        vmsgs = []
        for m in msgs:
            fname = m.get("file", "")
            if re.search(r'\.(mp4|mov|mkv|avi|webm)$', fname, re.I):
                vmsgs.append(m)
                continue
            raw = m.get("raw") or {}
            media = raw.get("Media") or {}
            doc = media.get("Document") or {}
            mime = doc.get("MimeType", "")
            if mime.startswith("video"):
                vmsgs.append(m)
        with open(videos_json, "w", encoding="utf-8") as f:
            json.dump({"id": d.get("id"), "messages": vmsgs}, f, ensure_ascii=False)
        return vmsgs
    except Exception:
        return []

class DownloadQueueManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.active_task: Optional[Dict[str, Any]] = None
        self.waiting_queue: List[Dict[str, Any]] = []
        self.completed_history: List[Dict[str, Any]] = []
        self.is_paused = False
        self.load_queue()
        self.adopt_running_process()

    def load_queue(self):
        if QUEUE_FILE.exists():
            try:
                with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.waiting_queue = data.get("waiting", [])
                self.completed_history = data.get("completed", [])[:50]
                self.is_paused = data.get("is_paused", False)
            except Exception:
                pass

    def save_queue(self):
        try:
            data = {
                "active": self.active_task,
                "waiting": self.waiting_queue,
                "completed": self.completed_history[:50],
                "is_paused": self.is_paused
            }
            with open(QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def adopt_running_process(self):
        proc = get_tdl_process()
        if proc:
            try:
                cmd = proc.cmdline()
                chat_name = "当前下载任务"
                chat_id = 0
                if "-d" in cmd:
                    d_idx = cmd.index("-d")
                    if d_idx + 1 < len(cmd):
                        chat_name = Path(cmd[d_idx + 1]).name
                if "-f" in cmd:
                    f_idx = cmd.index("-f")
                    if f_idx + 1 < len(cmd):
                        f_name = Path(cmd[f_idx + 1]).name
                        m = re.search(r'_(\d+)', f_name)
                        if m:
                            chat_id = int(m.group(1))

                self.active_task = {
                    "id": str(uuid.uuid4())[:8],
                    "chat_id": chat_id,
                    "chat_name": chat_name,
                    "task_type": "all",
                    "threads": 8,
                    "limit": 4,
                    "proxy": DEFAULT_PROXY,
                    "status": "downloading",
                    "started_at": time.time(),
                    "pid": proc.pid
                }
                self.is_paused = False
                monitor.watchdog_status = f"正在下载: {chat_name}"
            except Exception:
                pass

    def add_task(self, task_params: dict, priority: str = "queue") -> Dict[str, Any]:
        with self.lock:
            task_id = str(uuid.uuid4())[:8]
            new_task = {
                "id": task_id,
                "chat_id": task_params["chat_id"],
                "chat_name": task_params["chat_name"],
                "task_type": task_params.get("task_type", "all"),
                "message_id": task_params.get("message_id"),
                "message_ids": task_params.get("message_ids"),
                "file_name": task_params.get("file_name"),
                "threads": task_params.get("threads", 8),
                "limit": task_params.get("limit", 4),
                "proxy": task_params.get("proxy", DEFAULT_PROXY),
                "status": "waiting",
                "added_at": time.time(),
                "started_at": None,
                "completed_at": None
            }

            proc = get_tdl_process()

            if priority == "now":
                if proc:
                    try:
                        proc.kill()
                        time.sleep(1.0)
                    except Exception:
                        pass
                    if self.active_task:
                        self.active_task["status"] = "waiting"
                        self.waiting_queue.insert(0, self.active_task)

                self.is_paused = False
                res = self._execute_task(new_task)
                if res.get("success"):
                    self.active_task = new_task
                    self.save_queue()
                    return {"success": True, "action": "started_now", "message": f"已立即开始下载「{new_task['chat_name']}」"}
                else:
                    return res
            else:
                if not proc and not self.is_paused:
                    res = self._execute_task(new_task)
                    if res.get("success"):
                        self.active_task = new_task
                        self.save_queue()
                        return {"success": True, "action": "started_now", "message": f"队列空闲，已立即开始下载「{new_task['chat_name']}」"}
                    else:
                        return res
                else:
                    self.waiting_queue.append(new_task)
                    pos = len(self.waiting_queue)
                    self.save_queue()
                    return {"success": True, "action": "queued", "position": pos, "message": f"已将「{new_task['chat_name']}」加入下载排队队列 (当前排在第 {pos} 位)"}

    def _execute_task(self, task: dict) -> Dict[str, Any]:
        safe_name = sanitize_name(task["chat_name"])
        target_dir = BASE_DOWNLOAD_DIR / safe_name
        target_dir.mkdir(parents=True, exist_ok=True)

        if task.get("custom_json") and Path(task["custom_json"]).exists():
            use_json = Path(task["custom_json"])
        else:
            videos_json = META_DIR / f"{safe_name}_{task['chat_id']}_videos.json"
            full_json = META_DIR / f"{safe_name}_{task['chat_id']}.json"

            if not videos_json.exists():
                if full_json.exists():
                    extract_videos_json(full_json, videos_json)
                else:
                    cmd_export = [
                        str(TDL_EXE), "chat", "export",
                        "-c", str(task["chat_id"]),
                        "-o", str(full_json),
                        "--proxy", task.get("proxy", DEFAULT_PROXY)
                    ]
                    try:
                        res = subprocess.run(cmd_export, capture_output=True, text=True, timeout=180)
                        if res.returncode == 0:
                            extract_videos_json(full_json, videos_json)
                        else:
                            return {"success": False, "message": f"自动导出媒体清单失败: {res.stderr or res.stdout}"}
                    except Exception as e:
                        return {"success": False, "message": f"导出清单超时或异常: {e}"}

            raw_use_json = videos_json if videos_json.exists() else full_json
            if not raw_use_json.exists():
                return {"success": False, "message": "未找到媒体清单，请先导出！"}

            # ========== SQLite 智能防重与差量过滤 ==========
            use_json = raw_use_json
            try:
                with open(raw_use_json, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                all_msgs = manifest.get("messages", [])
                
                downloaded_ids = get_downloaded_message_ids(task["chat_id"])
                pending_msgs = [m for m in all_msgs if m.get("id") not in downloaded_ids]

                if not pending_msgs and all_msgs:
                    task["status"] = "completed"
                    task["completed_at"] = time.time()
                    self.completed_history.insert(0, task)
                    self.save_queue()
                    monitor.watchdog_status = f"「{task['chat_name']}」全部视频已在防重库中，已安全跳过"
                    threading.Timer(1.0, self.start_next_in_queue).start()
                    return {"success": True, "already_completed": True, "message": f"「{task['chat_name']}」全部视频已在防重库中（已下载或已迁移），无需重复下载！"}

                if len(pending_msgs) < len(all_msgs):
                    filtered_json = META_DIR / f"{safe_name}_{task['chat_id']}_pending.json"
                    manifest["messages"] = pending_msgs
                    with open(filtered_json, "w", encoding="utf-8") as f:
                        json.dump(manifest, f, ensure_ascii=False, indent=2)
                    use_json = filtered_json
            except Exception as e:
                use_json = raw_use_json

        cmd = [
            str(TDL_EXE),
            "download",
            "--continue",
            "-f", str(use_json),
            "-d", str(target_dir),
            "--skip-same",
            "-t", str(task.get("threads", 8)),
            "-l", str(task.get("limit", 4)),
            "--proxy", task.get("proxy", DEFAULT_PROXY)
        ]

        try:
            new_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            task["status"] = "downloading"
            task["started_at"] = time.time()
            task["pid"] = new_proc.pid
            monitor.watchdog_status = f"正在下载: {task['chat_name']}"
            return {"success": True, "pid": new_proc.pid, "message": f"已成功启动「{task['chat_name']}」下载"}
        except Exception as e:
            return {"success": False, "message": f"启动异常: {e}"}

    def stop_all(self) -> Dict[str, Any]:
        with self.lock:
            self.is_paused = True
            proc = get_tdl_process()
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass
            if self.active_task:
                self.active_task["status"] = "paused"
                self.waiting_queue.insert(0, self.active_task)
                self.active_task = None
            monitor.watchdog_status = "已暂停下载队列"
            self.save_queue()
            return {"success": True, "message": "已成功停止当前任务并暂停队列"}

    def resume_queue(self) -> Dict[str, Any]:
        with self.lock:
            self.is_paused = False
            self.save_queue()
            return self.start_next_in_queue()

    def start_next_in_queue(self) -> Dict[str, Any]:
        if self.is_paused:
            monitor.watchdog_status = "队列已暂停"
            return {"success": False, "message": "队列当前处于暂停状态"}
        if not self.waiting_queue:
            self.active_task = None
            monitor.watchdog_status = "空闲 / 排队队列已全部完成"
            self.save_queue()
            return {"success": True, "message": "排队队列已无待处理任务"}

        next_task = self.waiting_queue.pop(0)
        res = self._execute_task(next_task)
        if res.get("success"):
            self.active_task = next_task
            self.save_queue()
            return {"success": True, "message": f"已自动启动下一排队任务: 「{next_task['chat_name']}」"}
        else:
            next_task["status"] = "failed"
            self.completed_history.insert(0, next_task)
            self.save_queue()
            return self.start_next_in_queue()

queue_manager = DownloadQueueManager()

# ==================== 全量机器人媒体扫描器 ====================
class BotMediaScanner:
    def __init__(self):
        self.lock = threading.Lock()
        self.is_scanning = False
        self.total_bots = 0
        self.scanned_count = 0
        self.found_videos = 0
        self.current_bot_name = ""
        self.stop_requested = False

    def start_scan(self):
        with self.lock:
            if self.is_scanning:
                return {"success": False, "message": "扫描已在进行中"}
            self.is_scanning = True
            self.stop_requested = False
            self.scanned_count = 0
            self.found_videos = 0
            self.current_bot_name = "准备启动..."

        threading.Thread(target=self._scan_thread, daemon=True).start()
        return {"success": True, "message": "已启动全量机器人扫描"}

    def stop_scan(self):
        with self.lock:
            self.stop_requested = True
            self.is_scanning = False
            return {"success": True, "message": "已终止扫描"}

    def get_status(self):
        with self.lock:
            return {
                "is_scanning": self.is_scanning,
                "total_bots": self.total_bots,
                "scanned_count": self.scanned_count,
                "progress": f"{self.scanned_count}/{self.total_bots}" if self.total_bots > 0 else "0/0",
                "found_videos": self.found_videos,
                "current_bot_name": self.current_bot_name
            }

    def _scan_thread(self):
        try:
            if not CHATS_JSON.exists():
                with self.lock:
                    self.is_scanning = False
                return

            with open(CHATS_JSON, "r", encoding="utf-8") as f:
                chats = json.load(f)

            results = {}
            if BOT_COUNTS_JSON.exists():
                try:
                    with open(BOT_COUNTS_JSON, "r", encoding="utf-8") as f:
                        results = json.load(f)
                except Exception:
                    pass

            bots = []
            for c in chats:
                u = str(c.get("username") or "").lower()
                v = str(c.get("visible_name") or "").lower()
                cid_str = str(c["id"])
                is_bot = (u.endswith("bot") or "bot" in u or "机器人" in v or "bot" in v or 
                          cid_str in results or c.get("type") == "bot" or c.get("is_bot") is True)
                if is_bot:
                    bots.append(c)

            with self.lock:
                self.total_bots = len(bots)

            for idx, b in enumerate(bots):
                with self.lock:
                    if self.stop_requested:
                        break
                    self.scanned_count = idx + 1
                    self.current_bot_name = b.get("visible_name") or "Bot"

                cid = b["id"]
                cid_str = str(cid)
                name = b.get("visible_name") or "Bot"
                u = b.get("username")
                tmp_path = META_DIR / f"scan_{cid}.json"

                sync_session_cache()
                cmd = [
                    str(TDL_EXE), "chat", "export",
                    "-c", str(cid),
                    "-T", "last", "-i", "40",
                    "--all", "--raw",
                    "-o", str(tmp_path),
                    "--storage", f"path={SESSION_CACHE_DIR},type=bolt",
                    "--proxy", DEFAULT_PROXY
                ]
                try:
                    res = subprocess.run(cmd, capture_output=True, timeout=20)
                    if tmp_path.exists():
                        with open(tmp_path, "r", encoding="utf-8") as jf:
                            data = json.load(jf)
                        msgs = data.get("messages", [])
                        vmsgs = []
                        gt_10 = 0
                        gt_30 = 0
                        gt_60 = 0
                        for m in msgs:
                            fname = m.get("file", "")
                            raw = m.get("raw") or {}
                            doc = (raw.get("Media") or {}).get("Document") or {}
                            if re.search(r'\.(mp4|mov|mkv|avi|webm)$', fname, re.I) or (doc.get("MimeType", "").startswith("video")):
                                vmsgs.append(m)
                                dur = 0
                                for a in doc.get("Attributes") or []:
                                    if isinstance(a, dict) and "Duration" in a: dur = a["Duration"]
                                if dur >= 10: gt_10 += 1
                                if dur >= 30: gt_30 += 1
                                if dur >= 60: gt_60 += 1

                        results[cid_str] = {
                            "chat_id": cid,
                            "visible_name": name,
                            "username": u,
                            "total_media": len(msgs),
                            "video_count": len(vmsgs),
                            "videos_gt_10s": gt_10,
                            "videos_gt_30s": gt_30,
                            "videos_gt_60s": gt_60
                        }
                        if len(vmsgs) > 0:
                            with self.lock:
                                self.found_videos += len(vmsgs)
                            # 自动生成 videos_json
                            safe_name = sanitize_name(name)
                            v_file = META_DIR / f"{safe_name}_{cid}_videos.json"
                            with open(v_file, "w", encoding="utf-8") as vf:
                                json.dump({"id": cid, "messages": vmsgs}, vf, ensure_ascii=False)
                        try:
                            tmp_path.unlink()
                        except Exception:
                            pass
                    else:
                        if cid_str not in results:
                            results[cid_str] = {
                                "chat_id": cid,
                                "visible_name": name,
                                "username": u,
                                "total_media": 0,
                                "video_count": 0,
                                "videos_gt_10s": 0,
                                "videos_gt_30s": 0,
                                "videos_gt_60s": 0
                            }
                except Exception:
                    pass

                # 每5个保存一次
                if (idx + 1) % 5 == 0:
                    with open(BOT_COUNTS_JSON, "w", encoding="utf-8") as out_f:
                        json.dump(results, out_f, ensure_ascii=False, indent=2)

            with open(BOT_COUNTS_JSON, "w", encoding="utf-8") as out_f:
                json.dump(results, out_f, ensure_ascii=False, indent=2)

        finally:
            with self.lock:
                self.is_scanning = False
                self.current_bot_name = "扫描完成"

bot_scanner = BotMediaScanner()


# ==================== 守护线程 Watchdog ====================
def watchdog_loop():
    while True:
        try:
            proc = get_tdl_process()
            active_chat_name = queue_manager.active_task.get("chat_name") if queue_manager.active_task else None
            monitor.update_speed_and_quota(proc, active_chat_name)

            with queue_manager.lock:
                if queue_manager.active_task and not monitor.daily_limit_reached and not queue_manager.is_paused:
                    cur_task = queue_manager.active_task
                    safe_name = sanitize_name(cur_task["chat_name"])
                    target_dir = BASE_DOWNLOAD_DIR / safe_name

                    # 实时检查当前任务是否已 100% 下载完毕
                    is_completed = False
                    v_json = META_DIR / f"{safe_name}_{cur_task['chat_id']}_videos.json"
                    if v_json.exists():
                        try:
                            with open(v_json, "r", encoding="utf-8") as jf:
                                target_count = len(json.load(jf).get("messages", []))
                            completed_count = sum(1 for f in os.scandir(target_dir) if f.is_file() and not f.name.endswith(".tmp")) if target_dir.exists() else 0
                            if target_count > 0 and completed_count >= target_count:
                                is_completed = True
                        except Exception:
                            pass

                    if is_completed:
                        if proc:
                            try:
                                proc.kill()
                            except Exception:
                                pass
                        cur_task["status"] = "completed"
                        cur_task["completed_at"] = time.time()
                        queue_manager.completed_history.insert(0, cur_task)
                        queue_manager.active_task = None
                        queue_manager.save_queue()
                        threading.Thread(target=scan_and_index_existing_files, daemon=True).start()
                        monitor.watchdog_status = f"「{cur_task['chat_name']}」全部下载完毕"
                        queue_manager.start_next_in_queue()
                        continue

                    if proc:
                        monitor.watchdog_status = f"正在下载: {cur_task['chat_name']}"
                    else:
                        if monitor.auto_retry_enabled:
                            if check_tcp_port("192.168.8.11", 7890):
                                now = time.time()
                                if now - monitor.last_retry_time >= 10:
                                    monitor.watchdog_status = f"「{cur_task['chat_name']}」掉线，10秒后自动续传..."
                                    monitor.last_retry_time = now
                                    monitor.retry_count += 1
                                    queue_manager._execute_task(cur_task)
                            else:
                                monitor.watchdog_status = "代理连接异常，等待代理连通后自动重试..."
                elif not proc and not queue_manager.active_task:
                    if monitor.daily_limit_reached:
                        monitor.watchdog_status = f"今日已达限额 ({monitor.daily_limit_gb} GB)，已暂停"
                    elif queue_manager.is_paused:
                        monitor.watchdog_status = "队列已暂停"
                    else:
                        monitor.watchdog_status = "空闲"
        except Exception:
            pass
        time.sleep(1.2)

threading.Thread(target=watchdog_loop, daemon=True).start()

# ==================== 请求结构体 ====================
class QueueAddRequest(BaseModel):
    chat_id: int
    chat_name: str
    task_type: Optional[str] = "all"
    message_id: Optional[int] = None
    message_ids: Optional[List[int]] = None
    file_name: Optional[str] = None
    priority: Optional[str] = "queue"

class DownloadRequest(BaseModel):
    chat_id: int
    chat_name: str
    threads: int = 8
    limit: int = 4
    proxy: str = DEFAULT_PROXY
    switch_if_running: bool = False
    auto_export: bool = True
    export_limit: Optional[int] = None

class SettingsRequest(BaseModel):
    daily_limit_gb: float
    auto_retry_enabled: bool

class ExportRequest(BaseModel):
    chat_id: int
    chat_name: str
    limit: Optional[int] = None
    proxy: str = DEFAULT_PROXY

# ==================== API 路由 ====================
@app.get("/api/status")
def get_status():
    proc = get_tdl_process()
    is_running = proc is not None
    proc_info = None
    if is_running:
        try:
            mem = proc.memory_info().rss / (1024 * 1024)
            cpu = proc.cpu_percent(interval=0.05)
            cmd = proc.cmdline()
            proc_info = {
                "pid": proc.pid,
                "memory_mb": round(mem, 2),
                "cpu_percent": round(cpu, 1),
                "create_time": proc.create_time(),
                "cmdline": " ".join(cmd) if cmd else ""
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            is_running = False

    proxy_online = check_tcp_port("192.168.8.11", 7890)
    today_gb = round(monitor.today_downloaded_bytes / (1024**3), 3)

    return {
        "running": is_running,
        "process": proc_info,
        "port": SERVER_PORT,
        "speed_human": monitor.speed_human,
        "speed_bytes_sec": monitor.speed_bytes_sec,
        "speed_mb_sec": round(monitor.speed_bytes_sec / (1024*1024), 2),
        "today_downloaded_gb": today_gb,
        "daily_limit_gb": monitor.daily_limit_gb,
        "daily_limit_reached": monitor.daily_limit_reached,
        "auto_retry_enabled": monitor.auto_retry_enabled,
        "retry_count": monitor.retry_count,
        "watchdog_status": monitor.watchdog_status,
        "proxy_online": proxy_online,
        "proxy_url": DEFAULT_PROXY,
        "base_dir": str(BASE_DOWNLOAD_DIR),
        "meta_dir": str(META_DIR),
        "tdl_exists": TDL_EXE.exists(),
        "active_task": queue_manager.active_task,
        "waiting_count": len(queue_manager.waiting_queue),
        "is_paused": queue_manager.is_paused
    }


@app.post("/api/bots/scan")
def api_start_bot_scan():
    return bot_scanner.start_scan()

@app.get("/api/bots/scan/status")
def api_get_bot_scan_status():
    return bot_scanner.get_status()

@app.post("/api/bots/scan/stop")
def api_stop_bot_scan():
    return bot_scanner.stop_scan()

@app.get("/api/chats")
def list_chats(query: Optional[str] = None, chat_type: Optional[str] = None):
    if not CHATS_JSON.exists():
        return {"total": 0, "chats": []}
    try:
        with open(CHATS_JSON, "r", encoding="utf-8") as f:
            chats = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法解析 chats.json: {str(e)}")

    bot_counts = {}
    if BOT_COUNTS_JSON.exists():
        try:
            with open(BOT_COUNTS_JSON, "r", encoding="utf-8") as f:
                bot_counts = json.load(f)
        except Exception:
            pass

    # 动态扫描所有已有视频清单建立精确统计 (含时长分档: >10s, >30s, >60s)
    dynamic_stats = {}
    for vf in META_DIR.glob("*_videos.json"):
        m = re.search(r'_(\d+)_videos\.json$', vf.name)
        if m:
            cid = m.group(1)
            try:
                with open(vf, "r", encoding="utf-8") as jf:
                    vd = json.load(jf)
                vmsgs = vd.get("messages", [])
                gt_10 = 0
                gt_30 = 0
                gt_60 = 0
                for vm in vmsgs:
                    raw = vm.get("raw") or {}
                    doc = (raw.get("Media") or {}).get("Document") or {}
                    dur = 0
                    for a in doc.get("Attributes") or []:
                        if isinstance(a, dict) and "Duration" in a:
                            dur = a["Duration"]
                    if dur >= 10: gt_10 += 1
                    if dur >= 30: gt_30 += 1
                    if dur >= 60: gt_60 += 1
                dynamic_stats[cid] = {
                    "count": len(vmsgs),
                    "gt_10": gt_10,
                    "gt_30": gt_30,
                    "gt_60": gt_60
                }
            except Exception:
                pass

    active_cid = queue_manager.active_task.get("chat_id") if queue_manager.active_task else None
    queued_cids = {t["chat_id"] for t in queue_manager.waiting_queue}

    for c in chats:
        cid = c.get("id")
        cid_str = str(cid)
        u = str(c.get("username") or "").lower()
        v = str(c.get("visible_name") or "").lower()
        is_bot = (u.endswith("bot") or "bot" in u or "机器人" in v or "bot" in v or 
                  "提取" in v or "助手" in v or "存储" in v or "储存" in v or "仓库" in v or "网盘" in v or
                  cid_str in bot_counts or c.get("type") == "bot" or c.get("is_bot") is True)
        c["is_bot"] = is_bot
        binfo = bot_counts.get(cid_str) or {}
        dyn = dynamic_stats.get(cid_str) or {}
        vcount = dyn.get("count") if "count" in dyn else (binfo.get("video_count", 0) if binfo else 0)
        c["video_count"] = vcount
        c["videos_gt_10s"] = dyn.get("gt_10") if "gt_10" in dyn else (binfo.get("videos_gt_10s", vcount) if binfo else vcount)
        c["videos_gt_30s"] = dyn.get("gt_30") if "gt_30" in dyn else (binfo.get("videos_gt_30s", 0) if binfo else 0)
        c["videos_gt_60s"] = dyn.get("gt_60") if "gt_60" in dyn else (binfo.get("videos_gt_60s", 0) if binfo else 0)
        c["total_media"] = binfo.get("total_media", vcount) if binfo else vcount
        c["photo_count"] = max(0, c["total_media"] - vcount)
        c["video_note"] = f"({vcount}个视频)" if vcount > 0 else ""

        if cid == active_cid:
            c["queue_status"] = "downloading"
        elif cid in queued_cids:
            c["queue_status"] = "queued"
        else:
            c["queue_status"] = "none"

    if chat_type and chat_type != "all":
        if chat_type == "bot":
            chats = [c for c in chats if c.get("is_bot")]
            chats.sort(key=lambda x: -x.get("video_count", 0))
        elif chat_type in ("group", "chat"):
            chats = [c for c in chats if c.get("type") in ("group", "chat") and not c.get("is_bot")]
        elif chat_type == "channel":
            chats = [c for c in chats if c.get("type") == "channel" and not c.get("is_bot")]
        elif chat_type == "private":
            chats = [c for c in chats if c.get("type") == "private" and not c.get("is_bot")]
        else:
            chats = [c for c in chats if c.get("type") == chat_type]

    if query:
        q = query.lower().strip()
        filtered = []
        for c in chats:
            name = str(c.get("visible_name") or "").lower()
            uname = str(c.get("username") or "").lower()
            cid = str(c.get("id") or "")
            vnote = str(c.get("video_note") or "").lower()
            if q in name or q in uname or q in cid or q in vnote:
                filtered.append(c)
        chats = filtered

    return {
        "total": len(chats),
        "chats": chats
    }

@app.get("/api/progress")
def get_progress(chat_id: int = Query(...), chat_name: str = Query(...)):
    safe_name = sanitize_name(chat_name)
    chat_dir = BASE_DOWNLOAD_DIR / safe_name
    
    total_target_videos = 0
    videos_json = META_DIR / f"{safe_name}_{chat_id}_videos.json"
    full_json = META_DIR / f"{safe_name}_{chat_id}.json"
    preview_json = META_DIR / f"{safe_name}_{chat_id}_preview.json"

    if videos_json.exists():
        try:
            with open(videos_json, "r", encoding="utf-8") as f:
                d = json.load(f)
                total_target_videos = len(d.get("messages", []))
        except Exception:
            pass
    elif full_json.exists():
        vmsgs = extract_videos_json(full_json, videos_json)
        total_target_videos = len(vmsgs)
    elif preview_json.exists():
        vmsgs = extract_videos_json(preview_json, videos_json)
        total_target_videos = len(vmsgs)

    completed_files = []
    tmp_files = []
    total_bytes = 0

    if chat_dir.exists():
        try:
            for entry in os.scandir(chat_dir):
                if entry.is_file():
                    stat = entry.stat()
                    total_bytes += stat.st_size
                    item = {
                        "name": entry.name,
                        "size_bytes": stat.st_size,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "mtime": stat.st_mtime,
                        "is_tmp": entry.name.endswith(".tmp")
                    }
                    if entry.name.endswith(".tmp"):
                        tmp_files.append(item)
                    else:
                        completed_files.append(item)
        except Exception:
            pass

    completed_files.sort(key=lambda x: x["mtime"], reverse=True)
    tmp_files.sort(key=lambda x: x["mtime"], reverse=True)

    pct = round((len(completed_files) / total_target_videos * 100), 1) if total_target_videos > 0 else 0.0
    remaining_count = max(0, total_target_videos - len(completed_files))

    is_completed = (total_target_videos > 0 and len(completed_files) >= total_target_videos)
    if is_completed:
        pct = 100.0
        remaining_count = 0

    is_currently_downloading = False
    if not is_completed:
        if queue_manager.active_task and queue_manager.active_task.get("chat_id") == chat_id:
            is_currently_downloading = True

    return {
        "chat_id": chat_id,
        "chat_name": chat_name,
        "safe_name": safe_name,
        "dir_exists": chat_dir.exists(),
        "has_exported_json": videos_json.exists() or full_json.exists() or preview_json.exists(),
        "total_target_videos": total_target_videos,
        "completed_count": len(completed_files),
        "tmp_count": len(tmp_files),
        "remaining_count": remaining_count,
        "percentage": pct,
        "is_completed": is_completed,
        "total_size_gb": round(total_bytes / (1024**3), 2),
        "total_size_mb": round(total_bytes / (1024**2), 2),
        "is_currently_downloading": is_currently_downloading,
        "recent_files": (tmp_files + completed_files)[:15],
    }

@app.get("/api/tasks")
def list_tasks():
    chats_by_id = {}
    chats_by_name = {}
    if CHATS_JSON.exists():
        try:
            with open(CHATS_JSON, "r", encoding="utf-8") as f:
                chats = json.load(f)
            for c in chats:
                chats_by_id[c.get("id")] = c
                if c.get("visible_name"):
                    chats_by_name[c.get("visible_name")] = c
        except Exception:
            pass

    tasks = []
    seen_chat_ids = set()

    if BASE_DOWNLOAD_DIR.exists():
        for entry in os.scandir(BASE_DOWNLOAD_DIR):
            if entry.is_dir() and entry.name != "_tdl_meta":
                folder_name = entry.name
                files = []
                try:
                    files = [f for f in os.scandir(entry.path) if f.is_file()]
                except Exception:
                    pass
                completed = [f for f in files if not f.name.endswith('.tmp')]
                tmps = [f for f in files if f.name.endswith('.tmp')]
                total_size = sum(f.stat().st_size for f in files)

                cid = None
                target_count = 0
                for mf in META_DIR.glob(f"{folder_name}_*_videos.json"):
                    m = re.search(r'_(\d+)_videos\.json$', mf.name)
                    if m:
                        cid = int(m.group(1))
                        try:
                            with open(mf, "r", encoding="utf-8") as jf:
                                d = json.load(jf)
                                target_count = len(d.get("messages", []))
                        except Exception:
                            pass
                        break

                chat_info = chats_by_id.get(cid) or chats_by_name.get(folder_name) or {}
                if not cid and chat_info:
                    cid = chat_info.get("id")
                
                if cid:
                    seen_chat_ids.add(cid)

                is_comp = (target_count > 0 and len(completed) >= target_count)
                is_active = False
                if not is_comp and queue_manager.active_task:
                    if queue_manager.active_task.get("chat_id") == cid or queue_manager.active_task.get("chat_name") == folder_name:
                        is_active = True

                pct = 100.0 if is_comp else (round(len(completed) / target_count * 100, 1) if target_count else 0)
                status_type = "completed" if is_comp else ("downloading" if is_active else "paused")

                tasks.append({
                    "chat_name": chat_info.get("visible_name") or folder_name,
                    "chat_id": cid,
                    "type": chat_info.get("type", "channel"),
                    "username": chat_info.get("username"),
                    "completed_count": len(completed),
                    "tmp_count": len(tmps),
                    "total_size_gb": round(total_size / (1024**3), 2),
                    "target_count": target_count,
                    "percentage": pct,
                    "is_active": is_active,
                    "status": status_type
                })

    tasks.sort(key=lambda x: (not x["is_active"], x["status"] == "completed", -x["completed_count"]))
    return {"total": len(tasks), "tasks": tasks}


@app.get("/api/thumb")
def get_thumb(chat_id: int = Query(...), msg_id: int = Query(...), file: Optional[str] = None):
    for f in THUMB_CACHE_DIR.glob(f"*{msg_id}*"):
        if f.is_file() and f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
            return FileResponse(f, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Thumbnail not ready")

@app.get("/api/queue")
def get_queue(chat_id: Optional[int] = Query(None), chat_name: Optional[str] = Query(None)):
    active_in_flight = []
    active_task = queue_manager.active_task
    if active_task:
        safe_name = sanitize_name(active_task.get("chat_name", ""))
        chat_dir = BASE_DOWNLOAD_DIR / safe_name
        if chat_dir.exists():
            try:
                for entry in os.scandir(chat_dir):
                    if entry.is_file() and entry.name.endswith(".tmp"):
                        stat = entry.stat()
                        tracker = monitor.file_speed_tracker.get(entry.name, {})
                        speed_human = tracker.get("speed_human", "分块传输中...")
                        speed_raw = tracker.get("speed_bytes_sec", 0.0)
                        active_in_flight.append({
                            "raw_name": entry.name,
                            "file": entry.name[:-4],
                            "size_bytes": stat.st_size,
                            "size_mb": round(stat.st_size / (1024*1024), 2),
                            "speed_human": speed_human,
                            "speed_bytes_sec": speed_raw,
                            "status": "正在下载"
                        })
            except Exception:
                pass
        active_in_flight.sort(key=lambda x: x["size_mb"], reverse=True)

    res = {
        "active": queue_manager.active_task,
        "waiting": queue_manager.waiting_queue,
        "completed": queue_manager.completed_history,
        "is_paused": queue_manager.is_paused,
        "speed_human": monitor.speed_human,
        "speed_bytes_sec": monitor.speed_bytes_sec,
        "in_flight": active_in_flight
    }

    if chat_id is not None and chat_name:
        safe_name = sanitize_name(chat_name)
        chat_dir = BASE_DOWNLOAD_DIR / safe_name
        videos_json = META_DIR / f"{safe_name}_{chat_id}_videos.json"
        full_json = META_DIR / f"{safe_name}_{chat_id}.json"

        messages = []
        use_json = videos_json if videos_json.exists() else full_json
        if use_json.exists():
            try:
                with open(use_json, "r", encoding="utf-8") as f:
                    d = json.load(f)
                messages = d.get("messages", [])
            except Exception:
                pass

        completed_ids = set()
        if chat_dir.exists():
            try:
                for entry in os.scandir(chat_dir):
                    if entry.is_file() and not entry.name.endswith(".tmp"):
                        m = re.match(r'^\d+_(\d+)_(.+)$', entry.name)
                        if m:
                            completed_ids.add(int(m.group(1)))
            except Exception:
                pass

        next_queued = []
        pos = 1
        for msg in messages:
            mid = msg.get("id")
            if mid not in completed_ids:
                next_queued.append({
                    "queue_pos": pos,
                    "message_id": mid,
                    "file": msg.get("file", f"video_{mid}.mp4"),
                    "status": "等待下载"
                })
                pos += 1
            if len(next_queued) >= 60:
                break

        res.update({
            "source_chat_id": chat_id,
            "source_chat_name": chat_name,
            "total_target_videos": len(messages),
            "completed_count": len(completed_ids),
            "next_queued": next_queued
        })

    return res

@app.post("/api/queue/add")
def queue_add(req: QueueAddRequest):
    return queue_manager.add_task(req.dict(), priority=req.priority or "queue")

@app.post("/api/queue/move")
def queue_move(task_id: str = Query(...), direction: str = Query(...)):
    with queue_manager.lock:
        idx = next((i for i, t in enumerate(queue_manager.waiting_queue) if t["id"] == task_id), None)
        if idx is None:
            return {"success": False, "message": "未在等待队列中找到该任务"}
        task = queue_manager.waiting_queue.pop(idx)
        if direction == "up" and idx > 0:
            queue_manager.waiting_queue.insert(idx - 1, task)
        elif direction == "down" and idx < len(queue_manager.waiting_queue):
            queue_manager.waiting_queue.insert(idx + 1, task)
        elif direction == "top":
            queue_manager.waiting_queue.insert(0, task)
        else:
            queue_manager.waiting_queue.insert(idx, task)
        queue_manager.save_queue()
        return {"success": True, "message": "队列排队顺序已调整"}

@app.post("/api/queue/remove")
def queue_remove(task_id: str = Query(...)):
    with queue_manager.lock:
        idx = next((i for i, t in enumerate(queue_manager.waiting_queue) if t["id"] == task_id), None)
        if idx is not None:
            removed = queue_manager.waiting_queue.pop(idx)
            queue_manager.save_queue()
            return {"success": True, "message": f"已将「{removed.get('chat_name')}」从排队列表中移除"}
        return {"success": False, "message": "未找到指定任务"}

@app.post("/api/queue/skip")
def queue_skip():
    with queue_manager.lock:
        proc = get_tdl_process()
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
        if queue_manager.active_task:
            queue_manager.active_task["status"] = "skipped"
            queue_manager.completed_history.insert(0, queue_manager.active_task)
            queue_manager.active_task = None
        queue_manager.save_queue()
        res = queue_manager.start_next_in_queue()
        return {"success": True, "message": "已跳过当前任务并开始下一个任务", "next": res}

@app.post("/api/download/resume")
def resume_download():
    return queue_manager.resume_queue()

@app.get("/api/chat/preview")
def get_chat_preview(chat_id: int = Query(...), chat_name: str = Query(...), refresh: bool = Query(False)):
    safe_name = sanitize_name(chat_name)
    chat_dir = BASE_DOWNLOAD_DIR / safe_name
    videos_json = META_DIR / f"{safe_name}_{chat_id}_videos.json"
    full_json = META_DIR / f"{safe_name}_{chat_id}.json"
    preview_json = META_DIR / f"{safe_name}_{chat_id}_preview.json"

    # 优先选择具有真实 raw 元数据和时长的文件
    use_json = None
    if not refresh:
        if file_has_raw_metadata(preview_json):
            use_json = preview_json
        elif file_has_raw_metadata(full_json):
            use_json = full_json
        elif file_has_raw_metadata(videos_json):
            use_json = videos_json

    # 如果现有文件都没有 raw 元数据(如旧版极简导出)，或者用户请求刷新：立即抓取完整 raw 消息
    if (use_json is None or refresh) and TDL_EXE.exists():
        sync_session_cache()
        cmd_export = [
            str(TDL_EXE), "chat", "export",
            "-c", str(chat_id),
            "-T", "last", "-i", "80",
            "--all", "--raw",
            "-o", str(preview_json),
            "--storage", f"path={SESSION_CACHE_DIR},type=bolt",
            "--proxy", DEFAULT_PROXY
        ]
        try:
            res = subprocess.run(cmd_export, capture_output=True, timeout=35)
            if res.returncode == 0 and preview_json.exists():
                use_json = preview_json
                extract_videos_json(preview_json, videos_json)
        except Exception:
            pass

    # 保底回退
    if use_json is None:
        for pj in [preview_json, full_json, videos_json]:
            if pj.exists():
                use_json = pj
                break

    cards = []
    if use_json and use_json.exists():
        try:
            with open(use_json, "r", encoding="utf-8") as f:
                d = json.load(f)
            msgs = d.get("messages", [])

            # 构建相册关联映射 (GroupedID -> Photo)
            group_photo_map = {}
            for m in msgs:
                raw = m.get("raw") or {}
                gid = raw.get("GroupedID")
                media = raw.get("Media") or {}
                if gid and media.get("Photo"):
                    group_photo_map[gid] = m

            completed_fnames = set()
            tmp_fnames = set()
            completed_ids = set()
            if chat_dir.exists():
                for entry in os.scandir(chat_dir):
                    if entry.is_file():
                        m_id = re.match(r'^\d+_(\d+)_(.+)$', entry.name)
                        if m_id:
                            mid_val = int(m_id.group(1))
                            if entry.name.endswith(".tmp"):
                                tmp_fnames.add(m_id.group(2)[:-4])
                            else:
                                completed_ids.add(mid_val)
                                completed_fnames.add(m_id.group(2))
                        else:
                            if entry.name.endswith(".tmp"):
                                tmp_fnames.add(entry.name[:-4])
                            else:
                                completed_fnames.add(entry.name)

            for m in msgs[:80]:
                mid = m.get("id")
                raw = m.get("raw") or {}
                media = raw.get("Media") or {}
                doc = media.get("Document") or {}
                photo = media.get("Photo") or {}
                fname = m.get("file") or ""
                gid = raw.get("GroupedID")

                is_photo = bool(photo)
                is_video = bool(doc) or bool(re.search(r'\.(mp4|mov|mkv|avi|webm)$', fname, re.I))

                if not is_photo and not is_video:
                    continue

                if is_photo and not fname:
                    fname = f"{photo.get('ID', mid)}.jpg"
                elif is_video and not fname:
                    fname = f"video_{mid}.mp4"

                duration = 0
                w, h = 0, 0
                attrs = doc.get("Attributes") or []
                for a in attrs:
                    if isinstance(a, dict):
                        if "Duration" in a:
                            duration = a["Duration"]
                        if "W" in a and "H" in a:
                            w, h = a["W"], a["H"]

                # 检查本地已下载视频是否存在
                is_downloaded = mid in completed_ids or fname in completed_fnames
                is_downloading = fname in tmp_fnames
                local_video_file = None

                if is_video and chat_dir.exists():
                    local_cand = list(chat_dir.glob(f"*_{mid}_*")) + ([chat_dir / fname] if fname and (chat_dir / fname).exists() else [])
                    for vc in local_cand:
                        if vc.is_file() and vc.suffix.lower() in [".mp4", ".mkv", ".mov", ".avi"] and not vc.name.endswith(".tmp"):
                            local_video_file = vc
                            # 如果从 JSON 没能解析出时长，利用 OpenCV 毫秒级直接读取本地视频时长
                            if duration == 0:
                                try:
                                    cap = cv2.VideoCapture(str(vc))
                                    fps = cap.get(cv2.CAP_PROP_FPS)
                                    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                                    cap.release()
                                    if fps > 0 and frames > 0:
                                        duration = round(frames / fps, 1)
                                except Exception:
                                    pass
                            break

                duration_human = ""
                if duration > 0:
                    mins = int(duration // 60)
                    secs = int(duration % 60)
                    duration_human = f"{mins:02d}:{secs:02d}"

                res_str = f"{h}p" if h > 0 else ""
                size_bytes = doc.get("Size") or m.get("size") or 0
                if is_photo and not size_bytes:
                    for s_size in photo.get("Sizes") or []:
                        if s_size.get("Type") in ["x", "y", "m"]:
                            size_bytes = s_size.get("Size", 0)
                            w, h = s_size.get("W", w), s_size.get("H", h)

                size_human = f"{size_bytes / (1024*1024):.1f} MB" if size_bytes > 0 else "--"

                # 缩略图获取与高清处理
                thumb_url = None
                is_hd_thumb = False

                for cf in THUMB_CACHE_DIR.glob(f"*{mid}*"):
                    if cf.is_file() and cf.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                        thumb_url = f"/api/thumb?chat_id={chat_id}&msg_id={mid}&file={cf.name}"
                        is_hd_thumb = True
                        break

                if not is_hd_thumb and local_video_file:
                    try:
                        cap = cv2.VideoCapture(str(local_video_file))
                        ret, frame = cap.read()
                        cap.release()
                        if ret:
                            out_frame = THUMB_CACHE_DIR / f"frame_{chat_id}_{mid}.jpg"
                            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            img = Image.fromarray(rgb)
                            img.thumbnail((640, 640), Image.Resampling.LANCZOS)
                            img.save(out_frame, quality=85)
                            thumb_url = f"/api/thumb?chat_id={chat_id}&msg_id={mid}&file={out_frame.name}"
                            is_hd_thumb = True
                    except Exception:
                        pass

                if not is_hd_thumb and is_video and gid and gid in group_photo_map:
                    p_item = group_photo_map[gid]
                    p_mid = p_item.get("id")
                    for cf in THUMB_CACHE_DIR.glob(f"*{p_mid}*"):
                        if cf.is_file():
                            thumb_url = f"/api/thumb?chat_id={chat_id}&msg_id={p_mid}&file={cf.name}"
                            is_hd_thumb = True
                            break

                if not thumb_url:
                    sizes_list = photo.get("Sizes", []) if is_photo else doc.get("Thumbs", [])
                    for t in sizes_list:
                        if isinstance(t, dict) and t.get("Type") == "i" and t.get("Bytes"):
                            thumb_url = stripped_thumb_to_base64(t.get("Bytes"))
                            is_hd_thumb = False
                            break

                cards.append({
                    "id": mid,
                    "file_name": fname,
                    "text": raw.get("Message") or m.get("text") or "",
                    "size_bytes": size_bytes,
                    "size_human": size_human,
                    "date": datetime.datetime.fromtimestamp(m.get("date") or raw.get("Date") or time.time()).strftime("%Y-%m-%d") if (m.get("date") or raw.get("Date")) else "",
                    "views": raw.get("Views"),
                    "duration_sec": duration,
                    "duration_human": duration_human,
                    "resolution": res_str,
                    "is_photo": is_photo,
                    "is_video": is_video,
                    "thumb": thumb_url,
                    "is_hd_thumb": is_hd_thumb,
                    "is_downloaded": is_downloaded,
                    "is_downloading": is_downloading
                })
        except Exception as e:
            print("Preview parse error:", e)

    return {
        "chat_id": chat_id,
        "chat_name": chat_name,
        "cards": cards,
        "total_cards": len(cards)
    }

@app.post("/api/download/start")
def start_download(req: DownloadRequest):
    return queue_manager.add_task(req.dict(), priority="now" if req.switch_if_running else "now")

@app.post("/api/download/stop")
def stop_download():
    return queue_manager.stop_all()

@app.post("/api/settings")
def update_settings(req: SettingsRequest):
    monitor.daily_limit_gb = max(0.0, req.daily_limit_gb)
    monitor.auto_retry_enabled = req.auto_retry_enabled
    monitor.save_stats()
    return {"success": True, "message": "策略配置已成功更新"}

@app.post("/api/open-folder")
def open_folder(chat_name: str = Query(...)):
    safe_name = sanitize_name(chat_name)
    chat_dir = BASE_DOWNLOAD_DIR / safe_name
    chat_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.startfile(str(chat_dir))
        return {"success": True, "message": f"已在资源管理器中打开: {chat_dir}"}
    except Exception as e:
        return {"success": False, "message": f"打开失败: {str(e)}"}

@app.get("/api/logs")
def get_logs(tail: int = 50):
    if not LOG_FILE.exists():
        return {"logs": ["暂无日志文件"]}
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return {"logs": [line.rstrip() for line in lines[-tail:]]}
    except Exception as e:
        return {"logs": [f"读取日志失败: {str(e)}"]}

# ==================== 跟踪追更与自动监控 API ====================
class TrackRequest(BaseModel):
    chat_id: int
    chat_name: str
    interval_seconds: Optional[int] = 1800
    auto_download: Optional[bool] = True
    is_active: Optional[bool] = True
    use_mcp: Optional[bool] = False

@app.get("/api/tracker/list")
def api_get_tracked():
    return {
        "success": True,
        "tracked": get_tracked_chats(),
        "status": tracker_engine.last_status
    }

@app.post("/api/tracker/save")
def api_save_track(req: TrackRequest):
    res = set_tracked_chat(
        chat_id=req.chat_id,
        chat_name=req.chat_name,
        interval_seconds=req.interval_seconds or 1800,
        auto_download=1 if req.auto_download else 0,
        is_active=1 if req.is_active else 0,
        use_mcp=1 if req.use_mcp else 0
    )
    return {"success": True, "chat": res}

@app.post("/api/tracker/toggle")
def api_toggle_track(chat_id: int = Query(...)):
    new_state = toggle_tracked_chat(chat_id)
    return {"success": True, "is_active": new_state}

@app.delete("/api/tracker/remove")
def api_remove_track(chat_id: int = Query(...)):
    remove_tracked_chat(chat_id)
    return {"success": True, "message": "已取消跟踪"}

@app.post("/api/tracker/check")
def api_check_track(chat_id: Optional[int] = Query(None)):
    if chat_id:
        return tracker_engine.check_chat_now(chat_id)
    return tracker_engine.check_all_now()

# ==================== 文件迁移与历史防重 API ====================
class MigrateRequest(BaseModel):
    source_folder: str
    target_dir: str
    mode: Optional[str] = "move"
    preserve_subfolder: Optional[bool] = True

@app.get("/api/migrate/summary")
def api_migrate_summary():
    return {"success": True, "folders": get_migration_summary()}

@app.post("/api/migrate/start")
def api_migrate_start(req: MigrateRequest):
    return migrate_files(
        source_folder=req.source_folder,
        target_dir=req.target_dir,
        mode=req.mode or "move",
        preserve_subfolder=req.preserve_subfolder
    )

@app.get("/api/downloads/stats")
def api_downloads_stats():
    return {"success": True, "stats": get_downloads_stats()}

@app.get("/api/downloads/list")
def api_downloads_list(chat_id: Optional[int] = None, status: Optional[str] = None,
                       query: Optional[str] = None, limit: int = 50, offset: int = 0):
    return {"success": True, "records": search_downloads(chat_id, status, query, limit, offset)}

@app.post("/api/downloads/scan_now")
def api_downloads_scan():
    return scan_and_index_existing_files()

@app.on_event("startup")
def on_startup():
    init_db()
    tracker_engine.set_queue_manager(queue_manager)
    tracker_engine.start()
    threading.Thread(target=scan_and_index_existing_files, daemon=True).start()

@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        return "<h1>Front-end index.html not found</h1>"
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print(" tdl Telegram Downloader Web 仪表盘服务已启动")
    print(f" 本地管理地址: http://127.0.0.1:{SERVER_PORT}")
    print("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=SERVER_PORT, log_level="warning")
