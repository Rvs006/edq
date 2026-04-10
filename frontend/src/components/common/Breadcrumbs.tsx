/**
 * Breadcrumbs - Navigation breadcrumb trail for detail pages.
 *
 * Renders a horizontal list of links separated by chevrons.
 * The last item represents the current page and is not clickable.
 *
 * @example
 * ```tsx
 * import Breadcrumbs from '@/components/common/Breadcrumbs'
 *
 * <Breadcrumbs items={[
 *   { label: 'Devices', href: '/devices' },
 *   { label: device.hostname },
 * ]} />
 * ```
 */
import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

export interface BreadcrumbItem {
  /** Display label */
  label: string
  /** Navigation target. Omit for the current (last) page. */
  href?: string
}

export interface BreadcrumbsProps {
  items: BreadcrumbItem[]
  /** Additional CSS classes */
  className?: string
}

export default function Breadcrumbs({ items, className = '' }: BreadcrumbsProps) {
  if (items.length === 0) return null

  return (
    <nav aria-label="Breadcrumb" className={`flex items-center gap-1.5 text-sm ${className}`}>
      {items.map((item, idx) => {
        const isLast = idx === items.length - 1
        return (
          <span key={idx} className="flex items-center gap-1.5">
            {idx > 0 && (
              <ChevronRight className="w-3.5 h-3.5 text-zinc-400 dark:text-slate-500 shrink-0" />
            )}
            {isLast || !item.href ? (
              <span
                aria-current={isLast ? 'page' : undefined}
                className={`truncate max-w-[200px] ${
                isLast
                  ? 'font-medium text-zinc-900 dark:text-slate-100'
                  : 'text-zinc-500 dark:text-slate-400'
              }`}
              >
                {item.label}
              </span>
            ) : (
              <Link
                to={item.href}
                className="text-zinc-500 dark:text-slate-400 hover:text-brand-500 dark:hover:text-brand-400 truncate max-w-[200px] transition-colors"
              >
                {item.label}
              </Link>
            )}
          </span>
        )
      })}
    </nav>
  )
}
