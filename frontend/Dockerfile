# =============================================================================
# RankForge Frontend Dockerfile - build with Vite, serve with nginx
# =============================================================================

FROM node:24-alpine AS builder

WORKDIR /app

# VITE_API_URL is baked at build time. The default "/api" expects nginx (or
# another reverse proxy) to forward /api/* to the backend.
ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# -----------------------------------------------------------------------------
FROM nginx:alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
