FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1 \
    SYNAPSE_SHIELD_DB=/data/synapse_shield.db

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && mkdir -p /data

EXPOSE 8000

CMD ["synapse-shield", "run", "--host", "0.0.0.0", "--port", "8000"]
