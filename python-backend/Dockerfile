# Dockerfile for Python Backend with ASR Support
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for audio processing
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the model download script and pre-cache the FunASR model
COPY download_model.py .
RUN python download_model.py

# Copy the application code into the container
COPY *.py ./

# Expose the port the app runs on
EXPOSE 8000

# Define the command to run the app
CMD ["python", "main.py"]
