# ---------- deps ----------
FROM node:20-alpine AS deps

WORKDIR /app

# Manifests only, so this layer survives every source-only change.
COPY package.json package-lock.json ./
RUN npm ci

# ---------- builder ----------
FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* values are inlined into the JavaScript at build time, not read
# from the environment at runtime. They have to be present *here* — passing
# them only through docker-compose's env_file leaves the browser bundle with
# `undefined`, and lib/env.ts throws on the first render.
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_ENVIRONMENT=production

ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_ENVIRONMENT=$NEXT_PUBLIC_ENVIRONMENT \
    NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ---------- runtime ----------
FROM node:20-alpine AS runner

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup -g 10001 -S recover && adduser -u 10001 -S recover -G recover

WORKDIR /app

COPY --from=builder /app/public ./public
# standalone carries its own minimal node_modules and server.js; static assets
# are not traced into it and have to be copied alongside.
COPY --from=builder --chown=recover:recover /app/.next/standalone ./
COPY --from=builder --chown=recover:recover /app/.next/static ./.next/static

USER recover

EXPOSE 3000

CMD ["node", "server.js"]
