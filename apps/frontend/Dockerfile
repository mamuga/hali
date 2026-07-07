# ── Stage 1: build the React PWA ──────────────────────────────────────────────
FROM node:22-slim AS build

WORKDIR /app

COPY package.json package-lock.json nx.json tsconfig.base.json ./
COPY packages ./packages
COPY apps/frontend ./apps/frontend

RUN npm install -g npm@11.6.2
RUN npm ci

ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npx nx run frontend:build

# ── Stage 2: serve with Caddy ─────────────────────────────────────────────────
FROM caddy:2-alpine AS runtime

COPY --from=build /app/dist/apps/frontend /srv
COPY apps/frontend/Caddyfile /etc/caddy/Caddyfile

ENV PORT=3000
EXPOSE $PORT

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
