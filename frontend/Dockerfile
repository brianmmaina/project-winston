# syntax=docker/dockerfile:1.7

# ---------- build ----------
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --legacy-peer-deps 2>/dev/null || npm install

COPY . .

# Build-time env baked into the bundle.
#
# * VITE_API_URL: leave empty in production so the SPA emits relative URLs that
#   go through the same nginx that serves the static assets (see nginx.conf).
# * VITE_API_KEY: optional; if set, the SPA attaches ``Authorization: Bearer``
#   on every request. Pair with ``API_KEY`` on the backend.
ARG VITE_API_URL=""
ARG VITE_API_KEY=""
ENV VITE_API_URL=$VITE_API_URL \
    VITE_API_KEY=$VITE_API_KEY

RUN npm run build

# ---------- serve ----------
FROM nginx:1.27-alpine

# Drop default site so our config is the only one.
RUN rm -f /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/app.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

ENV PORT=8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:${PORT}/nginx-health || exit 1

CMD ["/bin/sh", "-c", "envsubst '${PORT} ${BACKEND_URL}' < /etc/nginx/conf.d/app.conf.template > /etc/nginx/conf.d/app.conf && nginx -g 'daemon off;'"]
