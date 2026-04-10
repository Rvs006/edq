import * as Sentry from '@sentry/react'

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

function parseSampleRate(value: string | undefined) {
  const parsed = Number.parseFloat(value ?? '')
  if (Number.isNaN(parsed)) {
    return 0
  }
  return Math.min(Math.max(parsed, 0), 1)
}

const sentryDsn = import.meta.env.VITE_SENTRY_DSN?.trim() || ''
const sentryEnabled = parseBoolean(import.meta.env.VITE_SENTRY_ENABLED, Boolean(sentryDsn)) && Boolean(sentryDsn)
const sentryEnvironment = import.meta.env.VITE_SENTRY_ENVIRONMENT?.trim() || import.meta.env.MODE || 'production'
const sentryRelease = import.meta.env.VITE_SENTRY_RELEASE?.trim() || undefined
const sentryTracesSampleRate = parseSampleRate(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE)

let initialized = false

export function initFrontendSentry() {
  if (initialized || !sentryEnabled || typeof window === 'undefined') {
    return
  }

  Sentry.init({
    dsn: sentryDsn,
    enabled: true,
    environment: sentryEnvironment,
    release: sentryRelease,
    tracesSampleRate: sentryTracesSampleRate,
    sendDefaultPii: false,
  })
  initialized = true
}

export function isFrontendSentryEnabled() {
  return sentryEnabled
}

export function getFrontendSentryMetadata() {
  return {
    sentryEnabled,
    sentryEnvironment,
    sentryRelease,
  }
}

export function captureFrontendException(
  error: unknown,
  context: {
    tags?: Record<string, string>
    extra?: Record<string, unknown>
  } = {},
) {
  if (!initialized || !sentryEnabled) {
    return
  }

  const normalized = error instanceof Error ? error : new Error(String(error))
  Sentry.withScope((scope) => {
    for (const [key, value] of Object.entries(context.tags ?? {})) {
      scope.setTag(key, value)
    }
    for (const [key, value] of Object.entries(context.extra ?? {})) {
      scope.setExtra(key, value)
    }
    Sentry.captureException(normalized)
  })
}
