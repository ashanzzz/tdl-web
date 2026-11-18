@echo off
chcp 65001 >nul
title 启动 Telegram 视频下载控制中心
cd /d "%~dp0"
start "" "TelegramDownloader.exe"
exit
