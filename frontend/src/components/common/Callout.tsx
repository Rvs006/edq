import { Info, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'

type CalloutVariant = 'info' | 'warning' | 'success' | 'error'

interface CalloutProps {
  variant?: CalloutVariant
  title?: string
  children: React.ReactNode
  className?: string
}

const variants: Record<CalloutVariant, { icon: React.ElementType; bg: string; border: string; text: string; iconColor: string }> = {
  info: {
    icon: Info,
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    text: 'text-blue-800',
    iconColor: 'text-blue-500',
  },
  warning: {
    icon: AlertTriangle,
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    text: 'text-amber-800',
    iconColor: 'text-amber-500',
  },
  success: {
    icon: CheckCircle2,
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    text: 'text-emerald-800',
    iconColor: 'text-emerald-500',
  },
  error: {
    icon: XCircle,
    bg: 'bg-red-50',
    border: 'border-red-200',
    text: 'text-red-800',
    iconColor: 'text-red-500',
  },
}

export default function Callout({ variant = 'info', title, children, className = '' }: CalloutProps) {
  const v = variants[variant]
  const Icon = v.icon

  return (
    <div className={`flex gap-3 p-3 rounded-lg border ${v.bg} ${v.border} ${className}`}>
      <Icon className={`w-5 h-5 shrink-0 mt-0.5 ${v.iconColor}`} />
      <div className="flex-1 min-w-0">
        {title && <p className={`text-sm font-medium ${v.text} mb-0.5`}>{title}</p>}
        <div className={`text-sm ${v.text} opacity-90`}>{children}</div>
      </div>
    </div>
  )
}
