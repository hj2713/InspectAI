# Multi-Agent Code Review System - Docker Image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install ONLY production dependencies (no torch!)
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

# Pre-download ChromaDB embedding model (if ChromaDB installed) to avoid repeated downloads
# This caches the ~80MB all-MiniLM-L6-v2 model in the Docker image
RUN python -c "try:\n    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2\n    ONNXMiniLM_L6_V2()\n    print('ChromaDB model cached')\nexcept ImportError:\n    print('ChromaDB not installed, skipping model cache')"

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p logs

# Expose port (Cloud Run uses 8080 by default)
EXPOSE 8080

# Run the application
CMD ["python", "-m", "uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8080"]
