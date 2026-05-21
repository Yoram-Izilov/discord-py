FROM python:3.12.7-slim

WORKDIR /app

# Install system dependencies and create non-root user in one layer
RUN apt-get update && apt-get install -y \
    ffmpeg libsndfile1 curl chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m botuser

# Install Python dependencies (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure data dir exists and is owned by the non-root user
RUN mkdir -p /app/data && chown -R botuser:botuser /app

USER botuser

CMD ["python", "bot.py"]
