import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { X, ChevronLeft, ChevronRight, Sparkles } from 'lucide-react'

interface TourStep {
  page: string
  title: string
  description: string
  targetSelector: string
  position: 'top' | 'bottom' | 'left' | 'right'
}

const TOUR_STEPS: TourStep[] = [
  {
    page: '/',
    title: 'Welcome to EDQ',
    description: "This is your Dashboard — a quick overview of testing activity. The numbers show your team's real testing history.",
    targetSelector: '[data-tour="kpi-grid"]',
    position: 'bottom',
  },
  {
    page: '/',
    title: 'Quick Actions',
    description: 'These buttons are your main entry points. Add a device, start a test, or generate a report.',
    targetSelector: '[data-tour="quick-actions"]',
    position: 'top',
  },
  {
    page: '/devices',
    title: 'Device Inventory',
    description: 'All registered devices across projects. Use Add Device to register one manually, or Discover to find devices on the network.',
    targetSelector: '[data-tour="devices-toolbar"]',
    position: 'bottom',
  },
  {
    page: '/test-runs',
    title: 'Test Sessions',
    description: 'Each test session runs 43 security checks — about 25 run automatically, and 18 are guided manual tests where you physically verify the device.',
    targetSelector: '[data-tour="test-runs-table"]',
    position: 'bottom',
  },
  {
    page: '/reports',
    title: 'Generate Reports',
    description: "Select a device and completed session, choose your format (Excel, Word, or PDF), and generate. Reports match Electracom's client format exactly.",
    targetSelector: '[data-tour="report-form"]',
    position: 'bottom',
  },
  {
    page: '/review',
    title: 'QA Review Queue',
    description: 'After testing, a QA lead reviews flagged results. They can override verdicts with justification, then approve or request a retest.',
    targetSelector: '[data-tour="review-list"]',
    position: 'bottom',
  },
  {
    page: '/network-scan',
    title: 'Network Scanning',
    description: 'Scan an entire subnet to discover and test multiple devices at once. Perfect for site surveys and bulk qualification.',
    targetSelector: '[data-tour="scan-config"]',
    position: 'bottom',
  },
  {
    page: '/settings',
    title: 'Settings & Help',
    description: 'Configure your theme, check tool versions, and manage your profile. You can restart this tour anytime from here.',
    targetSelector: '[data-tour="settings-section"]',
    position: 'bottom',
  },
]

const STORAGE_KEY_COMPLETED = 'edq_tour_completed'
const STORAGE_KEY_DISMISSED = 'edq_tour_dismissed'

export function useTourState() {
  const [tourCompleted, setTourCompleted] = useState(() => {
    return localStorage.getItem(STORAGE_KEY_COMPLETED) === 'true'
  })
  const [tourDismissed, setTourDismissed] = useState(() => {
    return localStorage.getItem(STORAGE_KEY_DISMISSED) === 'true'
  })
  const [tourActive, setTourActive] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)

  const startTour = useCallback(() => {
    setCurrentStep(0)
    setTourActive(true)
  }, [])

  const dismissTour = useCallback(() => {
    setTourDismissed(true)
    localStorage.setItem(STORAGE_KEY_DISMISSED, 'true')
  }, [])

  const completeTour = useCallback(() => {
    setTourActive(false)
    setTourCompleted(true)
    setTourDismissed(true)
    localStorage.setItem(STORAGE_KEY_COMPLETED, 'true')
    localStorage.setItem(STORAGE_KEY_DISMISSED, 'true')
  }, [])

  const skipTour = useCallback(() => {
    setTourActive(false)
    setTourDismissed(true)
    localStorage.setItem(STORAGE_KEY_DISMISSED, 'true')
  }, [])

  const restartTour = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY_COMPLETED)
    localStorage.removeItem(STORAGE_KEY_DISMISSED)
    setTourCompleted(false)
    setTourDismissed(false)
    setCurrentStep(0)
    setTourActive(true)
  }, [])

  const showWelcomeBanner = !tourCompleted && !tourDismissed

  return {
    tourActive,
    tourCompleted,
    tourDismissed,
    currentStep,
    setCurrentStep,
    startTour,
    dismissTour,
    completeTour,
    skipTour,
    restartTour,
    showWelcomeBanner,
  }
}

interface SpotlightRect {
  top: number
  left: number
  width: number
  height: number
}

interface TooltipPos {
  top: number
  left: number
}

function getSpotlightRect(el: HTMLElement, padding = 8): SpotlightRect {
  const rect = el.getBoundingClientRect()
  return {
    top: rect.top - padding + window.scrollY,
    left: rect.left - padding + window.scrollX,
    width: rect.width + padding * 2,
    height: rect.height + padding * 2,
  }
}

function getTooltipPosition(
  spotlight: SpotlightRect,
  position: TourStep['position'],
  tooltipW = 340,
  tooltipH = 200,
): TooltipPos {
  const gap = 12
  let top = 0
  let left = 0

  switch (position) {
    case 'bottom':
      top = spotlight.top + spotlight.height + gap
      left = spotlight.left + spotlight.width / 2 - tooltipW / 2
      break
    case 'top':
      top = spotlight.top - tooltipH - gap
      left = spotlight.left + spotlight.width / 2 - tooltipW / 2
      break
    case 'right':
      top = spotlight.top + spotlight.height / 2 - tooltipH / 2
      left = spotlight.left + spotlight.width + gap
      break
    case 'left':
      top = spotlight.top + spotlight.height / 2 - tooltipH / 2
      left = spotlight.left - tooltipW - gap
      break
  }

  const maxLeft = window.innerWidth - tooltipW - 16
  left = Math.max(16, Math.min(left, maxLeft))
  top = Math.max(16, top)

  return { top, left }
}

interface GuidedTourProps {
  isActive: boolean
  currentStep: number
  onNext: () => void
  onPrev: () => void
  onSkip: () => void
  onComplete: () => void
}

export default function GuidedTour({ isActive, currentStep, onNext, onPrev, onSkip, onComplete }: GuidedTourProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const [spotlight, setSpotlight] = useState<SpotlightRect | null>(null)
  const [tooltipPos, setTooltipPos] = useState<TooltipPos>({ top: 0, left: 0 })
  const tooltipRef = useRef<HTMLDivElement>(null)
  const [navigating, setNavigating] = useState(false)

  const step = TOUR_STEPS[currentStep]
  const isLastStep = currentStep === TOUR_STEPS.length - 1
  const isFirstStep = currentStep === 0

  const findAndHighlight = useCallback(() => {
    if (!step) return
    const el = document.querySelector(step.targetSelector) as HTMLElement | null
    if (el) {
      const rect = getSpotlightRect(el)
      setSpotlight(rect)
      const tooltipH = tooltipRef.current?.offsetHeight || 200
      const tooltipW = tooltipRef.current?.offsetWidth || 340
      setTooltipPos(getTooltipPosition(rect, step.position, tooltipW, tooltipH))
      setNavigating(false)
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    } else {
      setSpotlight(null)
      setNavigating(false)
    }
  }, [step])

  useEffect(() => {
    if (!isActive || !step) return

    const currentPath = location.pathname === '/' ? '/' : location.pathname
    const targetPath = step.page

    if (currentPath !== targetPath) {
      setNavigating(true)
      navigate(targetPath)
      return
    }

    const timer = setTimeout(findAndHighlight, 150)
    return () => clearTimeout(timer)
  }, [isActive, currentStep, step, location.pathname, navigate, findAndHighlight])

  useEffect(() => {
    if (!isActive || !navigating) return
    const timer = setTimeout(findAndHighlight, 400)
    return () => clearTimeout(timer)
  }, [isActive, navigating, location.pathname, findAndHighlight])

  useEffect(() => {
    if (!isActive) return
    const handleResize = () => findAndHighlight()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [isActive, findAndHighlight])

  if (!isActive || !step) return null

  return (
    <div className="fixed inset-0 z-[9999]">
      <svg className="absolute inset-0 w-full h-full" style={{ pointerEvents: 'none' }}>
        <defs>
          <mask id="tour-mask">
            <rect x="0" y="0" width="100%" height="100%" fill="white" />
            {spotlight && (
              <rect
                x={spotlight.left}
                y={spotlight.top}
                width={spotlight.width}
                height={spotlight.height}
                rx="8"
                fill="black"
              />
            )}
          </mask>
        </defs>
        <rect
          x="0"
          y="0"
          width="100%"
          height="100%"
          fill="rgba(0,0,0,0.5)"
          mask="url(#tour-mask)"
          style={{ pointerEvents: 'auto' }}
          onClick={onSkip}
        />
      </svg>

      {spotlight && (
        <div
          className="absolute rounded-lg ring-2 ring-brand-500 ring-offset-2"
          style={{
            top: spotlight.top,
            left: spotlight.left,
            width: spotlight.width,
            height: spotlight.height,
            pointerEvents: 'none',
            boxShadow: '0 0 0 4px rgba(30, 64, 175, 0.15)',
          }}
        />
      )}

      <div
        ref={tooltipRef}
        className="absolute bg-white rounded-xl shadow-2xl border border-zinc-200 p-5 w-[340px] animate-fade-in"
        style={{
          top: tooltipPos.top,
          left: tooltipPos.left,
          pointerEvents: 'auto',
        }}
      >
        <button
          onClick={onSkip}
          className="absolute top-3 right-3 p-1 rounded-md hover:bg-zinc-100 transition-colors text-zinc-400 hover:text-zinc-600"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="w-4 h-4 text-brand-500" />
          <span className="text-xs font-semibold text-brand-500 uppercase tracking-wide">
            Step {currentStep + 1} of {TOUR_STEPS.length}
          </span>
        </div>

        <h3 className="text-base font-semibold text-zinc-900 mb-1.5">{step.title}</h3>
        <p className="text-sm text-zinc-600 leading-relaxed mb-4">{step.description}</p>

        <div className="flex items-center justify-between">
          <div className="flex gap-1">
            {TOUR_STEPS.map((_, i) => (
              <div
                key={i}
                className={`w-1.5 h-1.5 rounded-full transition-colors ${
                  i === currentStep ? 'bg-brand-500' : i < currentStep ? 'bg-brand-300' : 'bg-zinc-200'
                }`}
              />
            ))}
          </div>

          <div className="flex items-center gap-2">
            {!isFirstStep && (
              <button
                onClick={onPrev}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-100 rounded-lg transition-colors"
              >
                <ChevronLeft className="w-3 h-3" />
                Back
              </button>
            )}
            {isLastStep ? (
              <button
                onClick={onComplete}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-brand-500 hover:bg-brand-600 rounded-lg transition-colors"
              >
                Finish Tour
              </button>
            ) : (
              <button
                onClick={onNext}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-brand-500 hover:bg-brand-600 rounded-lg transition-colors"
              >
                Next
                <ChevronRight className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
