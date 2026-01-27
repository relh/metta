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
RUN pnpm run build:scripts

# ================================ Serve the Next.js app ================================
FROM base AS runtime

WORKDIR /metta/web/softmax.com
ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /metta/web/softmax.com/public ./
COPY --from=builder --chown=nextjs:nodejs /metta/web/softmax.com/.next/standalone /metta/
COPY --from=builder --chown=nextjs:nodejs /metta/web/softmax.com/.next/static .next/

# Prisma files for database migrations
COPY --from=builder /metta/web/softmax.com/prisma ./
COPY --from=builder /metta/web/softmax.com/package.json ./

# Install Prisma (CLI + client) for migrations and update-softmax-team script.
#
# TODO - installing this with npm instead of pnpm is inconsistent and slower than pnpm;
# but naive pnpm results in 2.2GB image instead of 1.4GB because of pnpm caches. It's probably possible to optimize this.
RUN PRISMA_VERSION=$(node -p "require('./package.json').dependencies['@prisma/client'].replace(/^[\^~]/, '')") && \
    npm install @prisma/client@$PRISMA_VERSION prisma@$PRISMA_VERSION --silent && \
    npx prisma generate

# Pre-compiled script for update-softmax-team cronjob
COPY --from=builder /metta/web/softmax.com/scripts/update-softmax-team.js ./scripts/

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Start the Next.js server
CMD ["node", "web/softmax.com/server.js"]
