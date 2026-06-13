FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy orchestrator code
COPY . .

# Expose API port
EXPOSE 8000

# Run FastAPI server
CMD ["python3", "-m", "uvicorn", "master:app", "--host", "0.0.0.0", "--port", "8000"]
