# This Dockerfile relies on turborepo to optimize the build process.
# Building this image requires the entire metta repo to be used as a build context, due to the global `pnpm-lock.yaml` file.

# ================================ Base image - pnpm and turbo ==========================
FROM node:24-bookworm-slim AS base

WORKDIR /metta

ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"

COPY package.json ./
RUN corepack enable pnpm
RUN pnpm install -g turbo

# ================================ Prepare pruned source with turbo =====================
FROM base AS pruned-source
WORKDIR /metta
COPY . .

RUN turbo prune @softmax/dashboard @softmax/bardo @softmax/pantheon @softmax/diagnose --docker

# =============================== Build from pruned source ==============================
FROM base AS builder
WORKDIR /metta

ARG NEXT_PUBLIC_DASHBOARD_API_BASE_URL=http://127.0.0.1:8010
ENV NEXT_PUBLIC_DASHBOARD_API_BASE_URL=$NEXT_PUBLIC_DASHBOARD_API_BASE_URL
ARG BARDO_BASE_PATH=/bardo
ENV BARDO_BASE_PATH=$BARDO_BASE_PATH
ARG NEXT_PUBLIC_BARDO_BASE_PATH=/bardo
ENV NEXT_PUBLIC_BARDO_BASE_PATH=$NEXT_PUBLIC_BARDO_BASE_PATH
ARG PANTHEON_BASE_PATH=/pantheon
ENV PANTHEON_BASE_PATH=$PANTHEON_BASE_PATH
ARG NEXT_PUBLIC_PANTHEON_BASE_PATH=/pantheon
ENV NEXT_PUBLIC_PANTHEON_BASE_PATH=$NEXT_PUBLIC_PANTHEON_BASE_PATH
ARG DIAGNOSE_BASE_PATH=/diagnose
ENV DIAGNOSE_BASE_PATH=$DIAGNOSE_BASE_PATH
ARG NEXT_PUBLIC_DIAGNOSE_BASE_PATH=/diagnose
ENV NEXT_PUBLIC_DIAGNOSE_BASE_PATH=$NEXT_PUBLIC_DIAGNOSE_BASE_PATH

COPY --from=pruned-source /metta/out/json/ .
RUN pnpm install --frozen-lockfile

COPY --from=pruned-source /metta/out/full/ .
# turbo's pruned sources don't include .env files
COPY dashboard ./dashboard
COPY bardo ./bardo
COPY pantheon ./pantheon
COPY diagnose ./diagnose

RUN mkdir -p /metta/dashboard/public
RUN mkdir -p /metta/bardo/public
RUN mkdir -p /metta/pantheon/public
RUN mkdir -p /metta/diagnose/public
RUN pnpm --dir dashboard run build
RUN pnpm --dir bardo run build
RUN pnpm --dir pantheon run build
RUN pnpm --dir diagnose run build

# ================================ Serve the Next.js app ================================
FROM node:24-bookworm-slim AS runtime

WORKDIR /app
ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /metta/dashboard/public ./dashboard/public
COPY --from=builder --chown=nextjs:nodejs /metta/dashboard/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /metta/dashboard/.next/static ./dashboard/.next/static
COPY --from=builder /metta/bardo/public ./bardo/public
COPY --from=builder --chown=nextjs:nodejs /metta/bardo/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /metta/bardo/.next/static ./bardo/.next/static
COPY --from=builder /metta/pantheon/public ./pantheon/public
COPY --from=builder --chown=nextjs:nodejs /metta/pantheon/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /metta/pantheon/.next/static ./pantheon/.next/static
COPY --from=builder /metta/diagnose/public ./diagnose/public
COPY --from=builder --chown=nextjs:nodejs /metta/diagnose/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /metta/diagnose/.next/static ./diagnose/.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV BARDO_PORT=5175
ENV PANTHEON_PORT=5176
ENV DIAGNOSE_PORT=5177
ENV BARDO_PROXY_URL=http://127.0.0.1:5175/bardo
ENV PANTHEON_PROXY_URL=http://127.0.0.1:5176/pantheon
ENV DIAGNOSE_PROXY_URL=http://127.0.0.1:5177/diagnose

CMD ["sh", "-lc", "PORT=$BARDO_PORT HOSTNAME=127.0.0.1 node bardo/server.js & PORT=$PANTHEON_PORT HOSTNAME=127.0.0.1 node pantheon/server.js & PORT=$DIAGNOSE_PORT HOSTNAME=127.0.0.1 node diagnose/server.js & exec node dashboard/server.js"]
