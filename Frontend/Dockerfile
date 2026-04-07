# ── Build từ repo root: docker build -f Frontend/Dockerfile . ─────────────────
FROM python:3.11-slim

WORKDIR /app

# Cài Python dependencies
COPY Frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ Frontend (app.py + pages/)
COPY Frontend/ .

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# API_URL được truyền vào lúc deploy (Cloud Run env var)
# ENV API_URL=http://backend-service-url

EXPOSE 8080

# Streamlit cần chạy headless, disable CORS cho Cloud Run
CMD ["sh", "-c", "streamlit run app.py \
    --server.port=${PORT:-8080} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false"]
