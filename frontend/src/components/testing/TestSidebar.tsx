import { useState, useMemo, useEffect, useCallback, useRef, forwardRef } from 'react'
import { Search, ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { motion } from 'framer-motion'
import { summarizeRunProgress } from '@/lib/testUi'

export interface TestResultItem {
  id: string
  test_id: string
  test_name: string
  tier: 'automatic' | 'guided_manual' | 'auto_na'
  verdict: string | null
  tool?: string | null
  is_essential?: boolean
  comment?: string | null
  duration_seconds?: number | null
  started_at?: string | null
}

interface TestSidebarProps {
  results: TestResultItem[]
  selectedTestId: string | null
  runningTestId: string | null
  runStatus?: string | null
  onSelectTest: (id: string) => void
  className?: string
}

const verdictIcons: Record<string, { icon: string; color: string }> = {
  pass: { icon: '✅', color: 'text-green-600' },
  fail: { icon: '❌', color: 'text-red-600' },
  advisory: { icon: '⚠️', color: 'text-amber-600' },
  info: { icon: 'ℹ️', color: 'text-cyan-600' },
  'n/a': { icon: '⊘', color: 'text-zinc-400' },
  na: { icon: '⊘', color: 'text-zinc-400' },
  skipped_safe_mode: { icon: '🔒', color: 'text-zinc-400' },
  skipped_scenario: { icon: '⚡', color: 'text-yellow-500' },
  pending: { icon: '⏳', color: 'text-blue-400' },
}

type DisplayState = 'waiting' | 'running' | 'done' | 'manual_pending'

function isManualPending(result: TestResultItem, runStatus?: string | null): boolean {
  if (result.tier !== 'guided_manual') return false
  if (result.verdict && result.verdict !== 'pending') return false
  const normalizedStatus = (runStatus || '').toLowerCase()
  return normalizedStatus === 'awaiting_manual' || normalizedStatus === 'awaiting_review'
}

function getDisplayState(result: TestResultItem, isRunning: boolean, runStatus?: string | null): DisplayState {
  if (isRunning) return 'running'
  if (result.verdict && result.verdict !== 'pending') return 'done'
  if (isManualPending(result, runStatus)) return 'manual_pending'
  return 'waiting'
}

function isScenarioSkipped(result: TestResultItem): boolean {
  return (result.verdict === 'na' || result.verdict === 'n/a') &&
    !!(result.comment && (result.comment.startsWith('Skipped') || result.comment.includes('not applicable in')))
}

function getStatusDisplay(result: TestResultItem, isRunning: boolean, runStatus?: string | null) {
  if (isRunning) return { icon: null, color: 'text-blue-500', isSpinner: true }
  if (result.verdict && result.verdict !== 'pending') {
    if (isScenarioSkipped(result)) {
      return { icon: '⚡', color: 'text-yellow-500', isSpinner: false }
    }
    const value = verdictIcons[result.verdict.toLowerCase()] || verdictIcons.pending
    return { icon: value.icon, color: value.color, isSpinner: false }
  }
  if (isManualPending(result, runStatus)) {
    return { icon: '📋', color: 'text-amber-500', isSpinner: false }
  }
  return { icon: null, color: 'text-zinc-300', isSpinner: false }
}

export default function TestSidebar({
  results,
  selectedTestId,
  runningTestId,
  runStatus,
  onSelectTest,
  className = '',
}: TestSidebarProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [autoCollapsed, setAutoCollapsed] = useState(false)
  const [manualCollapsed, setManualCollapsed] = useState(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const runningItemRef = useRef<HTMLButtonElement>(null)

  const { autoTests, manualTests } = useMemo(() => {
    const auto: TestResultItem[] = []
    const manual: TestResultItem[] = []
    for (const result of results) {
      if (result.tier === 'guided_manual') manual.push(result)
      else auto.push(result)
    }
    return { autoTests: auto, manualTests: manual }
  }, [results])

  const filterTests = (tests: TestResultItem[]) => {
    if (!searchQuery.trim()) return tests
    const query = searchQuery.toLowerCase()
    return tests.filter(
      (test) =>
        test.test_id.toLowerCase().includes(query) ||
        test.test_name.toLowerCase().includes(query) ||
        (test.tool && test.tool.toLowerCase().includes(query))
    )
  }

  const filteredAuto = filterTests(autoTests)
  const filteredManual = filterTests(manualTests)
  const allFiltered = useMemo(() => [...filteredAuto, ...filteredManual], [filteredAuto, filteredManual])

  const { completed: completedCount, progressLabel, detailText } = useMemo(
    () => summarizeRunProgress(results, runningTestId, runStatus),
    [results, runningTestId, runStatus]
  )

  const queuePositions = useMemo(() => {
    const positions: Record<string, number> = {}
    const autoWaiting = autoTests.filter(test => !test.verdict || test.verdict === 'pending')
    const runningIndex = runningTestId ? autoWaiting.findIndex(test => test.test_id === runningTestId) : -1
    let position = 1
    for (let index = 0; index < autoWaiting.length; index++) {
      if (autoWaiting[index].test_id === runningTestId) continue
      if (runningIndex >= 0 && index < runningIndex) continue
      positions[autoWaiting[index].test_id] = position++
    }
    return positions
  }, [autoTests, runningTestId])

  useEffect(() => {
    if (
      runningItemRef.current
      && scrollContainerRef.current
      && typeof runningItemRef.current.scrollIntoView === 'function'
    ) {
      runningItemRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [runningTestId])

  const handleKeyNav = useCallback(
    (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
      if (event.key !== 'j' && event.key !== 'k') return
      event.preventDefault()
      const currentIndex = allFiltered.findIndex((test) => test.id === selectedTestId)
      const nextIndex =
        event.key === 'j'
          ? currentIndex < allFiltered.length - 1 ? currentIndex + 1 : 0
          : currentIndex > 0 ? currentIndex - 1 : allFiltered.length - 1
      if (allFiltered[nextIndex]) onSelectTest(allFiltered[nextIndex].id)
    },
    [allFiltered, selectedTestId, onSelectTest]
  )

  useEffect(() => {
    document.addEventListener('keydown', handleKeyNav)
    return () => document.removeEventListener('keydown', handleKeyNav)
  }, [handleKeyNav])

  const progressPct = results.length > 0 ? Math.round((completedCount / results.length) * 100) : 0

  return (
    <div className={`flex flex-col h-full bg-white dark:bg-dark-card border-r border-zinc-200 dark:border-slate-700/50 ${className}`}>
      <div className="px-3 pt-3 pb-2 border-b border-zinc-100 dark:border-slate-700/50 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-zinc-500 dark:text-slate-400 uppercase tracking-wider">Tests</span>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-blue-600 dark:text-blue-300 font-medium">{progressLabel}</span>
            <span className="text-xs text-zinc-400 dark:text-slate-500 font-mono">{completedCount}/{results.length}</span>
          </div>
        </div>

        <div className="w-full h-1.5 bg-zinc-100 dark:bg-slate-700 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-brand-500 to-blue-500 rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${progressPct}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>

        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Filter tests..."
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-zinc-50 dark:bg-slate-800 border border-zinc-200 dark:border-slate-600 rounded-md
                       text-zinc-700 dark:text-slate-200 placeholder-zinc-400 dark:placeholder-slate-500
                       focus:outline-hidden focus:ring-1 focus:ring-brand-500/30 focus:border-brand-500"
          />
        </div>

        <p className="text-[10px] text-zinc-400 dark:text-slate-500">{detailText}</p>
      </div>

      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto">
        <SidebarSection title="Automatic Tests" count={filteredAuto.length} collapsed={autoCollapsed} onToggle={() => setAutoCollapsed(!autoCollapsed)}>
          {filteredAuto.map((test) => (
            <SidebarItem
              key={test.id}
              ref={test.test_id === runningTestId ? runningItemRef : undefined}
              result={test}
              isSelected={test.id === selectedTestId}
              isRunning={test.test_id === runningTestId}
              runStatus={runStatus}
              queuePosition={queuePositions[test.test_id] || null}
              onClick={() => onSelectTest(test.id)}
            />
          ))}
        </SidebarSection>
        <SidebarSection title="Manual Tests" count={filteredManual.length} collapsed={manualCollapsed} onToggle={() => setManualCollapsed(!manualCollapsed)}>
          {filteredManual.map((test) => (
            <SidebarItem
              key={test.id}
              ref={test.test_id === runningTestId ? runningItemRef : undefined}
              result={test}
              isSelected={test.id === selectedTestId}
              isRunning={test.test_id === runningTestId}
              runStatus={runStatus}
              queuePosition={null}
              onClick={() => onSelectTest(test.id)}
            />
          ))}
        </SidebarSection>
      </div>
    </div>
  )
}

function SidebarSection({ title, count, collapsed, onToggle, children }: {
  title: string; count: number; collapsed: boolean; onToggle: () => void; children: React.ReactNode
}) {
  return (
    <div>
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-1.5 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider
                   text-zinc-500 dark:text-slate-400 hover:bg-zinc-50 dark:hover:bg-slate-700/40 transition-colors"
      >
        {collapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        {title}
        <span className="ml-auto text-zinc-400 font-mono normal-case">{count}</span>
      </button>
      {!collapsed && <div className="pb-1">{children}</div>}
    </div>
  )
}

const SidebarItem = forwardRef<HTMLButtonElement, {
  result: TestResultItem; isSelected: boolean; isRunning: boolean; runStatus?: string | null; queuePosition: number | null; onClick: () => void
}>(function SidebarItem({ result, isRunning, isSelected, runStatus, queuePosition, onClick }, ref) {
  const display = getStatusDisplay(result, isRunning, runStatus)
  const state = getDisplayState(result, isRunning, runStatus)
  const hoverText = [
    `${result.test_id} - ${result.test_name}`,
    result.tool ? `Tool: ${result.tool}` : '',
    result.tier === 'guided_manual' ? 'Manual test' : 'Automatic test',
  ].filter(Boolean).join(' | ')

  return (
    <button
      ref={ref}
      onClick={onClick}
      title={hoverText}
      aria-label={hoverText}
      className={`w-full flex items-center gap-2.5 px-3 py-1.5 text-left transition-all group relative
        ${isSelected ? 'bg-brand-50 text-brand-700 dark:bg-brand-950/40 dark:text-brand-300' : ''}
        ${isRunning ? 'bg-blue-50/60 dark:bg-blue-950/30' : ''}
        ${state === 'waiting' && !isSelected ? 'opacity-50' : ''}
        ${state !== 'waiting' || isSelected ? 'hover:bg-zinc-50 dark:hover:bg-slate-700/40' : 'hover:opacity-60'}
        text-zinc-700 dark:text-slate-200`}
    >
      {isRunning && <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-blue-500 rounded-r animate-pulse" />}
      {isSelected && !isRunning && <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-brand-500 rounded-r" />}

      <span className="flex-shrink-0 w-5 text-center text-sm leading-none">
        {display.isSpinner ? (
          <Loader2 className="w-4 h-4 animate-spin text-blue-500 mx-auto" />
        ) : display.icon ? (
          <span>{display.icon}</span>
        ) : (
          <span className="block w-2 h-2 rounded-full bg-zinc-200 dark:bg-slate-600 mx-auto" />
        )}
      </span>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] font-mono text-zinc-400 dark:text-slate-500 flex-shrink-0">{result.test_id}</span>
          <span className={`text-xs truncate ${isSelected ? 'font-medium text-brand-700 dark:text-brand-300' : ''}`}>
            {result.test_name}
          </span>
        </div>
        {isRunning && (
          <div className="mt-1 h-1 w-full bg-blue-100 dark:bg-blue-900/50 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-blue-500 rounded-full"
              initial={{ width: '10%' }}
              animate={{ width: ['10%', '70%', '90%'] }}
              transition={{ duration: 8, repeat: Infinity, ease: 'easeInOut' }}
            />
          </div>
        )}
      </div>

      {result.is_essential && (
        <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-red-400" title="Essential pass" />
      )}
    </button>
  )
})
