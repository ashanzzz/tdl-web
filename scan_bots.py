import sys
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
import subprocess, json, re, os
from pathlib import Path

TDL = r'D:\tdl_Windows_64bit\tdl.exe'
META_DIR = Path(r'D:\SynologyDrive\download\telegram\_tdl_meta')
CHATS_FILE = META_DIR / 'chats.json'
OUT_FILE = META_DIR / 'bot_video_counts.json'
PROXY = 'http://192.168.8.11:7890'

with open(CHATS_FILE, 'r', encoding='utf-8') as f:
    chats = json.load(f)

# Priority bots
bots = []
for c in chats:
    u = str(c.get('username') or '').lower()
    v = str(c.get('visible_name') or '').lower()
    is_bot = u.endswith('bot') or 'bot' in u or '机器人' in v or 'bot' in v
    if not is_bot:
        continue
    # Filter for download/file/video/extract/storage bots
    keywords = ['提取', '文件', '下载', '视频', '存储', '储存', '仓库', '网盘', '助手', '藏片', '资源', 'download', 'file', 'video', 'extract', 'disk']
    if any(k in v or k in u for k in keywords):
        bots.append(c)

print(f'Starting scan for {len(bots)} priority download/media bots...')

results = {}
if OUT_FILE.exists():
    try:
        with open(OUT_FILE, 'r', encoding='utf-8') as f:
            results = json.load(f)
    except:
        pass

for b in bots:
    cid = b['id']
    cid_str = str(cid)
    name = b.get('visible_name', 'Bot')
    
    tmp_path = META_DIR / f'scan_{cid}.json'
    cmd = [TDL, 'chat', 'export', '-c', str(cid), '-o', str(tmp_path), '--proxy', PROXY]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        if tmp_path.exists():
            with open(tmp_path, 'r', encoding='utf-8') as jf:
                data = json.load(jf)
            msgs = data.get('messages', [])
            vmsgs = [m for m in msgs if re.search(r'\.(mp4|mov|mkv|avi|webm)$', m.get('file', ''), re.I)]
            results[cid_str] = {
                'chat_id': cid,
                'visible_name': name,
                'username': b.get('username'),
                'total_media': len(msgs),
                'video_count': len(vmsgs)
            }
            if len(vmsgs) > 0:
                print(f'[FOUND] {name} ({cid}): {len(vmsgs)} videos / {len(msgs)} total')
            else:
                print(f'[0] {name} ({cid}): 0 videos')
            try:
                os.remove(tmp_path)
            except:
                pass
    except Exception as e:
        print(f'[ERR] {name}: {e}')

with open(OUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print('Scan finished and saved to bot_video_counts.json!')
