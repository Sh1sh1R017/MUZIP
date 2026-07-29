# Multi-stage Dockerfile for MUZIP (YouTube Audio & Playlist ZIP Downloader)

# Stage 1: Build React Frontend
FROM node:18-slim AS frontend-builder

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build


# Stage 2: Final Production Runtime (Python + FFmpeg)
FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Install FFmpeg and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root system security user
RUN useradd -m -u 10001 appuser && \
    chown -R appuser:appuser /app

# Copy application files and built frontend dist assets
COPY --chown=appuser:appuser . /app
COPY --from=frontend-builder --chown=appuser:appuser /app/dist /app/dist

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
