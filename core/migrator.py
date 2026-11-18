import os
import re
import shutil
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from .config import BASE_DOWNLOAD_DIR, META_DIR
from .db import batch_record_downloads, batch_mark_migrated, record_download

# 正则匹配形如: 8147635821_13435_6305092439560426155.mp4
FILENAME_REGEX = re.compile(r"^(\d+)_(\d+)_(.+)$")

def scan_and_index_existing_files() -> Dict[str, Any]:
    """
    扫描下载目录中已存在的全部视频文件，将其提取并录入防重数据库。
    """
    indexed_count = 0
    total_bytes = 0
    items_to_record = []
    
    # 建立 chat_id 到 chat_name 的缓存映射（从 _tdl_meta/*.json 解析）
    chat_name_map = {}
    if META_DIR.exists():
        for jf in META_DIR.glob("*_videos.json"):
            # 命名形式: <safe_name>_<chat_id>_videos.json
            m = re.search(r"^(.*)_(\d+)_videos\.json$", jf.name)
            if m:
                safe_name, cid = m.group(1), int(m.group(2))
                chat_name_map[cid] = safe_name

    if not BASE_DOWNLOAD_DIR.exists():
        return {"indexed_count": 0, "total_bytes": 0, "message": "下载目录不存在"}

    # 扫描主目录及直接子目录下的媒体文件
    media_extensions = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".ts", ".m4v"}
    
    for root, dirs, files in os.walk(BASE_DOWNLOAD_DIR):
        root_path = Path(root)
        # 排除 _tdl_meta 目录
        if "_tdl_meta" in root_path.parts:
            continue
            
        folder_chat_name = root_path.name if root_path != BASE_DOWNLOAD_DIR else "未分类"

        for file in files:
            p = root_path / file
            if p.suffix.lower() in media_extensions:
                m = FILENAME_REGEX.match(file)
                if m:
                    chat_id = int(m.group(1))
                    message_id = int(m.group(2))
                    raw_filename = m.group(3)
                    chat_name = chat_name_map.get(chat_id, folder_chat_name)
                    try:
                        file_size = p.stat().st_size
                    except Exception:
                        file_size = 0
                    
                    items_to_record.append({
                        "chat_id": chat_id,
                        "chat_name": chat_name,
                        "message_id": message_id,
                        "file_name": file,
                        "file_size": file_size,
                        "file_path": str(p.resolve()),
                        "status": "completed"
                    })
                    total_bytes += file_size
                    indexed_count += 1

                # 每 500 个批量提交一次
                if len(items_to_record) >= 500:
                    batch_record_downloads(items_to_record)
                    items_to_record.clear()

    if items_to_record:
        batch_record_downloads(items_to_record)
        items_to_record.clear()

    return {
        "success": True,
        "indexed_count": indexed_count,
        "total_bytes": total_bytes,
        "total_gb": round(total_bytes / (1024**3), 2),
        "message": f"成功扫描并登记 {indexed_count} 个现有历史视频 ({round(total_bytes / (1024**3), 2)} GB) 到防重数据库！"
    }

def get_migration_summary() -> List[Dict[str, Any]]:
    """
    获取各个下载目录或会话的文件总数、大小汇总，供前端展示选择迁移。
    """
    summary = []
    if not BASE_DOWNLOAD_DIR.exists():
        return summary

    media_extensions = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".ts", ".m4v"}

    # 扫描各个子目录
    for item in BASE_DOWNLOAD_DIR.iterdir():
        if item.is_dir() and item.name != "_tdl_meta":
            file_count = 0
            total_size = 0
            for f in item.glob("*"):
                if f.is_file() and f.suffix.lower() in media_extensions:
                    file_count += 1
                    try:
                        total_size += f.stat().st_size
                    except Exception:
                        pass
            if file_count > 0:
                summary.append({
                    "folder_name": item.name,
                    "folder_path": str(item.resolve()),
                    "file_count": file_count,
                    "total_size_bytes": total_size,
                    "total_size_gb": round(total_size / (1024**3), 2)
                })

    # 扫描根目录直属散落文件
    root_files = 0
    root_size = 0
    for f in BASE_DOWNLOAD_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in media_extensions:
            root_files += 1
            try:
                root_size += f.stat().st_size
            except Exception:
                pass
    if root_files > 0:
        summary.append({
            "folder_name": "[根目录直存文件]",
            "folder_path": str(BASE_DOWNLOAD_DIR.resolve()),
            "file_count": root_files,
            "total_size_bytes": root_size,
            "total_size_gb": round(root_size / (1024**3), 2)
        })

    return summary

def migrate_files(source_folder: str, target_dir: str, mode: str = "move",
                  preserve_subfolder: bool = True) -> Dict[str, Any]:
    """
    执行文件迁移：将 source_folder 里的视频文件迁移到 target_dir。
    mode: 'move' (移动，剪切释放原空间) 或 'copy' (复制)
    """
    src_path = Path(source_folder)
    dst_base = Path(target_dir)

    if not src_path.exists():
        return {"success": False, "message": f"源文件夹不存在: {source_folder}"}

    try:
        dst_base.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return {"success": False, "message": f"无法创建目标文件夹: {e}"}

    media_extensions = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".ts", ".m4v"}
    success_count = 0
    failed_count = 0
    total_bytes = 0
    db_updates = []

    # 确定目标子目录
    if preserve_subfolder and src_path != BASE_DOWNLOAD_DIR:
        final_dst = dst_base / src_path.name
        final_dst.mkdir(parents=True, exist_ok=True)
    else:
        final_dst = dst_base

    # 搜集待迁移文件
    files_to_process = [f for f in src_path.iterdir() if f.is_file() and f.suffix.lower() in media_extensions]

    for f in files_to_process:
        target_file = final_dst / f.name
        f_size = 0
        try:
            f_size = f.stat().st_size
        except Exception:
            pass

        try:
            if mode == "move":
                shutil.move(str(f), str(target_file))
            else:
                shutil.copy2(str(f), str(target_file))

            success_count += 1
            total_bytes += f_size

            # 解析文件名并记入防重已迁移数据库
            m = FILENAME_REGEX.match(f.name)
            if m:
                cid = int(m.group(1))
                mid = int(m.group(2))
                db_updates.append({
                    "chat_id": cid,
                    "message_id": mid,
                    "new_path": str(target_file.resolve())
                })
        except Exception as e:
            failed_count += 1

    if db_updates:
        batch_mark_migrated(db_updates)

    return {
        "success": True,
        "mode": mode,
        "source": str(src_path),
        "target": str(final_dst),
        "moved_count": success_count,
        "failed_count": failed_count,
        "total_gb": round(total_bytes / (1024**3), 2),
        "message": f"成功{ '移动' if mode == 'move' else '复制' } {success_count} 个文件 ({round(total_bytes / (1024**3), 2)} GB) 至 {final_dst}，已同步更新防重数据库！"
    }
