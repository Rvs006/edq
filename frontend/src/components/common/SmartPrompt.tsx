import { AlertTriangle, Info, CheckCircle, XCircle } from 'lucide-react'

type SmartPromptVariant = 'warning' | 'info' | 'success' | 'error'

interface SmartPromptProps {
  /** The prompt message (supports JSX) */
  children: React.ReactNode
  /** Visual variant */
  variant?: SmartPromptVariant
  /** Optional action button */
  action?: {
    label: string
    onClick: () => void
  }
  /** Optional dismiss handler */
  onDismiss?: () => void
  className?: string
}

const variantStyles: Record<SmartPromptVariant, { bg: string; border: string; text: string; icon: typeof AlertTriangle }> = {
  warning: {
    bg: 'bg-amber-50 dark:bg-amber-950/30',
    border: 'border-amber-200 dark:border-amber-800',
    text: 'text-amber-800 dark:text-amber-200',
    icon: AlertTriangle,
  },
  info: {
    bg: 'bg-blue-50 dark:bg-blue-950/30',
    border: 'border-blue-200 dark:border-blue-800',
    text: 'text-blue-800 dark:text-blue-200',
    icon: Info,
  },
  success: {
    bg: 'bg-emerald-50 dark:bg-emerald-950/30',
    border: 'border-emerald-200 dark:border-emerald-800',
    text: 'text-emerald-800 dark:text-emerald-200',
    icon: CheckCircle,
  },
  error: {
    bg: 'bg-red-50 dark:bg-red-950/30',
    border: 'border-red-200 dark:border-red-800',
    text: 'text-red-800 dark:text-red-200',
    icon: XCircle,
  },
}

export default function SmartPrompt({
  children,
  variant = 'warning',
  action,
  onDismiss,
  className = '',
}: SmartPromptProps) {
  const styles = variantStyles[variant]
  const Icon = styles.icon

  return (
    <div
      className={`flex items-center justify-between gap-3 px-4 py-3 rounded-lg border text-[13px] ${styles.bg} ${styles.border} ${styles.text} ${className}`}
    >
      <div className="flex items-center gap-3 min-w-0">
        <Icon className="w-4 h-4 flex-shrink-0" />
        <span className="min-w-0">{children}</span>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        {action && (
          <button
            onClick={action.onClick}
            className={`px-3 py-1 text-xs font-medium border rounded-md transition-colors ${styles.border} hover:opacity-80`}
          >
            {action.label}
          </button>
        )}
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="text-current opacity-60 hover:opacity-100 transition-opacity"
            aria-label="Dismiss"
          >
            <XCircle className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  )
}
