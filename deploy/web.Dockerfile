# Stage 1: build the React app (Node is needed only here, never on the host).
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund --fetch-retries=5 --fetch-timeout=120000
COPY frontend/ ./
RUN npm run build

# Stage 2: Caddy serves the static build and proxies /api, /docs and /storage.
FROM caddy:2.11.4-alpine
# The stock binary carries the cap_net_bind_service file capability; with cap_drop ALL and
# no-new-privileges the kernel refuses to exec it. We listen on 8080/8443, so drop the capability
# (cp does not copy extended attributes).
RUN cp /usr/bin/caddy /tmp/caddy && mv /tmp/caddy /usr/bin/caddy \
 && addgroup -S -g 10001 app && adduser -S -D -H -u 10001 -G app app \
 && mkdir -p /data /config && chown -R app:app /data /config
COPY deploy/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
USER app
ENV XDG_DATA_HOME=/data XDG_CONFIG_HOME=/config
EXPOSE 8080 8443
