/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_CLIENT_ERROR_ENDPOINT?: string
  readonly VITE_SENTRY_ENABLED?: string
  readonly VITE_SENTRY_DSN?: string
  readonly VITE_SENTRY_ENVIRONMENT?: string
  readonly VITE_SENTRY_RELEASE?: string
  readonly VITE_SENTRY_TRACES_SAMPLE_RATE?: string
  readonly VITE_SOURCEMAP?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
