type StatusDotVariant = 'online' | 'offline' | 'warning' | 'error' | 'idle' | string

const dotColors: Record<string, string> = {
  online: 'bg-emerald-500',
  connected: 'bg-emerald-500',
  running: 'bg-blue-500',
  selecting_interface: 'bg-purple-500',
  syncing: 'bg-sky-500',
  offline: 'bg-zinc-300',
  idle: 'bg-zinc-300',
  warning: 'bg-amber-500',
  paused_manual: 'bg-amber-500',
  paused_cable: 'bg-orange-500',
  error: 'bg-red-500',
  failed: 'bg-red-500',
}

interface StatusDotProps {
  status: StatusDotVariant
  pulse?: boolean
  size?: 'sm' | 'md' | 'lg'
  label?: string
  className?: string
}

export default function StatusDot({ status, pulse, size = 'md', label, className = '' }: StatusDotProps) {
  const color = dotColors[status?.toLowerCase()] || 'bg-zinc-300'
  const shouldPulse = pulse ?? ['online', 'running', 'selecting_interface', 'syncing', 'connected'].includes(status?.toLowerCase())
  const sizeClass = size === 'sm' ? 'w-2 h-2' : size === 'lg' ? 'w-3.5 h-3.5' : 'w-2.5 h-2.5'

  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      <span className={`rounded-full shrink-0 ${color} ${sizeClass} ${shouldPulse ? 'animate-pulse' : ''}`} />
      {label && <span className="text-xs text-zinc-600 capitalize">{label.replace(/_/g, ' ')}</span>}
    </span>
  )
}
