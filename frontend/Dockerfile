# Frontend: static build served by nginx. Build context: frontend/
# /api is NOT proxied here – Traefik routes it straight to the backend container.

FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
# The MSW worker is only used by `npm run dev:mock`; keep it out of production.
RUN npm run build && rm -f dist/mockServiceWorker.js

FROM nginxinc/nginx-unprivileged:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:8080/ || exit 1
