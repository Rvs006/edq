import {
  captureFrontendException,
  getFrontendSentryMetadata,
  isFrontendSentryEnabled,
} from './sentry'

type ClientErrorPayload = {
  message: string
  stack?: string
  componentStack?: string
  url: string
  timestamp: string
  handled?: boolean
  source?: 'error-boundary' | 'window-error' | 'unhandledrejection'
  capturedByFrontendSentry?: boolean
  telemetry?: {
    sentry_enabled: boolean
    sentry_environment?: string
    sentry_release?: string
  }
}

const DEFAULT_CLIENT_ERROR_ENDPOINT = '/api/client-errors'

type FrontendTelemetryConfig = {
  clientErrorEndpoint: string
  sentryEnabled: boolean
  sentryEnvironment: string
  sentryRelease?: string
}

function parseBoolean(value: string | undefined, fallback = false) {
  if (value === undefined) {
    return fallback
  }
  const normalized = value.trim().toLowerCase()
  if (['1', 'true', 'yes', 'on'].includes(normalized)) {
    return true
  }
  if (['0', 'false', 'no', 'off'].includes(normalized)) {
    return false
  }
  return fallback
}

function normalizeEndpoint(endpoint: string | undefined) {
  const candidate = endpoint?.trim() || DEFAULT_CLIENT_ERROR_ENDPOINT
  const base = typeof window !== 'undefined' ? window.location.origin : 'http://localhost'
  try {
    return new URL(candidate, base).toString()
  } catch {
    return candidate
  }
}

function getTelemetryConfig(): FrontendTelemetryConfig {
  const sentryMetadata = getFrontendSentryMetadata()

  return {
    clientErrorEndpoint: normalizeEndpoint(import.meta.env.VITE_CLIENT_ERROR_ENDPOINT),
    sentryEnabled: sentryMetadata.sentryEnabled,
    sentryEnvironment: sentryMetadata.sentryEnvironment,
    sentryRelease: sentryMetadata.sentryRelease,
  }
}

const telemetryConfig = getTelemetryConfig()

function sendPayload(payload: ClientErrorPayload) {
  if (typeof window === 'undefined') {
    return
  }

  const body = JSON.stringify(payload)
  const endpoint = telemetryConfig.clientErrorEndpoint

  try {
    if (navigator.sendBeacon?.(endpoint, body)) {
      return
    }
  } catch {
    // Fall through to fetch-based reporting.
  }

  void fetch(endpoint, {
    method: 'POST',
    body,
    headers: { 'Content-Type': 'application/json' },
    keepalive: true,
    credentials: 'same-origin',
  }).catch(() => {
    // Telemetry must never break the application flow.
  })
}

export function reportClientError(
  error: unknown,
  context: {
    componentStack?: string | null
    handled?: boolean
    source?: ClientErrorPayload['source']
  } = {},
) {
  if (typeof window === 'undefined') {
    return
  }

  const err = error instanceof Error ? error : new Error(String(error))
  const capturedByFrontendSentry = Boolean(context.handled && isFrontendSentryEnabled())
  const telemetry = telemetryConfig.sentryEnabled
    ? {
        sentry_enabled: true,
        sentry_environment: telemetryConfig.sentryEnvironment,
        sentry_release: telemetryConfig.sentryRelease,
      }
    : undefined

  sendPayload({
    message: err.message || 'Unknown frontend error',
    stack: err.stack?.slice(0, 4000),
    componentStack: context.componentStack?.slice(0, 4000),
    url: window.location.href,
    timestamp: new Date().toISOString(),
    handled: context.handled,
    source: context.source,
    capturedByFrontendSentry,
    telemetry,
  })

  if (capturedByFrontendSentry) {
    captureFrontendException(err, {
      tags: {
        source: context.source ?? 'error-boundary',
      },
      extra: {
        componentStack: context.componentStack ?? '',
        url: window.location.href,
      },
    })
  }
}

export function installGlobalErrorTelemetry() {
  if (typeof window === 'undefined') {
    return
  }

  const keyedWindow = window as Window & { __edqTelemetryInstalled?: boolean }
  if (keyedWindow.__edqTelemetryInstalled) {
    return
  }
  keyedWindow.__edqTelemetryInstalled = true

  window.addEventListener('error', (event) => {
    reportClientError(event.error ?? event.message, { handled: false, source: 'window-error' })
  })

  window.addEventListener('unhandledrejection', (event) => {
    reportClientError(event.reason, { handled: false, source: 'unhandledrejection' })
  })
}
