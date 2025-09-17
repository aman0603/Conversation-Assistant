FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

COPY pyproject.toml .
COPY src/ ./src/

RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install -e .

COPY config/ ./config/
COPY scripts/ ./scripts/

ENV PYTHONPATH=/app

EXPOSE 8000 8001

CMD [".venv/bin/python", "-m", "src.api.main"]