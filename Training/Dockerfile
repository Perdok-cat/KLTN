FROM python:3.11-slim

WORKDIR /app

# Cài thư viện trước (tận dụng Docker layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 120 -r requirements.txt

# Copy training script
COPY train_vertex.py .

ENTRYPOINT ["python", "train_vertex.py"]
