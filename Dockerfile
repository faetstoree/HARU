FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Cloud Run default port is 8080
ENV PORT=8080

# Do not use .env file (environment variables are injected by Cloud Run)
ENV PYTHONUNBUFFERED=1

# Start command
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
