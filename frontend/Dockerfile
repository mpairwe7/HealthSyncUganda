FROM oven/bun:1.4-alpine AS deps
WORKDIR /app
# Repo ships `bun.lock` (newer text format), not the legacy binary `bun.lockb`.
# Use a glob that matches either, but enforce `--frozen-lockfile` with no
# fallback — silent unlocked installs are a reproducibility hazard.
COPY package.json bun.lock* ./
RUN bun install --frozen-lockfile

FROM oven/bun:1.4-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* vars are baked into the JS bundle at build time.
# Pass --build-arg NEXT_PUBLIC_API_BASE_URL=<backend-url> so the client
# calls the correct backend for each deployment environment.
# Default points to the Crane Cloud staging backend; override in CI for
# pilot/national deployments.
ARG NEXT_PUBLIC_API_BASE_URL=https://healthsync-backend-staging-9b4ecff1.renu-01.cranecloud.io
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN bun run build

FROM oven/bun:1.4-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

# Drop to an unprivileged user (distinct name to avoid colliding with the
# image's built-in `bun` user).
RUN addgroup -S appgroup && adduser -S -G appgroup appuser \
    && chown -R appuser:appgroup /app
USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -qO- http://127.0.0.1:3000/ >/dev/null 2>&1 || exit 1

CMD ["bun", "run", "start"]
