FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model during build (~90MB)
# Prevents 30s hang on first request while model downloads at runtime
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 titan && chown -R titan:titan /app
USER titan

# Expose port for health checks
EXPOSE 8080

# Run the MCP server
CMD ["python", "server.py"]
