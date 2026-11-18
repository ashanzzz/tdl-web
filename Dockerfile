# ==========================================
# tdl Telegram Downloader WebUI & Watchdog
# Multi-arch Dockerfile (linux/amd64, linux/arm64)
# ==========================================

FROM python:3.12-slim-bookworm

ARG TARGETARCH

# 安装基础系统依赖及多媒体工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    tar \
    ffmpeg \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# 下载对应架构的官方 tdl 二进制
ARG TDL_VERSION="v0.17.2"
RUN set -eux; \
    case "${TARGETARCH}" in \
        "amd64") TDL_ARCH="64bit" ;; \
        "arm64") TDL_ARCH="arm64" ;; \
        *) echo "Unsupported target architecture: ${TARGETARCH}"; exit 1 ;; \
    esac; \
    DOWNLOAD_URL="https://github.com/iyear/tdl/releases/download/${TDL_VERSION}/tdl_Linux_${TDL_ARCH}.tar.gz"; \
    echo "Downloading tdl from: ${DOWNLOAD_URL}"; \
    curl -fsSL "${DOWNLOAD_URL}" -o /tmp/tdl.tar.gz; \
    tar -xzf /tmp/tdl.tar.gz -C /usr/local/bin tdl; \
    chmod +x /usr/local/bin/tdl; \
    rm -f /tmp/tdl.tar.gz; \
    tdl version

WORKDIR /app

# 预安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码与纯 Web 前端
COPY core/ ./core/
COPY web/ ./web/
COPY server.py .

# 创建数据存储与配置卷
ENV DOWNLOAD_DIR=/data/downloads \
    META_DIR=/data/config \
    TDL_BIN=/usr/local/bin/tdl \
    PORT=8765 \
    PYTHONUNBUFFERED=1

RUN mkdir -p /data/downloads /data/config /root/.tdl

VOLUME ["/data/downloads", "/data/config", "/root/.tdl"]

EXPOSE 8765

CMD ["python", "server.py"]
