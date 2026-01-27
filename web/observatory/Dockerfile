# This Dockerfile relies on turborepo to optimize the build process.
# Refer to https://turborepo.com/docs/guides/tools/docker for more details.

# Building this image requires the entire metta repo to be used as a build context, due to the global `pnpm-lock.yaml` file.

# ================================ Base image - pnpm and turbo ==========================
FROM node:24-bookworm-slim AS base

# Set working directory
WORKDIR /metta

ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"

# Install dependencies
COPY package.json ./
RUN corepack enable pnpm
RUN pnpm install -g turbo

# ================================ Prepare pruned source with turbo =====================
FROM base AS pruned-source
WORKDIR /metta
COPY . .

# /metta/out will contain only the relevant files
RUN turbo prune @softmax/observatory --docker

# =============================== Build from pruned source ==============================
FROM base AS builder
WORKDIR /metta

COPY --from=pruned-source /metta/out/json/ .
RUN pnpm install --frozen-lockfile

COPY --from=pruned-source /metta/out/full/ .
# turbo's pruned sources don't include .env files
COPY web/observatory ./web/observatory

WORKDIR /metta/web/observatory

RUN pnpm run build

# ================================ Serve the Next.js app ================================
FROM node:24-bookworm-slim AS runtime

WORKDIR /app
ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /metta/web/observatory/public ./web/observatory/public
COPY --from=builder --chown=nextjs:nodejs /metta/web/observatory/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /metta/web/observatory/.next/static ./web/observatory/.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Start the Next.js server
CMD ["node", "web/observatory/server.js"]
