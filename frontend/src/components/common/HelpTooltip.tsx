import { useState, useRef, useEffect } from 'react'
import { HelpCircle } from 'lucide-react'

interface HelpTooltipProps {
  content: string
  title?: string
  className?: string
}

export default function HelpTooltip({ content, title, className = '' }: HelpTooltipProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  return (
    <div ref={ref} className={`relative inline-flex ${className}`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="p-0.5 rounded-full text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 transition-colors"
        aria-label={title || 'Help'}
      >
        <HelpCircle className="w-4 h-4" />
      </button>

      {open && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-white rounded-lg shadow-lg border border-zinc-200 text-left">
          {title && <p className="text-xs font-semibold text-zinc-900 mb-1">{title}</p>}
          <p className="text-xs text-zinc-600 leading-relaxed">{content}</p>
          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-px">
            <div className="w-2.5 h-2.5 bg-white border-b border-r border-zinc-200 rotate-45 -translate-y-1/2" />
          </div>
        </div>
      )}
    </div>
  )
}
