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

RUN turbo prune @softmax/dashboard --docker

# =============================== Build from pruned source ==============================
FROM base AS builder
WORKDIR /metta

ARG NEXT_PUBLIC_DASHBOARD_API_BASE_URL=http://127.0.0.1:8010
ENV NEXT_PUBLIC_DASHBOARD_API_BASE_URL=$NEXT_PUBLIC_DASHBOARD_API_BASE_URL

COPY --from=pruned-source /metta/out/json/ .
RUN pnpm install --frozen-lockfile

COPY --from=pruned-source /metta/out/full/ .
# turbo's pruned sources don't include .env files
COPY dashboard/frontend ./dashboard/frontend

WORKDIR /metta/dashboard/frontend

RUN mkdir -p /metta/dashboard/frontend/public
RUN pnpm run build

# ================================ Serve the Next.js app ================================
FROM node:24-bookworm-slim AS runtime

WORKDIR /app
ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /metta/dashboard/frontend/public ./dashboard/frontend/public
COPY --from=builder --chown=nextjs:nodejs /metta/dashboard/frontend/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /metta/dashboard/frontend/.next/static ./dashboard/frontend/.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "dashboard/frontend/server.js"]
