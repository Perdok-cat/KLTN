# docker build -f ModelVision/frontend/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

COPY ModelVision/frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ModelVision/frontend/ .

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

CMD ["sh", "-c", "streamlit run app.py \
    --server.port=${PORT:-8080} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false"]
