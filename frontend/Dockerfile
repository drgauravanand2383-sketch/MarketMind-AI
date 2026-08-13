# MarketMind AI Frontend — production image.
#
# This is a static single-page app (Vite/React) — the two required
# backend URLs (VITE_API_BASE_URL, VITE_WS_BASE_URL) are compiled into
# the JS bundle at *build* time, not read at container-start time like a
# typical server process. Pass them as build args:
#
#   docker build \
#     --build-arg VITE_API_BASE_URL=https://api.example.com/api/v1 \
#     --build-arg VITE_WS_BASE_URL=wss://api.example.com/ws \
#     -t marketmind-frontend .
#
# If they're omitted, the image still builds (Vite has no way to know
# they're required at build time), but every page load in the browser
# will fail immediately with a clear thrown error — see
# src/services/api/config.ts's `validateRequiredUrl` and
# docs/release/PRODUCTION_CONFIGURATION_GUIDE.md's Frontend section.
# There is no way to change these after the image is built without
# rebuilding — a different backend URL means a different image.

# ---- Stage 1: build the static bundle ----
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL
ARG VITE_WS_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_WS_BASE_URL=${VITE_WS_BASE_URL}

RUN npm run build

# ---- Stage 2: serve the bundle with nginx ----
FROM nginx:1.27-alpine AS production

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

# nginx:alpine already ships a non-root `nginx` user (uid 101) — just
# hand it ownership of what it needs to write to at runtime.
RUN chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/log/nginx /etc/nginx/conf.d && \
    touch /var/run/nginx.pid && \
    chown nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 8080

# Use 127.0.0.1, not localhost: nginx's `listen 8080;` (nginx.conf)
# binds IPv4 only, but this Alpine image's busybox wget resolves
# `localhost` to the IPv6 loopback (::1) first — nothing listens
# there, so wget fails with "Connection refused" even though nginx is
# up and serving fine on 127.0.0.1 (and via the published host port,
# which is routed by Docker's NAT rather than in-container DNS).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
