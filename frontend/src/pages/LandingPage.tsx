import { Link } from 'react-router-dom'
import {
  Shield, Network, ClipboardCheck, FileDown, Terminal,
  Wifi, Monitor, ScanLine, ArrowRight,
} from 'lucide-react'
import ThemeToggle from '@/components/common/ThemeToggle'
import { ElectracomLogo } from '@/components/common/ElectracomLogo'

const capabilities = [
  {
    icon: Network,
    title: 'Device Discovery',
    description: 'Find one device by IP or survey a subnet. Auto-detects IP, MAC, vendor, open ports, and OS fingerprint via nmap.',
  },
  {
    icon: ScanLine,
    title: 'Automated Security Scans',
    description: '29 automated checks using nmap, testssl.sh, ssh-audit, hydra, nikto, and supporting probes. Runs against the device under test.',
  },
  {
    icon: ClipboardCheck,
    title: 'Guided Manual Tests',
    description: '31 guided manual checks for physical inspection, web UI review, configuration validation, and extended qualification evidence.',
  },
  {
    icon: FileDown,
    title: 'Report Generation',
    description: 'Export Excel, Word, and PDF reports mapped to Electracom client templates.',
  },
  {
    icon: Terminal,
    title: 'Tools Sidecar',
    description: 'Dockerized sidecar runs nmap, testssl.sh, ssh-audit, hydra, nikto, and related network helpers. No local install needed.',
  },
  {
    icon: Shield,
    title: 'Review & Audit',
    description: 'QA review queue for overriding test results. Full audit log of who did what and when.',
  },
]

const tools = [
  'nmap', 'testssl.sh', 'ssh-audit', 'hydra', 'snmpwalk', 'nikto',
]

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-dark-bg flex flex-col pt-[3px]">
      <div className="fixed top-0 left-0 right-0 z-[60] h-[3px] rainbow-bar" />

      <header className="sticky top-[3px] z-30 bg-white/80 dark:bg-dark-surface/80 backdrop-blur-md border-b border-zinc-200 dark:border-slate-700/50">
        <div className="max-w-5xl mx-auto grid grid-cols-[1fr_auto_1fr] items-center min-h-[84px] px-4 sm:px-6">
          <div />
          <Link to="/" className="justify-self-center py-3">
            <ElectracomLogo size="md" />
          </Link>
          <div className="justify-self-end flex items-center gap-2">
            <ThemeToggle />
            <Link to="/login" className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-lg hover:bg-brand-600 transition-colors">
              Sign In
            </Link>
          </div>
        </div>
      </header>

      <div className="flex-1">
        {/* Hero — simple, no fluff */}
        <section className="bg-white dark:bg-dark-surface border-b border-zinc-200 dark:border-slate-700/50">
          <div className="max-w-5xl mx-auto px-4 sm:px-6 py-12 sm:py-16">
            <div className="max-w-xl">
              <h1 className="text-2xl sm:text-3xl font-bold text-zinc-900 dark:text-white leading-tight">
                EDQ — Device Qualifier
              </h1>
              <p className="mt-3 text-sm sm:text-base text-zinc-600 dark:text-slate-400 leading-relaxed">
                Internal tool for security qualification of IP devices on Electracom projects.
                60 tests (29 automated + 31 guided manual). Runs offline on Docker.
              </p>
              <div className="mt-5 flex items-center gap-3">
                <Link to="/login" className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-white bg-brand-500 rounded-lg hover:bg-brand-600 transition-colors">
                  Sign In <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            </div>
          </div>
        </section>

        {/* What it actually does */}
        <section className="max-w-5xl mx-auto px-4 sm:px-6 py-12 sm:py-16">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-white mb-6">What EDQ Does</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {capabilities.map((cap) => (
              <div key={cap.title} className="bg-white dark:bg-dark-card rounded-lg border border-zinc-200 dark:border-slate-700/50 p-4">
                <cap.icon className="w-5 h-5 text-brand-500 mb-2" />
                <h3 className="text-sm font-semibold text-zinc-900 dark:text-slate-100 mb-1">{cap.title}</h3>
                <p className="text-xs text-zinc-500 dark:text-slate-400 leading-relaxed">{cap.description}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="max-w-5xl mx-auto px-4 sm:px-6 pb-12 sm:pb-16">
          <div className="rounded-2xl border border-zinc-200 dark:border-slate-700/50 bg-white dark:bg-dark-card p-5 sm:p-6">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-white mb-4">How to use EDQ effectively</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 text-sm text-zinc-600 dark:text-slate-400">
              <div>
                <h3 className="font-semibold text-zinc-900 dark:text-slate-200 mb-2">Before you start</h3>
                <ul className="space-y-2 list-disc pl-5">
                  <li>Make sure the device is powered, reachable, and on an authorised network.</li>
                  <li>If the device uses DHCP, register its MAC address so EDQ can discover the lease later.</li>
                  <li>Pick the right connection scenario so skips and manual steps make sense.</li>
                </ul>
              </div>
              <div>
                <h3 className="font-semibold text-zinc-900 dark:text-slate-200 mb-2">While reviewing tests</h3>
                <ul className="space-y-2 list-disc pl-5">
                  <li>Use the sidebar to move test by test instead of scanning the whole page.</li>
                  <li>Open the explainer first: it tells you what the test checks, why it matters, and what pass/fail means.</li>
                  <li>Add notes whenever a result is unusual, partially acceptable, or needs reviewer context.</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* Tools & workflow */}
        <section className="bg-white dark:bg-dark-surface border-y border-zinc-200 dark:border-slate-700/50">
          <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10 sm:py-14">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              <div>
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-white mb-3">Workflow</h2>
                <ol className="space-y-3 text-sm text-zinc-600 dark:text-slate-400">
                  <li className="flex items-start gap-2">
                    <span className="w-5 h-5 rounded-full bg-brand-500 text-white text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">1</span>
                    <span><strong className="text-zinc-900 dark:text-slate-200">Register or discover device</strong> — add a known IP, or use bulk discovery when the address is unknown</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="w-5 h-5 rounded-full bg-brand-500 text-white text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">2</span>
                    <span><strong className="text-zinc-900 dark:text-slate-200">Create test run</strong> — select device and template, start automated scans</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="w-5 h-5 rounded-full bg-brand-500 text-white text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">3</span>
                    <span><strong className="text-zinc-900 dark:text-slate-200">Complete manual checks</strong> — guided forms for physical and UI tests</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="w-5 h-5 rounded-full bg-brand-500 text-white text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">4</span>
                    <span><strong className="text-zinc-900 dark:text-slate-200">Generate report</strong> — export Excel or Word in Electracom format</span>
                  </li>
                </ol>
              </div>
              <div>
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-white mb-3">Security Tools</h2>
                <p className="text-xs text-zinc-500 dark:text-slate-400 mb-3">
                  All tools run inside the Docker sidecar container. No local installation required.
                </p>
                <div className="flex flex-wrap gap-2">
                  {tools.map(t => (
                    <span key={t} className="inline-flex items-center gap-1 px-2.5 py-1 bg-zinc-100 dark:bg-slate-800 text-zinc-700 dark:text-slate-300 rounded text-xs font-mono">
                      <Terminal className="w-3 h-3 text-zinc-400" />
                      {t}
                    </span>
                  ))}
                </div>
                <div className="mt-4 flex items-start gap-2 text-xs text-zinc-500 dark:text-slate-400">
                  <Wifi className="w-4 h-4 text-zinc-400 shrink-0 mt-0.5" />
                  <span>Runs entirely offline — no cloud, no internet. Docker Compose stack on any machine.</span>
                </div>
                <div className="mt-2 flex items-start gap-2 text-xs text-zinc-500 dark:text-slate-400">
                  <Monitor className="w-4 h-4 text-zinc-400 shrink-0 mt-0.5" />
                  <span>Supports cameras, controllers, intercoms, access panels, HVAC, IoT sensors, meters.</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      <footer className="bg-white dark:bg-dark-card border-t border-zinc-200 dark:border-slate-700/50">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-5 flex flex-col items-center gap-3 text-center">
          <ElectracomLogo size="sm" />
          <p className="text-[11px] text-zinc-400 dark:text-slate-500">
            Electracom Projects Ltd &mdash; Internal Use Only
          </p>
        </div>
      </footer>
    </div>
  )
}
