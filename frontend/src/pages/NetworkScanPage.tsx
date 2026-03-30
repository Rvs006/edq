import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Network, Search, Play, CheckCircle2, XCircle, AlertTriangle,
  Loader2, ChevronRight, ChevronDown, RotateCcw, Wifi, WifiOff,
  Info, ArrowRight, Shield, Monitor, Server, LayoutGrid, List
} from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { networkScanApi, templatesApi, authorizedNetworksApi } from '@/lib/api'
import { UNIVERSAL_TESTS, TEST_CATEGORIES } from '@/lib/universal-tests'
import toast from 'react-hot-toast'

const SCENARIO_PRESELECTS: Record<string, string[]> = {
  test_lab: ['U01', 'U02', 'U06', 'U07', 'U08', 'U09', 'U10', 'U11', 'U12', 'U15', 'U16', 'U19', 'U34'],
  direct: ['U01', 'U06', 'U08', 'U10', 'U16'],
  site_network: ['U01', 'U02', 'U06', 'U08'],
}

const SCENARIOS = [
  { value: 'test_lab', label: 'Test Lab', desc: 'Isolated test environment — full scan safe' },
  { value: 'direct', label: 'Direct Connection', desc: 'Point-to-point with device — most scans safe' },
  { value: 'site_network', label: 'Site Network', desc: 'Production network — limited scans recommended', warn: true },
]

type Step = 'configure' | 'review' | 'monitor' | 'results'

interface DiscoveredDevice {
  ip: string
  mac: string | null
  vendor: string | null
  hostname: string | null
  services?: string[]
  open_ports?: number[]
  os?: string | null
  model?: string | null
  http_server?: string | null
}

type DeviceViewMode = 'grid' | 'tree'

interface ScanResult {
  run_id: string
  device_ip: string
  device_id: string
  vendor: string | null
  hostname: string | null
  status: string
  progress_pct: number
  total_tests: number
  completed_tests: number
  passed_tests: number
  failed_tests: number
  advisory_tests: number
  overall_verdict: string | null
}

export default function NetworkScanPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState<Step>('configure')
  const [cidr, setCidr] = useState('192.168.1.0/24')
  const [scenario, setScenario] = useState('test_lab')
  const [selectedTests, setSelectedTests] = useState<Set<string>>(new Set(SCENARIO_PRESELECTS.test_lab))
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(['Network']))
  const [discovering, setDiscovering] = useState(false)
  const [scanId, setScanId] = useState<string | null>(null)
  const [devices, setDevices] = useState<DiscoveredDevice[]>([])
  const [selectedDevices, setSelectedDevices] = useState<Set<string>>(new Set())
  const [starting, setStarting] = useState(false)
  const [results, setResults] = useState<ScanResult[]>([])
  const [scanStatus, setScanStatus] = useState<string>('pending')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [authorizedNets, setAuthorizedNets] = useState<{ cidr: string; label: string | null }[]>([])
  const [authNetsLoaded, setAuthNetsLoaded] = useState(false)

  useEffect(() => {
    authorizedNetworksApi.list({ active_only: true }).then(res => {
      setAuthorizedNets(res.data.map((n: { cidr: string; label: string | null }) => ({ cidr: n.cidr, label: n.label })))
      setAuthNetsLoaded(true)
    }).catch(() => setAuthNetsLoaded(true))
  }, [])

  const cidrValid = /^(\d{1,3}\.){3}\d{1,3}\/\d{1,2}$/.test(cidr)
  const cidrPrefix = cidr.split('/')[1] ? parseInt(cidr.split('/')[1]) : 0
  const hostCount = cidrValid && cidrPrefix >= 16 && cidrPrefix <= 30
    ? Math.pow(2, 32 - cidrPrefix) - 2
    : 0

  useEffect(() => {
    const preselected = SCENARIO_PRESELECTS[scenario] || []
    setSelectedTests(new Set(preselected))
  }, [scenario])

  const toggleTest = (id: string) => {
    setSelectedTests(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleCategory = (cat: string) => {
    const catTests = UNIVERSAL_TESTS.filter(t => t.category === cat)
    const allSelected = catTests.every(t => selectedTests.has(t.id))
    setSelectedTests(prev => {
      const next = new Set(prev)
      catTests.forEach(t => allSelected ? next.delete(t.id) : next.add(t.id))
      return next
    })
  }

  const handleDiscover = async () => {
    if (!cidrValid) return
    setDiscovering(true)
    try {
      const res = await networkScanApi.discover({
        cidr,
        connection_scenario: scenario,
        test_ids: Array.from(selectedTests),
      })
      const scan = res.data
      setScanId(scan.id)
      const found: DiscoveredDevice[] = scan.devices_found || []
      setDevices(found)
      setSelectedDevices(new Set(found.map((d: DiscoveredDevice) => d.ip)))
      setStep('review')
      if (found.length === 0) toast('No devices found on this subnet', { icon: '📡' })
      else toast.success(`Discovered ${found.length} device(s)`)
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      toast.error(error.response?.data?.detail || 'Discovery failed')
    } finally {
      setDiscovering(false)
    }
  }

  const handleStartScan = async () => {
    if (!scanId || selectedDevices.size === 0) return
    setStarting(true)
    try {
      const res = await networkScanApi.start({
        scan_id: scanId,
        device_ips: Array.from(selectedDevices),
        test_ids: Array.from(selectedTests),
        connection_scenario: scenario,
      })
      setScanStatus(res.data.status)
      setStep('monitor')
      toast.success('Batch scan started')
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      toast.error(error.response?.data?.detail || 'Failed to start batch scan')
    } finally {
      setStarting(false)
    }
  }

  useEffect(() => {
    if (step !== 'monitor' || !scanId) return
    const poll = async () => {
      try {
        const res = await networkScanApi.results(scanId)
        setResults(res.data.results || [])
        setScanStatus(res.data.status)
        if (res.data.status === 'complete' || res.data.status === 'error') {
          if (pollRef.current) clearInterval(pollRef.current)
          setStep('results')
        }
      } catch { /* ignore */ }
    }
    poll()
    pollRef.current = setInterval(poll, 3000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [step, scanId])

  useEffect(() => {
    if (step !== 'results' || !scanId) return
    const fetchFinal = async () => {
      try {
        const res = await networkScanApi.results(scanId)
        setResults(res.data.results || [])
      } catch { /* ignore */ }
    }
    fetchFinal()
  }, [step, scanId])

  return (
    <div className="page-container" data-tour="scan-config">
      <div className="mb-5">
        <h1 className="section-title">Network Scan</h1>
        <p className="section-subtitle">Discover and batch-test devices across a subnet</p>
      </div>

      <StepIndicator current={step} />

      {authNetsLoaded && authorizedNets.length === 0 && (
        <div className="mb-4 p-4 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-amber-800 dark:text-amber-200">No authorized networks configured</p>
            <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
              Scanning is blocked until an admin authorizes scan ranges.{' '}
              <a href="/authorized-networks" className="underline font-medium hover:text-amber-800 dark:hover:text-amber-200">
                Go to Authorized Networks →
              </a>
            </p>
          </div>
        </div>
      )}

      {authNetsLoaded && authorizedNets.length > 0 && step === 'configure' && (
        <div className="mb-4 p-3 bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800/50 rounded-xl flex items-center gap-2">
          <Shield className="w-4 h-4 text-emerald-500 shrink-0" />
          <p className="text-xs text-emerald-700 dark:text-emerald-300">
            <strong>Authorized ranges:</strong>{' '}
            {authorizedNets.map(n => n.label ? `${n.cidr} (${n.label})` : n.cidr).join(', ')}
          </p>
        </div>
      )}

      {step === 'configure' && !discovering && (
        <ConfigureStep
          cidr={cidr} setCidr={setCidr} cidrValid={cidrValid} hostCount={hostCount}
          scenario={scenario} setScenario={setScenario}
          selectedTests={selectedTests} setSelectedTests={setSelectedTests} toggleTest={toggleTest} toggleCategory={toggleCategory}
          expandedCategories={expandedCategories} setExpandedCategories={setExpandedCategories}
          discovering={discovering} onDiscover={handleDiscover}
        />
      )}
      {step === 'configure' && discovering && (
        <ScanAnimation cidr={cidr} />
      )}
      {step === 'review' && (
        <ReviewStep
          devices={devices} selectedDevices={selectedDevices} setSelectedDevices={setSelectedDevices}
          starting={starting} onStart={handleStartScan} onBack={() => setStep('configure')}
          testCount={selectedTests.size}
        />
      )}
      {step === 'monitor' && (
        <MonitorStep results={results} scanStatus={scanStatus} navigate={navigate} onNewScan={() => {
          if (pollRef.current) clearInterval(pollRef.current)
          setStep('configure')
          setScanId(null)
          setDevices([])
          setResults([])
          setScanStatus('pending')
        }} />
      )}
      {step === 'results' && (
        <ResultsStep results={results} navigate={navigate} onReset={() => {
          setStep('configure')
          setScanId(null)
          setDevices([])
          setResults([])
        }} />
      )}
    </div>
  )
}

function StepIndicator({ current }: { current: Step }) {
  const steps: { key: Step; label: string }[] = [
    { key: 'configure', label: 'Configure' },
    { key: 'review', label: 'Review Devices' },
    { key: 'monitor', label: 'Scanning' },
    { key: 'results', label: 'Results' },
  ]
  const idx = steps.findIndex(s => s.key === current)

  return (
    <div className="flex items-center gap-2 mb-6 overflow-x-auto pb-1">
      {steps.map((s, i) => (
        <div key={s.key} className="flex items-center gap-2">
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${
            i < idx ? 'bg-emerald-50 text-emerald-600 border border-emerald-200' :
            i === idx ? 'bg-brand-50 text-brand-600 border border-brand-200' :
            'bg-zinc-100 dark:bg-slate-800 text-zinc-400 border border-zinc-200 dark:border-slate-700/50'
          }`}>
            {i < idx ? <CheckCircle2 className="w-3.5 h-3.5" /> :
             <span className="w-4 h-4 rounded-full bg-current opacity-20 flex items-center justify-center text-[10px]">{i + 1}</span>}
            {s.label}
          </div>
          {i < steps.length - 1 && <ArrowRight className="w-3.5 h-3.5 text-zinc-300 shrink-0" />}
        </div>
      ))}
    </div>
  )
}

function ConfigureStep({
  cidr, setCidr, cidrValid, hostCount,
  scenario, setScenario,
  selectedTests, setSelectedTests, toggleTest, toggleCategory,
  expandedCategories, setExpandedCategories,
  discovering, onDiscover,
}: {
  cidr: string; setCidr: (v: string) => void; cidrValid: boolean; hostCount: number
  scenario: string; setScenario: (v: string) => void
  selectedTests: Set<string>; setSelectedTests: (v: Set<string>) => void; toggleTest: (id: string) => void; toggleCategory: (cat: string) => void
  expandedCategories: Set<string>; setExpandedCategories: (v: Set<string>) => void
  discovering: boolean; onDiscover: () => void
}) {
  return (
    <div className="space-y-4">
      <div className="card p-5">
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-slate-100 mb-3">Target Subnet</h3>
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1">
            <label className="label">CIDR Range</label>
            <input
              type="text"
              value={cidr}
              onChange={e => setCidr(e.target.value)}
              placeholder="192.168.1.0/24"
              className={`input ${cidr && !cidrValid ? 'border-red-300 focus:border-red-400' : ''}`}
            />
            {cidr && !cidrValid && <p className="text-xs text-red-500 mt-1">Invalid CIDR format</p>}
          </div>
          <div className="sm:w-48">
            <label className="label">Hosts in range</label>
            <div className="input bg-zinc-50 dark:bg-slate-800 text-zinc-600 dark:text-slate-400">{hostCount > 0 ? `~${hostCount} hosts` : '—'}</div>
          </div>
        </div>
      </div>

      <div className="card p-5">
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-slate-100 mb-3">Connection Scenario</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {SCENARIOS.map(s => (
            <button
              key={s.value}
              onClick={() => setScenario(s.value)}
              className={`text-left p-3 rounded-lg border transition-colors ${
                scenario === s.value
                  ? 'border-brand-500 bg-brand-50'
                  : 'border-zinc-200 dark:border-slate-700/50 hover:border-zinc-300 dark:hover:border-slate-600'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                {s.warn ? <AlertTriangle className="w-4 h-4 text-amber-500" /> : <Shield className="w-4 h-4 text-brand-500" />}
                <span className="text-sm font-medium text-zinc-800 dark:text-slate-200">{s.label}</span>
              </div>
              <p className="text-xs text-zinc-500">{s.desc}</p>
            </button>
          ))}
        </div>
        {scenario === 'site_network' && (
          <div className="mt-3 p-2.5 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
            <p className="text-xs text-amber-700">Site network mode uses conservative scan settings to minimise disruption. Some tests are not recommended.</p>
          </div>
        )}
      </div>

      <div className="card p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-slate-100">Test Selection</h3>
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-500">{selectedTests.size}/{UNIVERSAL_TESTS.length} selected</span>
            <button
              onClick={() => setSelectedTests(new Set(UNIVERSAL_TESTS.map(t => t.id)))}
              className="text-xs text-brand-500 hover:text-brand-600 font-medium"
            >Select All</button>
            <button
              onClick={() => setSelectedTests(new Set())}
              className="text-xs text-zinc-500 hover:text-zinc-600 font-medium"
            >Clear</button>
          </div>
        </div>

        <div className="space-y-1">
          {TEST_CATEGORIES.map(cat => {
            const catTests = UNIVERSAL_TESTS.filter(t => t.category === cat)
            const allSelected = catTests.every(t => selectedTests.has(t.id))
            const someSelected = catTests.some(t => selectedTests.has(t.id))
            const expanded = expandedCategories.has(cat)
            return (
              <div key={cat} className="border border-zinc-200 dark:border-slate-700/50 rounded-lg overflow-hidden">
                <button
                  onClick={() => {
                    const next = new Set(expandedCategories)
                    expanded ? next.delete(cat) : next.add(cat)
                    setExpandedCategories(next)
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 bg-zinc-50 dark:bg-slate-800 hover:bg-zinc-100 dark:hover:bg-slate-700 transition-colors"
                >
                  {expanded ? <ChevronDown className="w-4 h-4 text-zinc-400" /> : <ChevronRight className="w-4 h-4 text-zinc-400" />}
                  <span className="text-sm font-medium text-zinc-700 dark:text-slate-300 flex-1 text-left">{cat}</span>
                  <span className="text-xs text-zinc-400">{catTests.filter(t => selectedTests.has(t.id)).length}/{catTests.length}</span>
                  <input
                    type="checkbox"
                    checked={allSelected}
                    ref={el => { if (el) el.indeterminate = someSelected && !allSelected }}
                    onChange={() => toggleCategory(cat)}
                    onClick={e => e.stopPropagation()}
                    className="w-4 h-4 rounded border-zinc-300 text-brand-500 focus:ring-brand-500"
                  />
                </button>
                {expanded && (
                  <div className="divide-y divide-zinc-100">
                    {catTests.map(t => (
                      <label
                        key={t.id}
                        className="flex items-center gap-3 px-3 py-1.5 hover:bg-zinc-50 dark:hover:bg-slate-800 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={selectedTests.has(t.id)}
                          onChange={() => toggleTest(t.id)}
                          className="w-4 h-4 rounded border-zinc-300 text-brand-500 focus:ring-brand-500"
                        />
                        <span className="text-xs font-mono text-zinc-400 w-8">{t.id}</span>
                        <span className="text-sm text-zinc-700 dark:text-slate-300 flex-1">{t.name}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                          t.tier === 'automatic' ? 'bg-blue-50 text-blue-600' : 'bg-purple-50 text-purple-600'
                        }`}>{t.tier === 'automatic' ? 'Auto' : 'Manual'}</span>
                        {t.essential && <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-600 font-medium">Essential</span>}
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      <div className="flex justify-end">
        <button
          onClick={onDiscover}
          disabled={!cidrValid || hostCount === 0 || selectedTests.size === 0 || discovering}
          className="btn-primary"
        >
          {discovering ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          {discovering ? 'Discovering...' : 'Discover Devices'}
        </button>
      </div>
    </div>
  )
}

function ScanAnimation({ cidr }: { cidr: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center py-16"
    >
      <div className="relative w-28 h-28 mb-6">
        {/* Outer pulsing rings */}
        <div className="absolute inset-0 rounded-full border-2 border-blue-200 dark:border-blue-900 animate-ping opacity-20" />
        <div className="absolute inset-2 rounded-full border-2 border-blue-200 dark:border-blue-900 animate-ping opacity-20" style={{ animationDelay: '0.5s' }} />
        {/* Static ring */}
        <div className="absolute inset-0 rounded-full border-4 border-blue-200 dark:border-blue-900" />
        {/* Spinning arc */}
        <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-blue-500 animate-spin" />
        {/* Center icon */}
        <Network className="absolute inset-0 m-auto w-9 h-9 text-blue-500" />
      </div>
      <p className="text-base font-medium text-zinc-700 dark:text-slate-300">
        Scanning {cidr}...
      </p>
      <p className="text-sm text-zinc-400 dark:text-slate-500 mt-1.5">
        Discovering devices on the network
      </p>
      {/* Animated sweep bar */}
      <div className="w-64 h-1.5 mt-6 rounded-full bg-zinc-200 dark:bg-slate-700 overflow-hidden">
        <motion.div
          className="h-full w-1/3 rounded-full bg-gradient-to-r from-transparent via-blue-500 to-transparent"
          animate={{ x: ['-100%', '400%'] }}
          transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
        />
      </div>
    </motion.div>
  )
}

function ReviewStep({
  devices, selectedDevices, setSelectedDevices,
  starting, onStart, onBack, testCount,
}: {
  devices: DiscoveredDevice[]; selectedDevices: Set<string>; setSelectedDevices: (v: Set<string>) => void
  starting: boolean; onStart: () => void; onBack: () => void; testCount: number
}) {
  const [viewMode, setViewMode] = useState<DeviceViewMode>('grid')
  const [expandedVendors, setExpandedVendors] = useState<Set<string>>(new Set())
  const allSelected = devices.length > 0 && devices.every(d => selectedDevices.has(d.ip))

  // Group devices by vendor for tree view
  const vendorGroups = devices.reduce<Record<string, DiscoveredDevice[]>>((acc, d) => {
    const vendor = d.vendor || 'Unknown Vendor'
    if (!acc[vendor]) acc[vendor] = []
    acc[vendor].push(d)
    return acc
  }, {})

  // Auto-expand all vendors on first render
  useEffect(() => {
    setExpandedVendors(new Set(Object.keys(vendorGroups)))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [devices])

  const toggleDeviceSelection = (ip: string) => {
    const next = new Set(selectedDevices)
    next.has(ip) ? next.delete(ip) : next.add(ip)
    setSelectedDevices(next)
  }

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-200 dark:border-slate-700/50 bg-zinc-50 dark:bg-slate-800">
          <div className="flex items-center gap-2">
            <Monitor className="w-4 h-4 text-zinc-500" />
            <span className="text-sm font-semibold text-zinc-700 dark:text-slate-300">{devices.length} Device(s) Found</span>
          </div>
          <div className="flex items-center gap-3">
            {/* View mode toggle */}
            <div className="flex items-center rounded-lg border border-zinc-200 dark:border-slate-700/50 overflow-hidden">
              <button
                onClick={() => setViewMode('grid')}
                className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium transition-colors ${
                  viewMode === 'grid'
                    ? 'bg-brand-50 dark:bg-brand-900/30 text-brand-600 dark:text-brand-400'
                    : 'text-zinc-500 dark:text-slate-400 hover:bg-zinc-100 dark:hover:bg-slate-700'
                }`}
                title="Grid view"
              >
                <LayoutGrid className="w-3.5 h-3.5" />
                Grid
              </button>
              <button
                onClick={() => setViewMode('tree')}
                className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium transition-colors border-l border-zinc-200 dark:border-slate-700/50 ${
                  viewMode === 'tree'
                    ? 'bg-brand-50 dark:bg-brand-900/30 text-brand-600 dark:text-brand-400'
                    : 'text-zinc-500 dark:text-slate-400 hover:bg-zinc-100 dark:hover:bg-slate-700'
                }`}
                title="Tree view"
              >
                <List className="w-3.5 h-3.5" />
                Tree
              </button>
            </div>
            <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-slate-400 cursor-pointer">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={() => setSelectedDevices(allSelected ? new Set() : new Set(devices.map(d => d.ip)))}
                className="w-4 h-4 rounded border-zinc-300 text-brand-500"
              />
              Select All
            </label>
          </div>
        </div>

        {devices.length === 0 ? (
          <div className="p-8 text-center">
            <WifiOff className="w-8 h-8 text-zinc-300 mx-auto mb-2" />
            <p className="text-sm text-zinc-500">No devices found. Try a different subnet.</p>
          </div>
        ) : viewMode === 'grid' ? (
          /* --- Grid View --- */
          <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            <AnimatePresence>
              {devices.map((d, i) => (
                <motion.div
                  key={d.ip}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.06 }}
                  className={`relative rounded-lg border p-4 cursor-pointer transition-colors ${
                    selectedDevices.has(d.ip)
                      ? 'border-brand-400 bg-brand-50/50 dark:bg-brand-900/20 dark:border-brand-600'
                      : 'border-zinc-200 dark:border-slate-700/50 hover:border-zinc-300 dark:hover:border-slate-600 bg-white dark:bg-slate-800'
                  }`}
                  onClick={() => toggleDeviceSelection(d.ip)}
                >
                  <div className="absolute top-3 right-3">
                    <input
                      type="checkbox"
                      checked={selectedDevices.has(d.ip)}
                      onChange={() => toggleDeviceSelection(d.ip)}
                      onClick={e => e.stopPropagation()}
                      className="w-4 h-4 rounded border-zinc-300 text-brand-500"
                    />
                  </div>
                  <p className="text-sm font-mono font-bold text-zinc-800 dark:text-slate-200 mb-1">{d.ip}</p>
                  {d.mac && (
                    <p className="text-xs font-mono text-zinc-400 dark:text-slate-500 mb-2">{d.mac}</p>
                  )}
                  <div className="space-y-1">
                    {d.vendor && (
                      <div className="flex items-center gap-1.5">
                        <Shield className="w-3 h-3 text-zinc-400 shrink-0" />
                        <span className="text-xs text-zinc-600 dark:text-slate-400 truncate">{d.vendor}</span>
                      </div>
                    )}
                    {d.hostname && (
                      <div className="flex items-center gap-1.5">
                        <Server className="w-3 h-3 text-zinc-400 shrink-0" />
                        <span className="text-xs text-zinc-600 dark:text-slate-400 truncate">{d.hostname}</span>
                      </div>
                    )}
                    {d.os && (
                      <div className="flex items-center gap-1.5">
                        <Monitor className="w-3 h-3 text-zinc-400 shrink-0" />
                        <span className="text-xs text-zinc-600 dark:text-slate-400 truncate">{d.os}</span>
                      </div>
                    )}
                    {d.services && d.services.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {d.services.map(svc => (
                          <span key={svc} className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 font-medium">
                            {svc}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        ) : (
          /* --- Tree View --- */
          <div className="divide-y divide-zinc-100 dark:divide-slate-700/50">
            {Object.entries(vendorGroups).map(([vendor, vendorDevices]) => {
              const expanded = expandedVendors.has(vendor)
              const vendorAllSelected = vendorDevices.every(d => selectedDevices.has(d.ip))
              const vendorSomeSelected = vendorDevices.some(d => selectedDevices.has(d.ip))
              return (
                <div key={vendor}>
                  <button
                    onClick={() => {
                      const next = new Set(expandedVendors)
                      expanded ? next.delete(vendor) : next.add(vendor)
                      setExpandedVendors(next)
                    }}
                    className="w-full flex items-center gap-2 px-5 py-2.5 bg-zinc-50 dark:bg-slate-800/50 hover:bg-zinc-100 dark:hover:bg-slate-700/50 transition-colors"
                  >
                    {expanded
                      ? <ChevronDown className="w-4 h-4 text-zinc-400 dark:text-slate-500" />
                      : <ChevronRight className="w-4 h-4 text-zinc-400 dark:text-slate-500" />
                    }
                    <Shield className="w-4 h-4 text-brand-500" />
                    <span className="text-sm font-medium text-zinc-700 dark:text-slate-300 flex-1 text-left">{vendor}</span>
                    <span className="text-xs text-zinc-400 dark:text-slate-500 mr-2">{vendorDevices.length} device(s)</span>
                    <input
                      type="checkbox"
                      checked={vendorAllSelected}
                      ref={el => { if (el) el.indeterminate = vendorSomeSelected && !vendorAllSelected }}
                      onChange={(e) => {
                        e.stopPropagation()
                        const next = new Set(selectedDevices)
                        vendorDevices.forEach(d => vendorAllSelected ? next.delete(d.ip) : next.add(d.ip))
                        setSelectedDevices(next)
                      }}
                      onClick={e => e.stopPropagation()}
                      className="w-4 h-4 rounded border-zinc-300 text-brand-500"
                    />
                  </button>
                  <AnimatePresence>
                    {expanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        {vendorDevices.map(d => (
                          <label
                            key={d.ip}
                            className="flex items-center gap-3 px-5 pl-12 py-2 hover:bg-zinc-50 dark:hover:bg-slate-800 cursor-pointer border-t border-zinc-100 dark:border-slate-700/30"
                          >
                            <input
                              type="checkbox"
                              checked={selectedDevices.has(d.ip)}
                              onChange={() => toggleDeviceSelection(d.ip)}
                              className="w-4 h-4 rounded border-zinc-300 text-brand-500"
                            />
                            <Wifi className="w-3.5 h-3.5 text-zinc-400 dark:text-slate-500" />
                            <span className="text-sm font-mono font-medium text-zinc-800 dark:text-slate-200 w-32">{d.ip}</span>
                            {d.hostname && (
                              <span className="text-sm text-zinc-600 dark:text-slate-400 flex-1 truncate">{d.hostname}</span>
                            )}
                            <span className="text-xs font-mono text-zinc-400 dark:text-slate-500">{d.mac || ''}</span>
                          </label>
                        ))}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between">
        <button onClick={onBack} className="btn-secondary">Back</button>
        <div className="flex items-center gap-3">
          <span className="text-xs text-zinc-500">{selectedDevices.size} device(s) × {testCount} test(s)</span>
          <button
            onClick={onStart}
            disabled={selectedDevices.size === 0 || starting}
            className="btn-primary"
          >
            {starting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            {starting ? 'Starting...' : 'Start Scan'}
          </button>
        </div>
      </div>
    </div>
  )
}

function MonitorStep({ results, scanStatus, navigate, onNewScan }: { results: ScanResult[]; scanStatus: string; navigate: (path: string) => void; onNewScan: () => void }) {
  const totalTests = results.reduce((s, r) => s + r.total_tests, 0)
  const completedTests = results.reduce((s, r) => s + r.completed_tests, 0)
  const overallPct = totalTests > 0 ? Math.round((completedTests / totalTests) * 100) : 0
  const isRunning = scanStatus === 'running' || scanStatus === 'pending'

  return (
    <div className="space-y-4">
      <div className="card p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            {isRunning
              ? <Loader2 className="w-4 h-4 animate-spin text-brand-500" />
              : <CheckCircle2 className="w-4 h-4 text-emerald-500" />
            }
            <span className="text-sm font-semibold text-zinc-900 dark:text-slate-100">
              {isRunning ? `Scanning ${results.length} device(s)...` : `Scan complete — ${results.length} device(s)`}
            </span>
          </div>
          <span className="text-sm font-medium text-brand-500">{overallPct}%</span>
        </div>
        <div className="w-full bg-zinc-200 dark:bg-zinc-700 rounded-full h-2">
          <div
            className="bg-brand-500 h-2 rounded-full transition-all duration-500"
            style={{ width: `${overallPct}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {results.map(r => (
          <DeviceProgressCard key={r.run_id} result={r} navigate={navigate} />
        ))}
      </div>

      <div className="flex justify-start">
        <button onClick={onNewScan} className="btn-secondary">
          <RotateCcw className="w-4 h-4" /> New Scan
        </button>
      </div>
    </div>
  )
}

function DeviceProgressCard({ result, navigate }: { result: ScanResult; navigate: (path: string) => void }) {
  const [expanded, setExpanded] = useState(false)
  const pct = Math.round(result.progress_pct || 0)
  const isComplete = result.status === 'completed' || result.status === 'awaiting_manual'
  const isError = result.status === 'failed' || result.status === 'error'

  const displayName = result.hostname || result.vendor || null
  const subtitle = result.vendor && result.hostname ? result.vendor : null

  return (
    <div className={`card overflow-hidden ${isError ? 'border-red-200' : isComplete ? 'border-emerald-200' : ''}`}>
      <div
        className="p-4 cursor-pointer hover:bg-zinc-50 dark:hover:bg-slate-800/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <Server className="w-4 h-4 text-zinc-400 shrink-0" />
            <span className="text-sm font-mono font-medium text-zinc-800 dark:text-slate-200">{result.device_ip}</span>
            {displayName && (
              <span className="text-sm text-zinc-500 dark:text-slate-400 truncate">— {displayName}</span>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <StatusBadge status={result.status} verdict={result.overall_verdict} />
            {expanded ? <ChevronDown className="w-3.5 h-3.5 text-zinc-400" /> : <ChevronRight className="w-3.5 h-3.5 text-zinc-400" />}
          </div>
        </div>
        {subtitle && <p className="text-xs text-zinc-500 mb-2 ml-6">{subtitle}</p>}
        <div className="w-full bg-zinc-200 dark:bg-zinc-700 rounded-full h-1.5 mb-2">
          <div
            className={`h-1.5 rounded-full transition-all duration-500 ${isError ? 'bg-red-400' : isComplete ? 'bg-emerald-400' : 'bg-brand-500'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex items-center gap-3 text-[11px] text-zinc-500">
          <span>{result.completed_tests}/{result.total_tests} tests</span>
          {result.passed_tests > 0 && <span className="text-emerald-600">{result.passed_tests} pass</span>}
          {result.failed_tests > 0 && <span className="text-red-600">{result.failed_tests} fail</span>}
          {result.advisory_tests > 0 && <span className="text-amber-600">{result.advisory_tests} advisory</span>}
        </div>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-1 border-t border-zinc-100 dark:border-slate-700/50">
              <div className="grid grid-cols-2 gap-2 text-xs mb-3">
                <div>
                  <span className="text-zinc-400">IP Address</span>
                  <p className="font-mono text-zinc-700 dark:text-slate-300">{result.device_ip}</p>
                </div>
                {result.hostname && (
                  <div>
                    <span className="text-zinc-400">Hostname</span>
                    <p className="text-zinc-700 dark:text-slate-300">{result.hostname}</p>
                  </div>
                )}
                {result.vendor && (
                  <div>
                    <span className="text-zinc-400">Vendor</span>
                    <p className="text-zinc-700 dark:text-slate-300">{result.vendor}</p>
                  </div>
                )}
                <div>
                  <span className="text-zinc-400">Progress</span>
                  <p className="text-zinc-700 dark:text-slate-300">{pct}% ({result.completed_tests}/{result.total_tests})</p>
                </div>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); navigate(`/test-runs/${result.run_id}`) }}
                className="btn-primary text-xs py-1.5 px-3 w-full"
              >
                <ArrowRight className="w-3.5 h-3.5" />
                View Full Test Details
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function StatusBadge({ status, verdict }: { status: string; verdict: string | null }) {
  if (status === 'completed' || status === 'awaiting_manual') {
    if (verdict === 'pass') return <span className="badge bg-emerald-50 text-emerald-600 border border-emerald-200">Pass</span>
    if (verdict === 'fail') return <span className="badge bg-red-50 text-red-600 border border-red-200">Fail</span>
    if (verdict === 'qualified_pass') return <span className="badge bg-amber-50 text-amber-600 border border-amber-200">Advisory</span>
    return <span className="badge bg-blue-50 text-blue-600 border border-blue-200">Done</span>
  }
  if (status === 'running') return <span className="badge bg-brand-50 text-brand-600 border border-brand-200">Running</span>
  if (status === 'failed' || status === 'error') return <span className="badge bg-red-50 text-red-600 border border-red-200">Error</span>
  return <span className="badge bg-zinc-100 text-zinc-500 border border-zinc-200">{status}</span>
}

function ResultsStep({
  results, navigate, onReset,
}: {
  results: ScanResult[]; navigate: (path: string) => void; onReset: () => void
}) {
  const passed = results.filter(r => r.overall_verdict === 'pass').length
  const failed = results.filter(r => r.overall_verdict === 'fail').length

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Devices Scanned" value={results.length} icon={Monitor} />
        <StatCard label="Passed" value={passed} icon={CheckCircle2} color="emerald" />
        <StatCard label="Failed" value={failed} icon={XCircle} color="red" />
        <StatCard label="Advisory" value={results.filter(r => r.overall_verdict === 'qualified_pass').length} icon={AlertTriangle} color="amber" />
      </div>

      <div className="card">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-zinc-500 dark:text-slate-400 border-b border-zinc-200 dark:border-slate-700/50 bg-zinc-50 dark:bg-slate-800">
              <th className="px-5 py-2.5">Device IP</th>
              <th className="px-3 py-2.5">Vendor</th>
              <th className="px-3 py-2.5">Tests</th>
              <th className="px-3 py-2.5">Passed</th>
              <th className="px-3 py-2.5">Failed</th>
              <th className="px-3 py-2.5">Advisory</th>
              <th className="px-3 py-2.5">Verdict</th>
              <th className="px-3 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {results.map(r => (
              <tr key={r.run_id} className="border-b border-zinc-100 dark:border-slate-700/50 hover:bg-zinc-50 dark:hover:bg-slate-800">
                <td className="px-5 py-2.5 font-mono text-zinc-800 dark:text-slate-200">{r.device_ip}</td>
                <td className="px-3 py-2.5 text-zinc-600 dark:text-slate-400">{r.vendor || '—'}</td>
                <td className="px-3 py-2.5 text-zinc-600 dark:text-slate-400">{r.total_tests}</td>
                <td className="px-3 py-2.5 text-emerald-600 font-medium">{r.passed_tests}</td>
                <td className="px-3 py-2.5 text-red-600 font-medium">{r.failed_tests}</td>
                <td className="px-3 py-2.5 text-amber-600 font-medium">{r.advisory_tests}</td>
                <td className="px-3 py-2.5"><StatusBadge status={r.status} verdict={r.overall_verdict} /></td>
                <td className="px-3 py-2.5">
                  <button
                    onClick={() => navigate(`/test-runs/${r.run_id}`)}
                    className="text-xs text-brand-500 hover:text-brand-600 font-medium"
                  >View Details</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex justify-between">
        <button onClick={onReset} className="btn-secondary">
          <RotateCcw className="w-4 h-4" /> New Scan
        </button>
      </div>
    </div>
  )
}

function StatCard({ label, value, icon: Icon, color = 'brand' }: { label: string; value: number; icon: React.ElementType; color?: string }) {
  const colors: Record<string, string> = {
    brand: 'bg-brand-50 text-brand-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    red: 'bg-red-50 text-red-600',
    amber: 'bg-amber-50 text-amber-600',
  }
  return (
    <div className="card p-4">
      <div className={`w-8 h-8 rounded-lg ${colors[color]} flex items-center justify-center mb-2`}>
        <Icon className="w-4 h-4" />
      </div>
      <p className="text-2xl font-bold text-zinc-900 dark:text-slate-100">{value}</p>
      <p className="text-xs text-zinc-500 dark:text-slate-400">{label}</p>
    </div>
  )
}
