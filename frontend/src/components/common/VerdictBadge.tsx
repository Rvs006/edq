import { CheckCircle2, XCircle, AlertTriangle, MinusCircle, Clock, Info, ShieldOff } from 'lucide-react'

type Verdict = 'pass' | 'fail' | 'advisory' | 'qualified_pass' | 'na' | 'info' | 'pending' | 'skipped_safe_mode' | string

const config: Record<string, { label: string; className: string; icon: React.ElementType }> = {
  pass: { label: 'Pass', className: 'badge-pass', icon: CheckCircle2 },
  fail: { label: 'Fail', className: 'badge-fail', icon: XCircle },
  advisory: { label: 'Advisory', className: 'badge-advisory', icon: AlertTriangle },
  qualified_pass: { label: 'Qualified Pass', className: 'badge-qualified-pass', icon: CheckCircle2 },
  na: { label: 'N/A', className: 'badge-na', icon: MinusCircle },
  'n/a': { label: 'N/A', className: 'badge-na', icon: MinusCircle },
  info: { label: 'Info', className: 'badge-info', icon: Info },
  pending: { label: 'Pending', className: 'badge-pending', icon: Clock },
  skipped_safe_mode: { label: 'Skipped', className: 'badge-na', icon: ShieldOff },
}

interface VerdictBadgeProps {
  verdict: Verdict
  size?: 'sm' | 'md'
  showIcon?: boolean
}

export default function VerdictBadge({ verdict, size = 'sm', showIcon = false }: VerdictBadgeProps) {
  const v = config[verdict?.toLowerCase()] || config.pending
  const Icon = v.icon
  const sizeClass = size === 'sm' ? 'text-[10px]' : 'text-xs'

  return (
    <span className={`${v.className} ${sizeClass}`}>
      {showIcon && <Icon className="w-3 h-3 mr-1" />}
      {v.label}
    </span>
  )
}

export function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: 'badge-pending',
    selecting_interface: 'bg-purple-50 text-purple-700 border border-purple-200 dark:bg-purple-950/40 dark:text-purple-400 dark:border-purple-800',
    syncing: 'bg-sky-50 text-sky-700 border border-sky-200 dark:bg-sky-950/40 dark:text-sky-400 dark:border-sky-800',
    running: 'bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800',
    paused_manual: 'bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800',
    paused_cable: 'bg-orange-50 text-orange-700 border border-orange-200 dark:bg-orange-950/40 dark:text-orange-400 dark:border-orange-800',
    awaiting_manual: 'bg-yellow-50 text-yellow-700 border border-yellow-200 dark:bg-yellow-950/40 dark:text-yellow-400 dark:border-yellow-800',
    awaiting_review: 'bg-indigo-50 text-indigo-700 border border-indigo-200 dark:bg-indigo-950/40 dark:text-indigo-400 dark:border-indigo-800',
    completed: 'badge-pass',
    failed: 'badge-fail',
    cancelled: 'badge-na',
  }
  const label = status?.replace(/_/g, ' ') || 'unknown'
  return <span className={`badge text-[10px] capitalize ${styles[status] || 'badge-na'}`}>{label}</span>
}
