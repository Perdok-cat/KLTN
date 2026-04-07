# ── Build từ repo root: docker build -f Backend/Dockerfile . ──────────────────
FROM python:3.11-slim

WORKDIR /app

# Cài Python dependencies (không cần gcc vì không còn underthesea)
COPY Backend/requirements.txt ./Backend/requirements.txt
RUN pip install --no-cache-dir -r Backend/requirements.txt

# Copy source code Backend
COPY Backend/ ./Backend/

WORKDIR /app/Backend

ENV PORT=8080
ENV FLASK_DEBUG=false
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120 app:app"]
