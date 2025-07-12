# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libsndfile1 \
    ffmpeg \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip wheel setuptools

# ========================
# BuildKit pip 缓存挂载
# ========================
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# ==========================
# 拷贝模型缓存 + 利用 BuildKit 复用
# ==========================
COPY download_model.py .

# 使用 BuildKit 挂载 host 缓存模型
RUN --mount=type=cache,target=/app/model_cache \
    MODELSCOPE_CACHE=/app/model_cache \
    python download_model.py

COPY *.py ./
ENV MODELSCOPE_CACHE=/app/model_cache

EXPOSE 8000
CMD ["python", "main.py"]   