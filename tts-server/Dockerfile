FROM python:3.11-slim

# Install system dependencies for piper
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip first for better download handling
RUN pip install --upgrade pip

# Install heavy dependency first (onnxruntime ~18MB) with generous timeout
RUN pip install --no-cache-dir --timeout=600 --retries=10 onnxruntime==1.21.1

# Install remaining Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=300 --retries=5 -r requirements.txt

# Create models directory
RUN mkdir -p /app/models

# Copy server code
COPY server.py .

# Expose port
EXPOSE 5050

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5050/health')" || exit 1

# Run the server
CMD ["python", "server.py"]
