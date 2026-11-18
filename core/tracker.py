import json
import time
import threading
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional

from .config import TDL_BIN, META_DIR, DEFAULT_PROXY, MCP_GATEWAY_URL, BASE_DOWNLOAD_DIR
from .db import (
    get_tracked_chats, get_tracked_chat, update_track_progress,
    get_downloaded_message_ids, record_download
)

class AutoTracker:
    def __init__(self, queue_manager=None):
        self.queue_manager = queue_manager
        self.lock = threading.Lock()
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self.last_status: Dict[str, Any] = {
            "status": "idle",
            "last_run_time": None,
            "checking_chat": None
        }

    def set_queue_manager(self, qm):
        self.queue_manager = qm

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="AutoTrackerThread")
        self._thread.start()

    def stop(self):
        self.is_running = False

    def _worker_loop(self):
        while self.is_running:
            try:
                chats = get_tracked_chats()
                now = time.time()
                for c in chats:
                    if not self.is_running:
                        break
                    if not c.get("is_active"):
                        continue

                    interval = c.get("interval_seconds", 1800)
                    last_check = c.get("last_checked_at", 0)

                    if now - last_check >= interval:
                        self._check_single_chat(c)
                        # 每个会话检查之间略微等待，避免密集请求
                        time.sleep(2.0)
            except Exception as e:
                pass
            time.sleep(5.0)

    def check_chat_now(self, chat_id: int) -> Dict[str, Any]:
        """立即手动检查指定会话"""
        c = get_tracked_chat(chat_id)
        if not c:
            return {"success": False, "message": f"未找到跟踪会话: {chat_id}"}
        return self._check_single_chat(c)

    def check_all_now(self) -> Dict[str, Any]:
        """立即检查所有启用的跟踪会话"""
        chats = get_tracked_chats()
        results = []
        for c in chats:
            if c.get("is_active"):
                res = self._check_single_chat(c)
                results.append({"chat_name": c["chat_name"], "result": res})
        return {"success": True, "results": results}

    def _check_single_chat(self, chat_info: Dict[str, Any]) -> Dict[str, Any]:
        chat_id = chat_info["chat_id"]
        chat_name = chat_info["chat_name"]
        self.last_status["checking_chat"] = chat_name
        self.last_status["status"] = f"正在检查「{chat_name}」更新..."

        new_videos = []
        max_msg_id = chat_info.get("last_message_id", 0)

        # 尝试优先走 MCP Gateway（若启用）
        if chat_info.get("use_mcp") and MCP_GATEWAY_URL:
            try:
                mcp_videos, m_max = self._fetch_via_mcp(chat_id)
                if mcp_videos is not None:
                    new_videos = mcp_videos
                    if m_max > max_msg_id:
                        max_msg_id = m_max
            except Exception:
                new_videos = []

        # 若 MCP 没拿到或未启用，走轻量级 tdl export (最近25条)
        if not new_videos:
            tdl_videos, t_max = self._fetch_via_tdl_last(chat_id, chat_name)
            new_videos = tdl_videos
            if t_max > max_msg_id:
                max_msg_id = t_max

        # 查询数据库中已下载/已迁移过的 message_id 进行差量过滤
        downloaded_ids = get_downloaded_message_ids(chat_id)
        actual_new_videos = [v for v in new_videos if v["id"] not in downloaded_ids]

        new_count = len(actual_new_videos)
        update_track_progress(chat_id, max_msg_id, new_count)

        self.last_status["last_run_time"] = time.time()
        self.last_status["status"] = "监控待机中"
        self.last_status["checking_chat"] = None

        if actual_new_videos and chat_info.get("auto_download") and self.queue_manager:
            # 自动生成增量下载任务推入下载队列
            self._queue_incremental_download(chat_id, chat_name, actual_new_videos)

        return {
            "success": True,
            "chat_name": chat_name,
            "found_new_videos": new_count,
            "auto_download": bool(chat_info.get("auto_download")),
            "message": f"「{chat_name}」检查完毕：发现 {new_count} 个新视频"
        }

    def _fetch_via_mcp(self, chat_id: int):
        """通过 192.168.8.11:8791 的 MCP Gateway 检索最新消息"""
        url = f"{MCP_GATEWAY_URL}/search?chat={chat_id}&limit=25"
        req = urllib.request.Request(url, headers={"User-Agent": "tdl-tracker/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        
        # 提取含视频的消息
        videos = []
        max_id = 0
        for item in data:
            mid = item.get("message_id", 0)
            if mid > max_id:
                max_id = mid
            # 记录基础结构
            videos.append({"id": mid, "type": "message", "file": f"{mid}.mp4"})
        return videos, max_id

    def _fetch_via_tdl_last(self, chat_id: int, chat_name: str):
        """调用 tdl 快速导出最近 25 条消息"""
        temp_out = META_DIR / f"track_temp_{chat_id}.json"
        cmd = [
            str(TDL_BIN), "chat", "export",
            "-c", str(chat_id),
            "-T", "last",
            "-i", "25",
            "-o", str(temp_out),
            "--proxy", DEFAULT_PROXY
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
            if res.returncode == 0 and temp_out.exists():
                with open(temp_out, "r", encoding="utf-8") as f:
                    data = json.load(f)
                try:
                    temp_out.unlink()
                except Exception:
                    pass

                msgs = data.get("messages", [])
                videos = []
                max_id = 0
                for m in msgs:
                    mid = m.get("id", 0)
                    if mid > max_id:
                        max_id = mid
                    # 检查是否包含媒体视频
                    raw = m.get("raw", {})
                    media = raw.get("Media", {})
                    doc = media.get("Document", {})
                    mime = doc.get("MimeType", "")
                    is_video = media.get("Video", False) or "video" in mime.lower() or str(m.get("file", "")).lower().endswith((".mp4", ".mkv", ".mov", ".m4v"))
                    if is_video:
                        videos.append(m)
                return videos, max_id
        except Exception:
            pass
        return [], 0

    def _queue_incremental_download(self, chat_id: int, chat_name: str, video_messages: List[Dict[str, Any]]):
        """为追更新视频自动创建下载清单并入队"""
        inc_json = META_DIR / f"inc_track_{chat_id}_{int(time.time())}.json"
        payload = {
            "id": chat_id,
            "messages": video_messages
        }
        with open(inc_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        task_params = {
            "chat_id": chat_id,
            "chat_name": f"{chat_name} [追更]",
            "task_type": "incremental",
            "custom_json": str(inc_json),
            "threads": 8,
            "limit": 4,
            "proxy": DEFAULT_PROXY
        }
        self.queue_manager.add_task(task_params, priority="queue")

tracker_engine = AutoTracker()
