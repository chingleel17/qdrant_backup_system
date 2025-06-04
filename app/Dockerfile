FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統相依套件
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 複製需求檔案並安裝 Python 相依套件
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式檔案
COPY app/main.py .

# 建立備份目錄
RUN mkdir -p /tmp/qdrant_snapshots

# 設定環境變數
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 暴露連接埠
EXPOSE 8080

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# 使用 gunicorn 執行應用程式
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "600", "--keep-alive", "2", "--max-requests", "1000", "--max-requests-jitter", "100", "main:app"]
