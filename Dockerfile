FROM python:3.12-slim

# 비인터랙티브 + 한국시간
ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Seoul

WORKDIR /app

# 의존성 먼저 설치 (레이어 캐시)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 코드
COPY app/ ./app/
COPY schema.sql ./schema.sql

# /data 는 volume (SQLite + 캐시)
RUN mkdir -p /data/cache

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]