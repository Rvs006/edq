import { useState, useMemo, useEffect, useCallback, useRef, forwardRef } from 'react'
import { Search, ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { motion } from 'framer-motion'

export interface TestResultItem {
  id: string
  test_id: string
  test_name: string
  tier: 'automatic' | 'guided_manual' | 'auto_na'
  verdict: string | null
  tool?: string | null
  is_essential?: boolean
  comment?: string | null
}

interface TestSidebarProps {
  results: TestResultItem[]
  selectedTestId: string | null
  runningTestId: string | null
  onSelectTest: (id: string) => void
  className?: string
}

const verdictIcons: Record<string, { icon: string; color: string }> = {
  pass: { icon: '\u2705', color: 'text-green-600' },
  fail: { icon: '\u274C', color: 'text-red-600' },
  advisory: { icon: '\u26A0\uFE0F', color: 'text-amber-600' },
  info: { icon: '\u2139\uFE0F', color: 'text-cyan-600' },
  'n/a': { icon: '\u2298', color: 'text-zinc-400' },
  na: { icon: '\u2298', color: 'text-zinc-400' },
  skipped_safe_mode: { icon: '\uD83D\uDD12', color: 'text-zinc-400' },
  skipped_scenario: { icon: '\u26A1', color: 'text-yellow-500' },
  pending: { icon: '\u23F3', color: 'text-blue-400' },
}

type DisplayState = 'waiting' | 'running' | 'done' | 'manual_pending'

function getDisplayState(result: TestResultItem, isRunning: boolean): DisplayState {
  if (isRunning) return 'running'
  if (result.verdict && result.verdict !== 'pending') return 'done'
  if (result.tier === 'guided_manual' && (!result.verdict || result.verdict === 'pending')) return 'manual_pending'
  return 'waiting'
}

function isScenarioSkipped(result: TestResultItem): boolean {
  return (result.verdict === 'na' || result.verdict === 'n/a') &&
    !!(result.comment && (result.comment.startsWith('Skipped') || result.comment.includes('not applicable in')))
}

function getStatusDisplay(result: TestResultItem, isRunning: boolean) {
  if (isRunning) return { icon: null, color: 'text-blue-500', isSpinner: true }
  if (result.verdict && result.verdict !== 'pending') {
    // Scenario-skipped tests get yellow highlight
    if (isScenarioSkipped(result)) {
      return { icon: '\u26A1', color: 'text-yellow-500', isSpinner: false }
    }
    const v = verdictIcons[result.verdict.toLowerCase()] || verdictIcons.pending
    return { icon: v.icon, color: v.color, isSpinner: false }
  }
  if (result.tier === 'guided_manual' && (!result.verdict || result.verdict === 'pending'))
    return { icon: '\uD83D\uDCCB', color: 'text-amber-500', isSpinner: false }
  return { icon: null, color: 'text-zinc-300', isSpinner: false }
}

export default function TestSidebar({
  results,
  selectedTestId,
  runningTestId,
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
    for (const r of results) {
      if (r.tier === 'guided_manual') manual.push(r)
      else auto.push(r)
    }
    return { autoTests: auto, manualTests: manual }
  }, [results])

  const filterTests = (tests: TestResultItem[]) => {
    if (!searchQuery.trim()) return tests
    const q = searchQuery.toLowerCase()
    return tests.filter(
      (t) =>
        t.test_id.toLowerCase().includes(q) ||
        t.test_name.toLowerCase().includes(q) ||
        (t.tool && t.tool.toLowerCase().includes(q))
    )
  }

  const filteredAuto = filterTests(autoTests)
  const filteredManual = filterTests(manualTests)
  const allFiltered = useMemo(() => [...filteredAuto, ...filteredManual], [filteredAuto, filteredManual])

  const completedCount = results.filter((r) => r.verdict && r.verdict !== 'pending').length

  // Auto-scroll to running test
  useEffect(() => {
    if (runningItemRef.current && scrollContainerRef.current) {
      runningItemRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [runningTestId])

  const handleKeyNav = useCallback(
    (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key !== 'j' && e.key !== 'k') return
      e.preventDefault()
      const currentIdx = allFiltered.findIndex((t) => t.id === selectedTestId)
      let nextIdx: number
      if (e.key === 'j') nextIdx = currentIdx < allFiltered.length - 1 ? currentIdx + 1 : 0
      else nextIdx = currentIdx > 0 ? currentIdx - 1 : allFiltered.length - 1
      if (allFiltered[nextIdx]) onSelectTest(allFiltered[nextIdx].id)
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
          <span className="text-xs text-zinc-400 dark:text-slate-500 font-mono">{completedCount}/{results.length}</span>
        </div>

        {/* Overall progress bar */}
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
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter tests..."
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-zinc-50 dark:bg-slate-800 border border-zinc-200 dark:border-slate-600 rounded-md
                       text-zinc-700 dark:text-slate-200 placeholder-zinc-400 dark:placeholder-slate-500
                       focus:outline-hidden focus:ring-1 focus:ring-brand-500/30 focus:border-brand-500"
          />
        </div>
      </div>

      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto">
        <SidebarSection title="Automatic Tests" count={filteredAuto.length} collapsed={autoCollapsed} onToggle={() => setAutoCollapsed(!autoCollapsed)}>
          {filteredAuto.map((t) => (
            <SidebarItem
              key={t.id}
              ref={t.test_id === runningTestId ? runningItemRef : undefined}
              result={t}
              isSelected={t.id === selectedTestId}
              isRunning={t.test_id === runningTestId}
              onClick={() => onSelectTest(t.id)}
            />
          ))}
        </SidebarSection>
        <SidebarSection title="Manual Tests" count={filteredManual.length} collapsed={manualCollapsed} onToggle={() => setManualCollapsed(!manualCollapsed)}>
          {filteredManual.map((t) => (
            <SidebarItem
              key={t.id}
              ref={t.test_id === runningTestId ? runningItemRef : undefined}
              result={t}
              isSelected={t.id === selectedTestId}
              isRunning={t.test_id === runningTestId}
              onClick={() => onSelectTest(t.id)}
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
  result: TestResultItem; isSelected: boolean; isRunning: boolean; onClick: () => void
}>(function SidebarItem({ result, isSelected, isRunning, onClick }, ref) {
  const display = getStatusDisplay(result, isRunning)
  const state = getDisplayState(result, isRunning)

  return (
    <button
      ref={ref}
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 px-3 py-1.5 text-left transition-all group relative
        ${isSelected ? 'bg-brand-50 text-brand-700 dark:bg-brand-950/40 dark:text-brand-300' : ''}
        ${isRunning ? 'bg-blue-50/60 dark:bg-blue-950/30' : ''}
        ${state === 'waiting' && !isSelected ? 'opacity-60' : ''}
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
