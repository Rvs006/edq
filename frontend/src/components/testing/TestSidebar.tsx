import { useState, useMemo, useEffect, useCallback, useRef } from 'react'
import { Search, ChevronDown, ChevronRight, Loader2 } from 'lucide-react'

export interface TestResultItem {
  id: string
  test_number: string
  test_name: string
  tier: 'automatic' | 'guided_manual' | 'auto_na'
  verdict: string | null
  status?: string
  tool_used?: string | null
  essential_pass?: boolean
}

interface TestSidebarProps {
  results: TestResultItem[]
  selectedTestId: string | null
  runningTestNumber: string | null
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
  pending: { icon: '⏳', color: 'text-zinc-400' },
}

function getStatusDisplay(result: TestResultItem, isRunning: boolean) {
  if (isRunning) {
    return { icon: null, color: 'text-blue-500', isSpinner: true }
  }

  if (result.verdict && result.verdict !== 'pending') {
    const v = verdictIcons[result.verdict.toLowerCase()] || verdictIcons.pending
    return { icon: v.icon, color: v.color, isSpinner: false }
  }

  if (result.tier === 'guided_manual' && (!result.verdict || result.verdict === 'pending')) {
    return { icon: '📋', color: 'text-amber-500', isSpinner: false }
  }

  return { icon: '⏳', color: 'text-zinc-400', isSpinner: false }
}

export default function TestSidebar({
  results,
  selectedTestId,
  runningTestNumber,
  onSelectTest,
  className = '',
}: TestSidebarProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [autoCollapsed, setAutoCollapsed] = useState(false)
  const [manualCollapsed, setManualCollapsed] = useState(false)

  const { autoTests, manualTests } = useMemo(() => {
    const auto: TestResultItem[] = []
    const manual: TestResultItem[] = []
    for (const r of results) {
      if (r.tier === 'guided_manual') {
        manual.push(r)
      } else {
        auto.push(r)
      }
    }
    return { autoTests: auto, manualTests: manual }
  }, [results])

  const filterTests = (tests: TestResultItem[]) => {
    if (!searchQuery.trim()) return tests
    const q = searchQuery.toLowerCase()
    return tests.filter(
      (t) =>
        t.test_number.toLowerCase().includes(q) ||
        t.test_name.toLowerCase().includes(q) ||
        (t.tool_used && t.tool_used.toLowerCase().includes(q))
    )
  }

  const filteredAuto = filterTests(autoTests)
  const filteredManual = filterTests(manualTests)
  const allFiltered = useMemo(() => [...filteredAuto, ...filteredManual], [filteredAuto, filteredManual])

  const completedCount = results.filter(
    (r) => r.verdict && r.verdict !== 'pending'
  ).length

  const containerRef = useRef<HTMLDivElement>(null)

  const handleKeyNav = useCallback(
    (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key !== 'j' && e.key !== 'k') return
      e.preventDefault()
      const currentIdx = allFiltered.findIndex((t) => t.id === selectedTestId)
      let nextIdx: number
      if (e.key === 'j') {
        nextIdx = currentIdx < allFiltered.length - 1 ? currentIdx + 1 : 0
      } else {
        nextIdx = currentIdx > 0 ? currentIdx - 1 : allFiltered.length - 1
      }
      if (allFiltered[nextIdx]) {
        onSelectTest(allFiltered[nextIdx].id)
      }
    },
    [allFiltered, selectedTestId, onSelectTest]
  )

  useEffect(() => {
    document.addEventListener('keydown', handleKeyNav)
    return () => document.removeEventListener('keydown', handleKeyNav)
  }, [handleKeyNav])

  return (
    <div ref={containerRef} className={`flex flex-col h-full bg-white dark:bg-dark-card border-r border-zinc-200 dark:border-slate-700/50 ${className}`}>
      <div className="px-3 pt-3 pb-2 border-b border-zinc-100 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
            Tests
          </span>
          <span className="text-xs text-zinc-400 font-mono">
            {completedCount}/{results.length}
          </span>
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter tests..."
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-zinc-50 border border-zinc-200 rounded-md
                       text-zinc-700 placeholder-zinc-400
                       focus:outline-none focus:ring-1 focus:ring-brand-500/30 focus:border-brand-500"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <SidebarSection
          title="Automatic Tests"
          count={filteredAuto.length}
          collapsed={autoCollapsed}
          onToggle={() => setAutoCollapsed(!autoCollapsed)}
        >
          {filteredAuto.map((t) => (
            <SidebarItem
              key={t.id}
              result={t}
              isSelected={t.id === selectedTestId}
              isRunning={t.test_number === runningTestNumber}
              onClick={() => onSelectTest(t.id)}
            />
          ))}
        </SidebarSection>

        <SidebarSection
          title="Manual Tests"
          count={filteredManual.length}
          collapsed={manualCollapsed}
          onToggle={() => setManualCollapsed(!manualCollapsed)}
        >
          {filteredManual.map((t) => (
            <SidebarItem
              key={t.id}
              result={t}
              isSelected={t.id === selectedTestId}
              isRunning={t.test_number === runningTestNumber}
              onClick={() => onSelectTest(t.id)}
            />
          ))}
        </SidebarSection>
      </div>
    </div>
  )
}

function SidebarSection({
  title,
  count,
  collapsed,
  onToggle,
  children,
}: {
  title: string
  count: number
  collapsed: boolean
  onToggle: () => void
  children: React.ReactNode
}) {
  return (
    <div>
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-1.5 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider
                   text-zinc-500 hover:bg-zinc-50 transition-colors"
      >
        {collapsed ? (
          <ChevronRight className="w-3 h-3" />
        ) : (
          <ChevronDown className="w-3 h-3" />
        )}
        {title}
        <span className="ml-auto text-zinc-400 font-mono normal-case">{count}</span>
      </button>
      {!collapsed && <div className="pb-1">{children}</div>}
    </div>
  )
}

function SidebarItem({
  result,
  isSelected,
  isRunning,
  onClick,
}: {
  result: TestResultItem
  isSelected: boolean
  isRunning: boolean
  onClick: () => void
}) {
  const display = getStatusDisplay(result, isRunning)

  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 px-3 py-1.5 text-left transition-colors group relative
        ${isSelected ? 'bg-brand-50 text-brand-700' : 'hover:bg-zinc-50 text-zinc-700'}
        ${isRunning ? 'bg-blue-50/50' : ''}`}
    >
      {isRunning && (
        <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-blue-500 rounded-r animate-pulse" />
      )}
      {isSelected && !isRunning && (
        <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-brand-500 rounded-r" />
      )}

      <span className="flex-shrink-0 w-5 text-center text-sm leading-none">
        {display.isSpinner ? (
          <Loader2 className="w-4 h-4 animate-spin text-blue-500 mx-auto" />
        ) : (
          <span>{display.icon}</span>
        )}
      </span>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] font-mono text-zinc-400 flex-shrink-0">
            {result.test_number}
          </span>
          <span
            className={`text-xs truncate ${
              isSelected ? 'font-medium text-brand-700' : 'text-zinc-700'
            }`}
          >
            {result.test_name}
          </span>
        </div>
      </div>

      {result.essential_pass && (
        <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-red-400" title="Essential pass" />
      )}
    </button>
  )
}
