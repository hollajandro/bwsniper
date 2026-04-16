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
FROM nginx:1.27-alpine

# Remove the default site config
RUN rm /etc/nginx/conf.d/default.conf

# Copy our nginx site config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the Vite build output
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
