FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY bot.py .

# Create non-root user
RUN useradd -m -u 1000 titan && chown -R titan:titan /app
USER titan

# Run the Discord bot
CMD ["python3", "bot.py"]
