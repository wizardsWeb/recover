# ============================================================================
# Recover frontend — production image.
#
# Three stages: dependencies, build, run. The runtime stage carries only Next's
# standalone output — a self-contained server.js plus the node_modules actually
# traced as reachable — so it never runs an install of its own.
# ============================================================================

# ---------- deps ----------
FROM node:20-alpine AS deps

# Alpine ships musl; some of Next's native binaries want glibc symbols.
RUN apk add --no-cache libc6-compat

WORKDIR /app

# Manifests only, so this layer survives every source-only change.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# ---------- builder ----------
FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1

# NEXT_PUBLIC_* values are inlined into the JavaScript at build time, not read
# from the environment at runtime. They have to be present *here* — supplying
# them only as Container App env vars leaves the browser bundle with
# `undefined`, and lib/env.ts throws on the first render. The CI workflow
# passes them with --build-arg; docker-compose.prod.yml passes them under
# `build.args`.
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_APP_URL
ARG NEXT_PUBLIC_ENVIRONMENT

ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_APP_URL=$NEXT_PUBLIC_APP_URL \
    NEXT_PUBLIC_ENVIRONMENT=$NEXT_PUBLIC_ENVIRONMENT

RUN npm run build

# ---------- runner ----------
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

# -G nodejs is not optional: Alpine's BusyBox adduser otherwise drops the
# account into `nogroup`, which would make the --chown=nextjs:nodejs below
# grant nothing through its group bit.
RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 -G nodejs nextjs

COPY --from=builder /app/public ./public
# standalone carries its own minimal node_modules and server.js; static assets
# are not traced into it and have to be copied alongside.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

# wget is in busybox, so this costs nothing. / is the public marketing page —
# it renders without a session, which a probe on an authenticated route would
# not.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
