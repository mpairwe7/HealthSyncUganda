FROM oven/bun:1.3-alpine AS deps
WORKDIR /app
COPY package.json bun.lockb* ./
RUN bun install --frozen-lockfile || bun install

FROM oven/bun:1.3-alpine AS builder
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

FROM oven/bun:1.3-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
EXPOSE 3000
CMD ["bun", "run", "start"]
