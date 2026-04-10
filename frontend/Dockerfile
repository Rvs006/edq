FROM node:20-alpine AS build

WORKDIR /app

# Frontend telemetry and API config are build-time envs because Vite bakes them into the bundle.
ARG VITE_API_URL=/api
ARG VITE_CLIENT_ERROR_ENDPOINT=/api/client-errors
ARG VITE_SENTRY_ENABLED=false
ARG VITE_SENTRY_DSN=
ARG VITE_SENTRY_ENVIRONMENT=production
ARG VITE_SENTRY_RELEASE=
ARG VITE_SENTRY_TRACES_SAMPLE_RATE=0.0
ARG VITE_SOURCEMAP=false

ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_CLIENT_ERROR_ENDPOINT=${VITE_CLIENT_ERROR_ENDPOINT}
ENV VITE_SENTRY_ENABLED=${VITE_SENTRY_ENABLED}
ENV VITE_SENTRY_DSN=${VITE_SENTRY_DSN}
ENV VITE_SENTRY_ENVIRONMENT=${VITE_SENTRY_ENVIRONMENT}
ENV VITE_SENTRY_RELEASE=${VITE_SENTRY_RELEASE}
ENV VITE_SENTRY_TRACES_SAMPLE_RATE=${VITE_SENTRY_TRACES_SAMPLE_RATE}
ENV VITE_SOURCEMAP=${VITE_SOURCEMAP}

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
    chown -R nginx:nginx /etc/nginx/conf.d && \
    chown nginx:nginx /etc/nginx/conf.d/default.conf && \
    touch /var/run/nginx.pid && \
    chown nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
