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
