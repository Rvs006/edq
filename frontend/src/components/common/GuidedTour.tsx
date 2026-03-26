import { useState, useEffect, useCallback, useRef } from 'react'
import { X } from 'lucide-react'

export interface TourStep {
  /** CSS selector for the element to highlight */
  selector: string
  /** Title of the tour step */
  title: string
  /** Description text */
  description: string
  /** Preferred popover position relative to the highlighted element */
  position?: 'top' | 'bottom' | 'left' | 'right'
}

interface GuidedTourProps {
  steps: TourStep[]
  isActive: boolean
  onEnd: () => void
  /** Optional callback when step changes */
  onStepChange?: (step: number) => void
}

export default function GuidedTour({ steps, isActive, onEnd, onStepChange }: GuidedTourProps) {
  const [currentStep, setCurrentStep] = useState(0)
  const [rect, setRect] = useState<DOMRect | null>(null)
  const popoverRef = useRef<HTMLDivElement>(null)

  const updatePosition = useCallback(() => {
    if (!isActive || currentStep >= steps.length) return
    const el = document.querySelector(steps[currentStep].selector)
    if (el) {
      el.scrollIntoView({ behavior: 'instant', block: 'nearest', inline: 'nearest' })
      requestAnimationFrame(() => {
        setRect(el.getBoundingClientRect())
      })
    }
  }, [isActive, currentStep, steps])

  useEffect(() => {
    if (!isActive) return
    updatePosition()
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)
    return () => {
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition, true)
    }
  }, [isActive, updatePosition])

  useEffect(() => {
    if (!isActive) {
      setCurrentStep(0)
    }
  }, [isActive])

  if (!isActive || steps.length === 0) return null

  const step = steps[currentStep]
  const pad = 8

  // Build clip-path polygon to cut hole around highlighted element
  const clipPath = rect
    ? `polygon(
        0% 0%, 0% 100%,
        ${rect.left - pad}px 100%,
        ${rect.left - pad}px ${rect.top - pad}px,
        ${rect.right + pad}px ${rect.top - pad}px,
        ${rect.right + pad}px ${rect.bottom + pad}px,
        ${rect.left - pad}px ${rect.bottom + pad}px,
        ${rect.left - pad}px 100%,
        100% 100%, 100% 0%
      )`
    : 'none'

  // Calculate popover position
  const getPopoverStyle = (): React.CSSProperties => {
    if (!rect) return { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }
    const popW = 320
    const pos = step.position || 'bottom'
    const vw = window.innerWidth
    const vh = window.innerHeight

    let top = 0
    let left = 0

    if (pos === 'bottom' && rect.bottom + 12 + 200 < vh) {
      top = rect.bottom + 12
      left = rect.left + rect.width / 2 - popW / 2
    } else if (pos === 'top' && rect.top - 12 - 200 > 0) {
      top = rect.top - 212
      left = rect.left + rect.width / 2 - popW / 2
    } else if (pos === 'right' && rect.right + 12 + popW < vw) {
      top = rect.top + rect.height / 2 - 100
      left = rect.right + 12
    } else if (pos === 'left' && rect.left - 12 - popW > 0) {
      top = rect.top + rect.height / 2 - 100
      left = rect.left - popW - 12
    } else {
      top = rect.bottom + 12
      left = rect.left + rect.width / 2 - popW / 2
    }

    top = Math.max(8, Math.min(top, vh - 220))
    left = Math.max(8, Math.min(left, vw - popW - 8))

    return { top, left, width: popW }
  }

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      const next = currentStep + 1
      setCurrentStep(next)
      onStepChange?.(next)
    } else {
      onEnd()
    }
  }

  const handleBack = () => {
    if (currentStep > 0) {
      const prev = currentStep - 1
      setCurrentStep(prev)
      onStepChange?.(prev)
    }
  }

  return (
    <div className="fixed inset-0 z-[200]">
      {/* Backdrop with clip-path hole */}
      <div
        className="fixed inset-0 bg-black/60 transition-[clip-path] duration-300"
        style={{ clipPath }}
        onClick={onEnd}
      />

      {/* Highlight ring */}
      {rect && (
        <div
          className="fixed border-2 border-blue-400 rounded-lg pointer-events-none z-[201]"
          style={{
            top: rect.top - pad,
            left: rect.left - pad,
            width: rect.width + pad * 2,
            height: rect.height + pad * 2,
            boxShadow: '0 0 0 4px rgba(59, 130, 246, 0.2)',
          }}
        />
      )}

      {/* Popover */}
      <div
        ref={popoverRef}
        className="fixed z-[202] bg-white dark:bg-slate-800 rounded-xl shadow-2xl border border-zinc-200 dark:border-slate-700/50 p-4"
        style={getPopoverStyle()}
      >
        <div className="flex items-center justify-between mb-1">
          <span className="text-[11px] font-medium text-blue-600 dark:text-blue-400">
            Step {currentStep + 1} of {steps.length}
          </span>
          <button
            onClick={onEnd}
            className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-slate-100 mb-1">
          {step.title}
        </h3>
        <p className="text-xs text-zinc-600 dark:text-slate-400 mb-3 leading-relaxed">
          {step.description}
        </p>
        <div className="flex items-center justify-between">
          {/* Dots */}
          <div className="flex gap-1">
            {steps.map((_, i) => (
              <div
                key={i}
                className={`w-1.5 h-1.5 rounded-full transition-colors ${
                  i === currentStep ? 'bg-blue-500' : 'bg-zinc-300 dark:bg-zinc-600'
                }`}
              />
            ))}
          </div>
          {/* Buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={onEnd}
              className="text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
            >
              Skip tour
            </button>
            {currentStep > 0 && (
              <button
                onClick={handleBack}
                className="px-3 py-1 text-xs font-medium border border-zinc-300 dark:border-slate-600 rounded-md hover:bg-zinc-50 dark:hover:bg-slate-700 text-zinc-700 dark:text-slate-300"
              >
                Back
              </button>
            )}
            <button
              onClick={handleNext}
              className="px-3 py-1 text-xs font-medium bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              {currentStep === steps.length - 1 ? 'Finish' : 'Next'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
