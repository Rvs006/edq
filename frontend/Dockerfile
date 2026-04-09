FROM node:20-alpine AS build

WORKDIR /app

COPY package.json pnpm-lock.yaml* package-lock.json* ./
RUN corepack enable 2>/dev/null; \
    if [ -f pnpm-lock.yaml ]; then \
      pnpm install --frozen-lockfile; \
    elif [ -f package-lock.json ]; then \
      npm ci; \
    else \
      npm install; \
    fi

COPY . .
RUN if command -v pnpm >/dev/null 2>&1 && [ -f pnpm-lock.yaml ]; then \
      pnpm run build; \
    else \
      npm run build; \
    fi

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Run as non-root: adjust permissions for nginx user
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    touch /var/run/nginx.pid && \
    chown nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
