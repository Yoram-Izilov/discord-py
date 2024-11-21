FROM python:3.11-slim

WORKDIR /app

# Copy the application code
COPY . .

# Create the data folder
RUN mkdir -p /app/data
 
# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg libsndfile1 curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

    
# Command to run your application
CMD ["python", "bot.py"]
