FROM python:3.12-slim

WORKDIR /app

# Install dependencies required for building some python packages if necessary
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY src/ /app/src/
COPY pyproject.toml /app/
COPY README.md /app/

# Install the package itself
RUN pip install -e .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV SYNAPSE_DB_PATH=/app/data/synapse_shield.db
ENV SYNAPSE_DATASET_PATH=/app/data/synapse_dataset.db
ENV PYTHONPATH=/app/src

# Create data directory for SQLite databases
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "synapse_shield.main:app", "--host", "0.0.0.0", "--port", "8000"]
