# Metta Development Container
# Provides a consistent Linux x86 environment for development

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV UV_LINK_MODE=copy

WORKDIR /workspace

# =============================================================================
# System Dependencies
# =============================================================================

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    git \
    # libgl1 provides libGL.so.1, required by metta nimtest. The Nim mettascope tests
    # (validation, pathfinding, replay loading) don't render anything, but they import
    # modules that transitively depend on OpenGL via boxy/windy/silky. Without this
    # library, tests fail at runtime with "could not load: libGL.so.1".
    libgl1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
# Programming Languages
# =============================================================================

# Python (via uv)
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /bin/
COPY .python-version pyproject.toml uv.lock ./
RUN uv python install

# Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:$PATH"

# Go
RUN curl -fsSL https://go.dev/dl/go1.23.5.linux-amd64.tar.gz | tar -xz -C /usr/local
ENV PATH="/usr/local/go/bin:$PATH"

# Node.js and pnpm
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/* && \
    npm install -g pnpm

# =============================================================================
# Build Tools (Bazel, Nim, Nimby)
# =============================================================================

COPY .bazelversion .bazeliskversion /
COPY metta/setup/components/system_packages/bootstrap.py /tmp/bootstrap.py
RUN cd /tmp && uv run --no-sync python bootstrap.py --non-interactive

# =============================================================================
# AI Coding Assistants
# =============================================================================

RUN npm install -g @anthropic-ai/claude-code @openai/codex

# =============================================================================
# Developer Tools
# =============================================================================

# clang-format for C++ linting
RUN apt-get update && apt-get install -y --no-install-recommends \
    clang-format && \
    rm -rf /var/lib/apt/lists/*

# =============================================================================
# DOCKER CLI AND COMPOSE PLUGIN
# =============================================================================
# Provides `docker` and `docker compose` commands inside the devcontainer.
#
# HOW IT WORKS:
# - We install only the Docker CLI (not the daemon)
# - The devcontainer mounts /var/run/docker.sock from the host
# - Docker commands run against the HOST's Docker daemon
#
# WHY THIS MATTERS FOR OBSERVATORY:
# When you run `metta observatory postgres up` in the devcontainer, it uses
# docker-compose to start postgres. Because of the socket mount, this postgres
# container runs on the HOST's Docker (not nested inside the devcontainer).
# This means postgres is accessible at host.docker.internal:5432 from the
# devcontainer, which is handled by cli.py's get_db_uri() function.
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.5.1.tgz \
    | tar -xz -C /usr/local/bin --strip-components=1 docker/docker && \
    mkdir -p /usr/local/lib/docker/cli-plugins && \
    curl -fsSL "https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-x86_64" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose && \
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# =============================================================================
# KUBECTL
# =============================================================================
# Kubernetes CLI for managing the K8s cluster (OrbStack or k3d).
# Used by metta observatory for creating namespaces, viewing pods, etc.
RUN curl -fsSL "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    -o /usr/local/bin/kubectl && chmod +x /usr/local/bin/kubectl

# =============================================================================
# K3D
# =============================================================================
# k3d is k3s (lightweight Kubernetes) running in Docker.
# Used by metta observatory when:
# - Running in a devcontainer on Linux (no OrbStack available)
# - User explicitly chooses k3d via METTA_K8S_RUNTIME=k3d
#
# On Mac devcontainers, we prefer connecting to host's OrbStack instead
# because it's already set up and shares Docker images automatically.
RUN curl -fsSL https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash

# =============================================================================
# PROCESS-COMPOSE
# =============================================================================
# A tool for running multiple processes (similar to docker-compose but for
# local processes). Used by `metta observatory up` to orchestrate:
# - postgres, server, frontend, watcher, tournament, job logs
#
# process-compose provides a TUI for monitoring all services and handles
# dependencies (e.g., server waits for postgres to be healthy).
RUN curl -fsSL https://github.com/F1bonacc1/process-compose/releases/download/v1.87.0/process-compose_linux_amd64.tar.gz \
    | tar -xz -C /usr/local/bin process-compose

# GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
    apt-get update && apt-get install -y gh && \
    rm -rf /var/lib/apt/lists/*

# Graphite CLI
RUN npm install -g @withgraphite/graphite-cli

# =============================================================================
# Shell Enhancements
# =============================================================================

# Fish
RUN apt-get update && apt-get install -y --no-install-recommends \
    fish && \
    rm -rf /var/lib/apt/lists/*

# Nushell
RUN curl -fsSL https://github.com/nushell/nushell/releases/download/0.101.0/nu-0.101.0-x86_64-unknown-linux-gnu.tar.gz | \
    tar -xz -C /usr/local/bin --strip-components=1 nu-0.101.0-x86_64-unknown-linux-gnu/nu

# Starship prompt
RUN curl -fsSL https://starship.rs/install.sh | sh -s -- -y

# =============================================================================
# Environment Configuration
# =============================================================================

ENV PATH="/workspace/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/workspace/.venv"

# Shell startup configuration
RUN echo 'cd /workspace' >> /root/.bashrc && \
    echo '[ -f /workspace/.venv/bin/activate ] && source /workspace/.venv/bin/activate' >> /root/.bashrc

CMD ["/bin/bash"]
