FROM python:3.11-slim

# Install system dependencies as root FIRST
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python packages as root (system-wide, accessible to all users)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create HF-required non-root user (UID 1000) and give ownership
RUN useradd -m -u 1000 user && chown -R user:user /app
USER user

EXPOSE 7860

# Use uvicorn directly - more reliable than python app.py
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
