# ── Stage 1: build the React/Vite app ───────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

# Install dependencies first (separate layer → cache-friendly)
COPY package.json package-lock.json ./
RUN npm ci --prefer-offline

# Copy source and build
COPY . .
RUN npm run build

# ── Stage 2: serve with nginx ────────────────────────────────────────────────
FROM alpine:3.22

# Install the distro nginx package instead of the official nginx image, which
# includes extra modules that pull in libxpm.
RUN apk add --no-cache nginx \
    && mkdir -p /run/nginx \
    && rm -f /etc/nginx/http.d/default.conf

# Copy our nginx site config
COPY nginx.conf /etc/nginx/http.d/default.conf

# Copy the Vite build output
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
