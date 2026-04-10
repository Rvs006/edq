import { Component, type ErrorInfo, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { reportClientError } from '@/lib/telemetry'

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
  onError?: (error: Error, errorInfo: ErrorInfo) => void
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('[ErrorBoundary] Caught error:', error, errorInfo)
    reportClientError(error, {
      componentStack: errorInfo.componentStack,
      handled: true,
      source: 'error-boundary',
    })
    this.props.onError?.(error, errorInfo)
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null })
  }

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="flex flex-col items-center justify-center p-8 text-center text-zinc-900 dark:text-slate-100">
          <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-950/30 flex items-center justify-center mb-4">
            <AlertTriangle className="w-6 h-6 text-red-600" />
          </div>
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-slate-100 mb-2">Something went wrong</h2>
          <p className="text-sm text-zinc-500 dark:text-slate-400 mb-4 max-w-md">
            {this.state.error?.message || 'An unexpected error occurred.'}
          </p>
          <button
            onClick={this.handleReset}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-lg hover:bg-brand-600 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Try Again
          </button>
        </div>
      )
    }

    return this.props.children
  }
}

/** Page-level error boundary with full-height centering */
export function PageErrorBoundary({ children }: { children: ReactNode }) {
  const location = useLocation()
  return (
    <ErrorBoundary
      key={location.pathname}
      fallback={
        <div className="flex flex-col items-center justify-center min-h-[60vh] p-8 text-center text-zinc-900 dark:text-slate-100">
          <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-950/30 flex items-center justify-center mb-4">
            <AlertTriangle className="w-8 h-8 text-red-600" />
          </div>
          <h2 className="text-xl font-semibold text-zinc-900 dark:text-slate-100 mb-2">Page Error</h2>
          <p className="text-sm text-zinc-500 dark:text-slate-400 mb-6 max-w-md">
            This page encountered an error. Try refreshing or navigating to another page.
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => window.location.reload()}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-lg hover:bg-brand-600 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh Page
            </button>
            <a
              href="/"
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-zinc-700 dark:text-slate-200 bg-zinc-100 dark:bg-slate-800 rounded-lg hover:bg-zinc-200 dark:hover:bg-slate-700 transition-colors"
            >
              Go to Dashboard
            </a>
          </div>
        </div>
      }
    >
      {children}
    </ErrorBoundary>
  )
}
