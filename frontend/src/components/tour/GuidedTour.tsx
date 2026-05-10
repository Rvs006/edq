import { useState, useEffect, useCallback } from 'react'
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
    description: 'Each test session runs 48 active EDQ tests — 19 automated plus 29 guided manual checks where you physically verify the device and capture extra evidence.',
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

interface ViewportRect {
  top: number
  left: number
  width: number
  height: number
}

interface TooltipPlacement {
  x: number
  y: number
  width: number
  height: number
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
  const [spotlight, setSpotlight] = useState<ViewportRect | null>(null)
  const [navigating, setNavigating] = useState(false)

  const step = TOUR_STEPS[currentStep]
  const isLastStep = currentStep === TOUR_STEPS.length - 1
  const isFirstStep = currentStep === 0

  const findAndHighlight = useCallback(() => {
    if (!step) return
    const el = document.querySelector(step.targetSelector) as HTMLElement | null
    if (el) {
      // Scroll element into view first
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      // After scroll settles, get viewport-relative rect
      requestAnimationFrame(() => {
        const padding = 8
        const rect = el.getBoundingClientRect()
        setSpotlight({
          top: rect.top - padding,
          left: rect.left - padding,
          width: rect.width + padding * 2,
          height: rect.height + padding * 2,
        })
      })
      setNavigating(false)
    } else {
      setSpotlight(null)
      setNavigating(false)
    }
  }, [step])

  // Navigate to the correct page and find the target
  useEffect(() => {
    if (!isActive || !step) return
    const currentPath = location.pathname === '/' ? '/' : location.pathname
    if (currentPath !== step.page) {
      setNavigating(true)
      navigate(step.page)
      return
    }
    const timer = setTimeout(findAndHighlight, 200)
    return () => clearTimeout(timer)
  }, [isActive, currentStep, step, location.pathname, navigate, findAndHighlight])

  // Retry after navigation
  useEffect(() => {
    if (!isActive || !navigating) return
    const timer = setTimeout(findAndHighlight, 500)
    return () => clearTimeout(timer)
  }, [isActive, navigating, location.pathname, findAndHighlight])

  // Recalculate on resize / scroll
  useEffect(() => {
    if (!isActive) return
    const handler = () => findAndHighlight()
    window.addEventListener('resize', handler)
    window.addEventListener('scroll', handler, true)
    return () => {
      window.removeEventListener('resize', handler)
      window.removeEventListener('scroll', handler, true)
    }
  }, [isActive, findAndHighlight])

  if (!isActive || !step) return null

  const tooltipPlacement = getTooltipPlacement(spotlight, step.position)

  return (
    <div className="fixed inset-0 z-[9999] pointer-events-none">
      {/* Dark overlay with spotlight cutout using clip-path */}
      <svg
        aria-hidden="true"
        className="absolute inset-0 h-full w-full pointer-events-auto"
        onClick={() => { onSkip(); navigate('/') }}
      >
        <defs>
          <mask id="guided-tour-spotlight-mask">
            <rect x="0" y="0" width="100%" height="100%" fill="white" />
            {spotlight && (
              <rect
                x={spotlight.left}
                y={spotlight.top}
                width={spotlight.width}
                height={spotlight.height}
                rx="8"
                ry="8"
                fill="black"
              />
            )}
          </mask>
        </defs>
        <rect width="100%" height="100%" fill="black" opacity="0.5" mask="url(#guided-tour-spotlight-mask)" />
      </svg>

      {/* Spotlight ring */}
      {spotlight && (
        <svg aria-hidden="true" className="fixed inset-0 h-full w-full pointer-events-none">
          <rect
            x={spotlight.left}
            y={spotlight.top}
            width={spotlight.width}
            height={spotlight.height}
            rx="8"
            ry="8"
            fill="none"
            stroke="rgb(30 64 175)"
            strokeOpacity="0.15"
            strokeWidth="10"
          />
          <rect
            x={spotlight.left}
            y={spotlight.top}
            width={spotlight.width}
            height={spotlight.height}
            rx="8"
            ry="8"
            fill="none"
            stroke="rgb(59 130 246)"
            strokeWidth="2"
          />
        </svg>
      )}

      {/* Tooltip card */}
      <svg className="fixed inset-0 h-full w-full overflow-visible pointer-events-none">
        <foreignObject
          x={tooltipPlacement.x}
          y={tooltipPlacement.y}
          width={tooltipPlacement.width}
          height={tooltipPlacement.height}
          className="overflow-visible pointer-events-auto"
        >
          <div className="bg-white dark:bg-dark-card rounded-xl shadow-2xl border border-zinc-200 dark:border-slate-700/50 p-5 w-full animate-fade-in">
            {/* Header row: step counter + exit */}
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-brand-500" />
                <span className="text-xs font-semibold text-brand-500 uppercase tracking-wide">
                  Step {currentStep + 1} of {TOUR_STEPS.length}
                </span>
              </div>
              <button
                onClick={() => { onSkip(); navigate('/') }}
                className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-slate-300 transition-colors"
              >
                <X className="w-3.5 h-3.5" />
                Exit tour
              </button>
            </div>

            <h3 className="text-base font-semibold text-zinc-900 dark:text-slate-100 mb-1.5">{step.title}</h3>
            <p className="text-sm text-zinc-600 dark:text-slate-400 leading-relaxed mb-4">{step.description}</p>

            {/* Footer: dots + nav buttons */}
            <div className="flex items-center justify-between">
              <div className="flex gap-1.5">
                {TOUR_STEPS.map((_, i) => (
                  <div
                    key={i}
                    className={`w-2 h-2 rounded-full transition-colors ${
                      i === currentStep ? 'bg-brand-500' : i < currentStep ? 'bg-brand-300' : 'bg-zinc-200 dark:bg-slate-700'
                    }`}
                  />
                ))}
              </div>

              <div className="flex items-center gap-2">
                {!isFirstStep && (
                  <button
                    onClick={onPrev}
                    className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-zinc-600 dark:text-slate-400 hover:bg-zinc-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
                  >
                    <ChevronLeft className="w-3 h-3" />
                    Back
                  </button>
                )}
                {isLastStep ? (
                  <button
                    onClick={() => { onComplete(); navigate('/') }}
                    className="inline-flex items-center gap-1 px-4 py-1.5 text-xs font-medium text-white bg-brand-500 hover:bg-brand-600 rounded-lg transition-colors"
                  >
                    Finish Tour
                  </button>
                ) : (
                  <button
                    onClick={onNext}
                    className="inline-flex items-center gap-1 px-4 py-1.5 text-xs font-medium text-white bg-brand-500 hover:bg-brand-600 rounded-lg transition-colors"
                  >
                    Next
                    <ChevronRight className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </foreignObject>
      </svg>
    </div>
  )
}

function getTooltipPlacement(
  spotlight: ViewportRect | null,
  position: TourStep['position'],
): TooltipPlacement {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const gap = 14
  const width = Math.min(360, Math.max(280, vw - 32))
  const height = 320
  const maxX = Math.max(16, vw - width - 16)
  const maxY = Math.max(16, vh - height - 16)
  let x = (vw - width) / 2
  let y = (vh - height) / 2

  if (spotlight) {
    switch (position) {
      case 'bottom':
        y = spotlight.top + spotlight.height + gap
        x = spotlight.left + spotlight.width / 2 - width / 2
        break
      case 'top':
        y = spotlight.top - gap - height
        x = spotlight.left + spotlight.width / 2 - width / 2
        break
      case 'right':
        y = spotlight.top + spotlight.height / 2 - height / 2
        x = spotlight.left + spotlight.width + gap
        break
      case 'left':
        y = spotlight.top + spotlight.height / 2 - height / 2
        x = spotlight.left - width - gap
        break
    }
  }

  return {
    x: Math.round(Math.max(16, Math.min(x, maxX))),
    y: Math.round(Math.max(16, Math.min(y, maxY))),
    width: Math.round(width),
    height,
  }
}
