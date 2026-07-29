# ── Stage 1: build the Astro landing site ─────────────────────────────────────
# Build context is the repository root, matching apps/frontend.
FROM node:22-slim AS build

WORKDIR /app

COPY apps/landing/package.json apps/landing/package-lock.json ./

RUN npm install -g npm@11.6.2
RUN npm ci

COPY apps/landing ./

# Read at build time by src/config.ts and inlined into the static HTML.
ARG VITE_APP_URL
ARG VITE_GITHUB_URL
ARG VITE_DEMO_VIDEO_URL
ARG VITE_USSD_CODE
ARG VITE_WHATSAPP_NUMBER
ENV VITE_APP_URL=$VITE_APP_URL
ENV VITE_GITHUB_URL=$VITE_GITHUB_URL
ENV VITE_DEMO_VIDEO_URL=$VITE_DEMO_VIDEO_URL
ENV VITE_USSD_CODE=$VITE_USSD_CODE
ENV VITE_WHATSAPP_NUMBER=$VITE_WHATSAPP_NUMBER

RUN npm run build

# ── Stage 2: serve with Caddy ─────────────────────────────────────────────────
FROM caddy:2-alpine AS runtime

COPY --from=build /app/dist /srv
COPY apps/landing/Caddyfile /etc/caddy/Caddyfile

ENV PORT=3000
EXPOSE $PORT

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
