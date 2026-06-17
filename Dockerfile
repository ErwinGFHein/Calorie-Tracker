FROM python:3.11-slim

WORKDIR /workspace

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ /workspace/app/

# Expose data directory volume for persistent SQLite database
VOLUME /data

# Default database environment variable
ENV DATABASE_PATH=/data/tracker.db

EXPOSE 8000

# Run uvicorn server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
