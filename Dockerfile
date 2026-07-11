FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 先複製 requirements 以利用 Docker layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式
COPY . .

# Cloud Run 預設 port 是 8080
ENV PORT=8080

# 不使用 .env 檔（環境變數由 Cloud Run 注入）
ENV PYTHONUNBUFFERED=1

# 啟動指令
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
