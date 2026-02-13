FROM ubuntu:22.04

WORKDIR /workspace/metta

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /bin/

COPY . /workspace/metta

RUN uv python install
RUN uv run --no-sync python -m metta.setup.components.system_packages.bootstrap --non-interactive
RUN uv sync --frozen --package metta-app-backend --no-dev

WORKDIR /workspace/metta/app_backend
EXPOSE 8000
ENV HOST=0.0.0.0
ENV PORT=8000

CMD ["uv", "run", "--no-sync", "python", "src/metta/app_backend/server.py"]
