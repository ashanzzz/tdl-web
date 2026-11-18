---
name: tdl-telegram-downloader
description: Manage Telegram media downloading using tdl CLI on Windows. Automates checking environment, login, listing chats/channels/bots, exporting media JSON, batch downloading to Synology Drive (D:\SynologyDrive\download\telegram), resuming downloads, and error handling.
metadata:
  short-description: Windows tdl Telegram Downloader Automation Skill
---

# tdl Telegram Downloader 自动化执行手册与规范

用于在 Windows 环境下自动化调度与执行 `tdl` (Telegram Downloader) CLI，实现对 Telegram 频道、群组、私聊、会员机器人已有媒体文件的高速导出与下载。

---

## 核心固定环境配置

- **tdl 可执行文件绝对路径**：`D:\tdl_Windows_64bit\tdl.exe`
- **下载存储根目录 (Synology Drive 同步目录)**：`D:\SynologyDrive\download\telegram`
- **元数据与日志目录**：`D:\SynologyDrive\download\telegram\_tdl_meta`
  *(存储 `chats.json`、频道导出 `.json`、任务状态与日志，严禁在此目录保存实际下载文件)*
- **默认本地代理地址**：`http://192.168.8.11:7890`

---

## 自动化操作流程规范

### 1. 环境与可用性检查
执行前首先确认 `tdl.exe` 存在及版本信息：
```powershell
& "D:\tdl_Windows_64bit\tdl.exe" version
```
必须保证元数据目录存在：
```powershell
if (!(Test-Path "D:\SynologyDrive\download\telegram\_tdl_meta")) {
    New-Item -ItemType Directory -Force -Path "D:\SynologyDrive\download\telegram\_tdl_meta"
}
```

### 2. 登录状态检查与会话维护
检测是否具备有效 session（通常位于 `C:\Users\ashan\.tdl\data`）：
```powershell
& "D:\tdl_Windows_64bit\tdl.exe" chat ls --proxy http://192.168.8.11:7890
```
- 若未登录：
  - 优先支持从已有的官方桌面客户端导入：`& "D:\tdl_Windows_64bit\tdl.exe" login -d "C:\Users\ashan\AppData\Roaming\Telegram Desktop" --proxy http://192.168.8.11:7890`
  - 或通过二维码交互登录：`& "D:\tdl_Windows_64bit\tdl.exe" login -T qr --proxy http://192.168.8.11:7890`
- **安全铁律**：严禁清除已有 session，严禁向外部传输或记录用户 session/密码/验证码。

### 3. 获取与解析会话列表
导出完整聊天列表至 JSON：
```powershell
& "D:\tdl_Windows_64bit\tdl.exe" chat ls -o json --proxy http://192.168.8.11:7890 > "D:\SynologyDrive\download\telegram\_tdl_meta\chats.json"
```
根据用户提供的群名、频道名、机器人名、或关键词对 `chats.json` 进行精确或模糊筛选，输出候选列表让用户或自动化精准命中目标 `Chat ID` 与 `Type`。

### 4. 建立独立下载子目录
下载目录必须规范为独立子目录，杜绝混合存储：
- 规则：`D:\SynologyDrive\download\telegram\<清洗后的聊天名称>`
- 字符清洗：过滤 Windows 非法字符 `\ / : * ? " < > |`

### 5. 导出媒体信息至 JSON
- 完整导出：
  ```powershell
  & "D:\tdl_Windows_64bit\tdl.exe" chat export -c <CHAT_ID> -o "D:\SynologyDrive\download\telegram\_tdl_meta\<ChatName>_<CHAT_ID>.json" --proxy http://192.168.8.11:7890
  ```
- 快速测试/最近消息导出（如最近 20 条）：
  ```powershell
  & "D:\tdl_Windows_64bit\tdl.exe" chat export -c <CHAT_ID> -T last -i 20 -o "D:\SynologyDrive\download\telegram\_tdl_meta\<ChatName>_<CHAT_ID>_test.json" --proxy http://192.168.8.11:7890
  ```

### 6. 执行批量下载
根据导出的 JSON 文件执行下载：
```powershell
& "D:\tdl_Windows_64bit\tdl.exe" download -f "D:\SynologyDrive\download\telegram\_tdl_meta\<ChatName>_<CHAT_ID>.json" -d "D:\SynologyDrive\download\telegram\<ChatName>" --skip-same -t 8 -l 4 --proxy http://192.168.8.11:7890
```
- 仅下载特定类型（例如只要视频）：加入 `-i mp4,mkv,avi,mov`
- 断点续传：若异常中断，使用 `--continue`
- 避免重复下载：始终附带 `--skip-same`

### 7. 下载结果复核与汇报
下载完成后：
1. 统计目标子目录内的文件总数与总体积。
2. 对比 JSON 导出的媒体数与实际下载成功数。
3. 检查是否有下载失败项并输出明确诊断。

---

## 安全规则清单

1. 严禁自动执行 `Remove-Item -Recurse`、`del /s`、`rd /s` 处理下载目录。
2. 严禁删除或覆盖已下载文件。
3. 严禁登出、删除 Telegram session、退出群组或频道。
4. 严禁与任何 Telegram 机器人发生敏感交互（自动支付、充值、购买等）。