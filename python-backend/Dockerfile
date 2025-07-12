# Dockerfile for Python Backend with ModelScope ASR Support
# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for ModelScope and audio processing
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    ffmpeg \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install wheel for better package building
RUN pip install --upgrade pip wheel setuptools

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Use --no-cache-dir to reduce image size and --timeout for ModelScope dependencies
RUN pip install -r requirements.txt


# Set ModelScope cache environment variable
ENV MODELSCOPE_CACHE=/app/model_cache

# Copy the model download script and pre-cache the ModelScope model
COPY download_model.py .
RUN python download_model.py

# Copy the application code into the container
COPY *.py ./

# Expose the port the app runs on
EXPOSE 8000

# Define the command to run the app
CMD ["python", "main.py"]
