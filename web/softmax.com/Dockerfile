# This Dockerfile relies on turborepo to optimize the build process.
# Refer to https://turborepo.com/docs/guides/tools/docker for more details.

# Building this image requires the entire metta repo to be used as a build context, due to the global `pnpm-lock.yaml` file.

# ================================ Base image - pnpm and turbo ==========================
FROM node:24-bookworm-slim AS base

# Set working directory
WORKDIR /metta

ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"

# Install OpenSSL for Prisma client
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && apt-get install -y openssl

COPY package.json ./
RUN corepack enable pnpm
RUN pnpm install -g turbo

# ================================ Prepare pruned source with turbo =====================
FROM base AS pruned-source
WORKDIR /metta

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.jsonc ./
COPY web/ ./web/
COPY notebooks/utils/ ./notebooks/utils/

# /metta/out will contain only the relevant files
RUN turbo prune @softmax/website --docker

# =============================== Build from pruned source ==============================
FROM base AS builder
WORKDIR /metta

COPY --from=pruned-source /metta/out/json/ .
RUN pnpm install --frozen-lockfile

COPY --from=pruned-source /metta/out/full/ .
# turbo's pruned sources don't include .env files
COPY web/softmax.com ./web/softmax.com

WORKDIR /metta/web/softmax.com

RUN pnpm run db:generate
RUN pnpm run build

# ================================ Serve the Next.js app ================================
FROM base AS runtime

WORKDIR /metta
ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy the entire built workspace from builder
COPY --from=builder --chown=nextjs:nodejs /metta .

# Set corepack home to a shared location and prepare pnpm (version from root package.json)
ENV COREPACK_HOME=/opt/corepack
RUN mkdir -p /opt/corepack && \
    corepack prepare --activate && \
    chown -R nextjs:nodejs /opt/corepack

WORKDIR /metta/web/softmax.com

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["pnpm", "start"]
