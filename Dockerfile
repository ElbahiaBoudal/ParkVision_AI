FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./

RUN uv pip install --system --no-cache-dir \
    torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

RUN uv sync --frozen --no-dev \
    --no-install-package torch \
    --no-install-package torchvision

# OpenTelemetry (pas dans pyproject.toml mais utilisé dans main.py)
RUN uv pip install --system --no-cache-dir \
    opentelemetry-sdk \
    opentelemetry-instrumentation-fastapi \
    opentelemetry-instrumentation-sqlalchemy \
    opentelemetry-exporter-otlp-proto-grpc

COPY app/ ./app/
COPY mlflow_utils/ ./mlflow_utils/
COPY scripts/ ./scripts/
COPY main.py .
COPY data/ ./data/
COPY model_data/ ./model_data/

EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]