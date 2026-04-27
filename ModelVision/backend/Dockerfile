# docker build -f ModelVision/backend/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

COPY ModelVision/backend/requirements.txt ./ModelVision/backend/requirements.txt
RUN pip install --no-cache-dir -r ModelVision/backend/requirements.txt

COPY ModelVision/backend/ ./ModelVision/backend/

WORKDIR /app/ModelVision/backend

ENV PORT=8080
ENV FLASK_DEBUG=false
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120 app:app"]
