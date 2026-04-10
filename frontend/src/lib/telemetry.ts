type ClientErrorPayload = {
  message: string
  stack?: string
  componentStack?: string
  url: string
  timestamp: string
  handled?: boolean
  source?: 'error-boundary' | 'window-error' | 'unhandledrejection'
}

const CLIENT_ERROR_ENDPOINT = '/api/client-errors'

function sendPayload(payload: ClientErrorPayload) {
  const body = JSON.stringify(payload)

  try {
    if (navigator.sendBeacon?.(CLIENT_ERROR_ENDPOINT, body)) {
      return
    }
  } catch {
    // Fall through to fetch-based reporting.
  }

  void fetch(CLIENT_ERROR_ENDPOINT, {
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
  context: Pick<ClientErrorPayload, 'componentStack' | 'handled' | 'source'> = {},
) {
  const err = error instanceof Error ? error : new Error(String(error))

  sendPayload({
    message: err.message || 'Unknown frontend error',
    stack: err.stack?.slice(0, 4000),
    componentStack: context.componentStack?.slice(0, 4000),
    url: window.location.href,
    timestamp: new Date().toISOString(),
    handled: context.handled,
    source: context.source,
  })
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
