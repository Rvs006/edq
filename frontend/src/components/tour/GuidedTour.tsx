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

interface ViewportRect {
  top: number
  left: number
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
  const tooltipRef = useRef<HTMLDivElement>(null)
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

  // Compute tooltip position relative to viewport
  const tooltipW = 360
  const gap = 14
  let tooltipStyle: React.CSSProperties = { pointerEvents: 'auto' }

  if (spotlight) {
    const vw = window.innerWidth
    const vh = window.innerHeight
    let top = 0
    let left = 0

    switch (step.position) {
      case 'bottom':
        top = spotlight.top + spotlight.height + gap
        left = spotlight.left + spotlight.width / 2 - tooltipW / 2
        break
      case 'top':
        top = spotlight.top - gap
        left = spotlight.left + spotlight.width / 2 - tooltipW / 2
        break
      case 'right':
        top = spotlight.top + spotlight.height / 2 - 100
        left = spotlight.left + spotlight.width + gap
        break
      case 'left':
        top = spotlight.top + spotlight.height / 2 - 100
        left = spotlight.left - tooltipW - gap
        break
    }

    // Clamp to viewport
    left = Math.max(16, Math.min(left, vw - tooltipW - 16))
    top = Math.max(16, Math.min(top, vh - 260))

    // If tooltip overlaps spotlight on 'top', use transform to sit above
    if (step.position === 'top') {
      tooltipStyle = { ...tooltipStyle, bottom: vh - spotlight.top + gap, left, position: 'fixed' }
    } else {
      tooltipStyle = { ...tooltipStyle, top, left, position: 'fixed' }
    }
  } else {
    // No target found — center the tooltip
    tooltipStyle = {
      ...tooltipStyle,
      top: '50%',
      left: '50%',
      transform: 'translate(-50%, -50%)',
      position: 'fixed',
    }
  }

  return (
    <div className="fixed inset-0 z-[9999]" style={{ pointerEvents: 'none' }}>
      {/* Dark overlay with spotlight cutout using clip-path */}
      <div
        className="absolute inset-0 bg-black/50"
        style={{
          pointerEvents: 'auto',
          clipPath: spotlight
            ? `polygon(
                0% 0%, 0% 100%, 100% 100%, 100% 0%, 0% 0%,
                ${spotlight.left}px ${spotlight.top}px,
                ${spotlight.left}px ${spotlight.top + spotlight.height}px,
                ${spotlight.left + spotlight.width}px ${spotlight.top + spotlight.height}px,
                ${spotlight.left + spotlight.width}px ${spotlight.top}px,
                ${spotlight.left}px ${spotlight.top}px
              )`
            : undefined,
        }}
        onClick={onSkip}
      />

      {/* Spotlight ring */}
      {spotlight && (
        <div
          className="fixed rounded-lg ring-2 ring-brand-500"
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

      {/* Tooltip card */}
      <div
        ref={tooltipRef}
        className="bg-white dark:bg-dark-card rounded-xl shadow-2xl border border-zinc-200 dark:border-slate-700/50 p-5 w-[360px] animate-fade-in"
        style={tooltipStyle}
      >
        {/* Header row: step counter + exit */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-brand-500" />
            <span className="text-xs font-semibold text-brand-500 uppercase tracking-wide">
              Step {currentStep + 1} of {TOUR_STEPS.length}
            </span>
          </div>
          <button
            onClick={onSkip}
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
                onClick={onComplete}
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
    </div>
  )
}
