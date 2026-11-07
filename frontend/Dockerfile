# Frontend image: build the Vite app, serve it with nginx, and proxy /api to the backend so the
# browser sees ONE origin (no CORS, same as local dev). Used by docker-compose.yml.
# On Vercel you don't need this file; Vercel builds the app itself (see docs/deploy.md).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Leave empty to call /api on the same origin (the nginx proxy below). Set it only if the
# backend lives on a different domain, e.g. --build-arg VITE_API_URL=https://api.example.com
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine
# The official image fills in ${BACKEND_URL} from this template when the container starts.
ENV BACKEND_URL=http://backend:8000
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
