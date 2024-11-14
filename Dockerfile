# Use the official Python image as the base image
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Install system dependencies (FFmpeg, curl for yt-dlp, and other dependencies)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Expose any necessary ports (if applicable)
EXPOSE 8080

# Command to run your application
CMD ["python", "bot.py"]
