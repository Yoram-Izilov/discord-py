# Use the Python slim image
FROM python:3.11-slim

WORKDIR /app

# Copy the application code
COPY . .

# Create the data folder
RUN mkdir -p /app/data

# Install system dependencies (including Chrome)
RUN apt-get update && apt-get install -y \
    ffmpeg libsndfile1 curl chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set environment variable for Chrome
ENV PATH="/usr/bin:$PATH"

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Command to run your application
CMD ["python", "bot.py"]
