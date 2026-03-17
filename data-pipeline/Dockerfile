FROM python:3.12.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .

# 1. Install CPU-only PyTorch (~200 MB vs ~2 GB for CUDA version)
RUN pip install --no-cache-dir \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# 2. Install everything else; pip won't downgrade/upgrade torch since it's
#    already satisfied.  Works because requirements.txt has no torch pin.
RUN pip install --no-cache-dir -r requirements.txt

# Copy pipeline code and data files
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENTRYPOINT ["python", "data_ingestion_pipeline.py"]
CMD ["--reset"]
