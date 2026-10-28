# syntax=docker/dockerfile:1
# Сборка React-фронта и раздача статики через nginx. /api проксируется на сервис api из docker-compose.yml.
# Режим данных фиксируется при сборке: --build-arg VITE_DATA_MODE=mock|api (по умолчанию api).

FROM node:22.12-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_DATA_MODE=api
RUN npx tsc -b && npx vite build --mode "$VITE_DATA_MODE"

FROM nginxinc/nginx-unprivileged:1.27.5-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 8080
