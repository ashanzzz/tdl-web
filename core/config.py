import os
import sys
import shutil
from pathlib import Path

# 系统运行模式判断
IS_WINDOWS = sys.platform.startswith("win")

# 基础目录与可执行文件定位
def get_default_tdl_bin() -> Path:
    env_bin = os.environ.get("TDL_BIN")
    if env_bin:
        return Path(env_bin)
    
    # 优先检查工作区同目录的 tdl / tdl.exe
    here = Path(__file__).resolve().parent.parent
    if IS_WINDOWS:
        candidate = here / "tdl.exe"
        if candidate.exists():
            return candidate
        fixed = Path(r"D:\tdl_Windows_64bit\tdl.exe")
        if fixed.exists():
            return fixed
    else:
        candidate = here / "tdl"
        if candidate.exists():
            return candidate
        which_path = shutil.which("tdl")
        if which_path:
            return Path(which_path)
    return Path("tdl.exe" if IS_WINDOWS else "tdl")

def get_default_download_dir() -> Path:
    env_dir = os.environ.get("DOWNLOAD_DIR")
    if env_dir:
        return Path(env_dir)
    if IS_WINDOWS:
        fixed = Path(r"D:\SynologyDrive\download\telegram")
        if fixed.exists() or Path("D:").exists():
            return fixed
    return Path(__file__).resolve().parent.parent / "downloads"

TDL_BIN = get_default_tdl_bin()
BASE_DOWNLOAD_DIR = get_default_download_dir()

# 元数据目录
META_DIR = Path(os.environ.get("META_DIR", str(BASE_DOWNLOAD_DIR / "_tdl_meta")))
META_DIR.mkdir(parents=True, exist_ok=True)

# 核心路径
DATABASE_PATH = META_DIR / "history.db"
CHATS_JSON = META_DIR / "chats.json"
BOT_COUNTS_JSON = META_DIR / "bot_video_counts.json"
STATS_FILE = META_DIR / "quota_stats.json"
QUEUE_FILE = META_DIR / "download_queue.json"
SESSION_CACHE_DIR = META_DIR / "session_cache"
THUMB_CACHE_DIR = META_DIR / "thumb_cache"

SESSION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 网络与网关默认配置
DEFAULT_PROXY = os.environ.get("PROXY_URL", "http://192.168.8.11:7890")
MCP_GATEWAY_URL = os.environ.get("MCP_GATEWAY_URL", "http://192.168.8.11:8791")
SERVER_PORT = int(os.environ.get("PORT", 8765))

# 默认跟踪轮询间隔（秒），默认 30 分钟 (1800 秒)
DEFAULT_TRACKER_INTERVAL = int(os.environ.get("TRACKER_INTERVAL", 1800))

# 身份安全认证配置
AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "ashan")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "Woo@@@204317")
AUTH_SESSION_EXPIRE_HOURS = int(os.environ.get("AUTH_SESSION_EXPIRE_HOURS", 24 * 7))  # 默认 7 天有效

