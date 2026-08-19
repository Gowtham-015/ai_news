FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered output for real-time logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Kolkata

WORKDIR /app

# Install system dependencies & timezone data
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Ensure data and logs directories exist
RUN mkdir -p data logs

# Default startup command for 24/7 continuous autonomous daemon
CMD ["python", "main.py", "--daemon"]
