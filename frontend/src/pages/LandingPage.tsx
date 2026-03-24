import { Link } from 'react-router-dom'
import { Zap, FileSpreadsheet, Wifi, WifiOff, ArrowRight, Cpu, ScanLine, ClipboardCheck, FileDown, Shield } from 'lucide-react'

const stats = [
  { value: '43', label: 'Security Tests', icon: Shield, color: 'text-blue-600', bg: 'bg-blue-50' },
  { value: '60%', label: 'Automated', icon: Zap, color: 'text-amber-600', bg: 'bg-amber-50' },
  { value: '3', label: 'Report Formats', icon: FileSpreadsheet, color: 'text-emerald-600', bg: 'bg-emerald-50' },
  { value: '100%', label: 'Offline', icon: WifiOff, color: 'text-purple-600', bg: 'bg-purple-50' },
]

const steps = [
  {
    step: 1,
    title: 'Connect Device',
    description: 'Plug in the device under test via Ethernet. EDQ auto-discovers it on the network.',
    icon: Cpu,
    color: 'from-blue-500 to-blue-600',
  },
  {
    step: 2,
    title: 'Run Automated Scans',
    description: 'EDQ executes 25+ security tests automatically using nmap, testssl.sh, ssh-audit, and more.',
    icon: ScanLine,
    color: 'from-amber-500 to-amber-600',
  },
  {
    step: 3,
    title: 'Complete Manual Checks',
    description: 'Guided forms walk you through 18 physical and UI-based tests with single-click verdicts.',
    icon: ClipboardCheck,
    color: 'from-emerald-500 to-emerald-600',
  },
  {
    step: 4,
    title: 'Generate Reports',
    description: 'Export pixel-perfect Excel or Word reports that match Electracom client formats exactly.',
    icon: FileDown,
    color: 'from-purple-500 to-purple-600',
  },
]

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-zinc-50 flex flex-col">
      <header className="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-zinc-200">
        {/* Rainbow accent bar */}
        <div className="flex h-1 w-full">
          <div className="flex-1 bg-[#0099cc]" />
          <div className="flex-1 bg-[#f5a623]" />
          <div className="flex-1 bg-[#34a853]" />
          <div className="flex-1 bg-[#9b59b6]" />
          <div className="flex-1 bg-[#e53935]" />
        </div>
        <div className="max-w-6xl mx-auto flex items-center justify-between h-14 px-4 sm:px-6">
          <div className="flex items-center gap-2.5">
            <img src="/icon.png" alt="" className="h-7 w-7" />
            <span className="text-sm font-bold text-zinc-900 tracking-widest uppercase" style={{ letterSpacing: '0.15em' }}>Electracom</span>
          </div>
          <Link
            to="/login"
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-lg hover:bg-brand-600 transition-colors"
          >
            Sign In
          </Link>
        </div>
      </header>

      <main className="flex-1">
        <section className="relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-blue-50 via-white to-purple-50" />
          <div className="absolute top-20 -right-32 w-96 h-96 bg-brand-500/5 rounded-full blur-3xl" />
          <div className="absolute -bottom-16 -left-16 w-72 h-72 bg-purple-500/5 rounded-full blur-3xl" />

          <div className="relative max-w-6xl mx-auto px-4 sm:px-6 pt-16 pb-20 sm:pt-24 sm:pb-28">
            <div className="max-w-2xl mx-auto text-center">
              <div className="inline-flex items-center gap-1.5 px-3 py-1 bg-brand-50 text-brand-500 rounded-full text-xs font-semibold mb-6 border border-brand-100">
                <Shield className="w-3 h-3" />
                Electracom Device Qualifier
              </div>

              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-zinc-900 leading-[1.1]">
                <span className="bg-gradient-to-r from-brand-500 via-blue-600 to-purple-600 bg-clip-text text-transparent">
                  Automated Security
                </span>
                <br />
                <span className="text-zinc-900">Qualification for</span>
                <br />
                <span className="text-zinc-900">Smart Building Devices</span>
              </h1>

              <p className="mt-5 text-lg text-zinc-600 max-w-lg mx-auto leading-relaxed">
                Reduce device qualification from a full working day to 1&ndash;2 hours.
                43 security tests. Automated reports. Completely offline.
              </p>

              <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
                <Link
                  to="/login"
                  className="inline-flex items-center gap-2 px-6 py-3 text-sm font-semibold text-white bg-brand-500 rounded-lg hover:bg-brand-600 transition-colors shadow-lg shadow-brand-500/20"
                >
                  Get Started <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            </div>
          </div>
        </section>

        <section className="relative -mt-8 z-10">
          <div className="max-w-4xl mx-auto px-4 sm:px-6">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
              {stats.map((stat) => (
                <div
                  key={stat.label}
                  className="bg-white rounded-xl border border-zinc-200 p-4 sm:p-5 shadow-sm hover:shadow-md transition-shadow"
                >
                  <div className={`w-9 h-9 rounded-lg ${stat.bg} flex items-center justify-center mb-3`}>
                    <stat.icon className={`w-4.5 h-4.5 ${stat.color}`} />
                  </div>
                  <p className="text-2xl sm:text-3xl font-bold text-zinc-900">{stat.value}</p>
                  <p className="text-xs sm:text-sm text-zinc-500 mt-0.5">{stat.label}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="max-w-5xl mx-auto px-4 sm:px-6 py-20 sm:py-28">
          <div className="text-center mb-12">
            <h2 className="text-2xl sm:text-3xl font-bold text-zinc-900">How It Works</h2>
            <p className="text-sm text-zinc-500 mt-2 max-w-md mx-auto">
              Four simple steps to qualify any IP device on your network
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {steps.map((step) => (
              <div key={step.step} className="relative group">
                <div className="bg-white rounded-xl border border-zinc-200 p-5 h-full hover:border-zinc-300 hover:shadow-md transition-all">
                  <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${step.color} flex items-center justify-center mb-4 shadow-sm`}>
                    <step.icon className="w-5 h-5 text-white" />
                  </div>
                  <div className="text-xs font-semibold text-zinc-400 mb-1">Step {step.step}</div>
                  <h3 className="text-base font-semibold text-zinc-900 mb-1.5">{step.title}</h3>
                  <p className="text-sm text-zinc-500 leading-relaxed">{step.description}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="bg-zinc-900 text-white">
          <div className="max-w-5xl mx-auto px-4 sm:px-6 py-16 sm:py-20">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              <div>
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center mb-3">
                  <Wifi className="w-5 h-5 text-blue-400" />
                </div>
                <h3 className="font-semibold text-white mb-1">Fully Offline</h3>
                <p className="text-sm text-zinc-400 leading-relaxed">
                  Runs entirely on Docker. No cloud, no internet. Perfect for isolated test environments.
                </p>
              </div>
              <div>
                <div className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center mb-3">
                  <Zap className="w-5 h-5 text-amber-400" />
                </div>
                <h3 className="font-semibold text-white mb-1">Saves 6+ Hours</h3>
                <p className="text-sm text-zinc-400 leading-relaxed">
                  Automates 60% of tests and generates reports instantly. What took a day now takes hours.
                </p>
              </div>
              <div>
                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center mb-3">
                  <FileSpreadsheet className="w-5 h-5 text-emerald-400" />
                </div>
                <h3 className="font-semibold text-white mb-1">Client-Ready Reports</h3>
                <p className="text-sm text-zinc-400 leading-relaxed">
                  Pixel-perfect Excel and Word reports matching Electracom&rsquo;s existing client formats.
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="bg-white border-t border-zinc-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <img src="/icon.png" alt="" className="h-5 w-5" />
            <span className="text-xs font-bold text-zinc-700 tracking-widest uppercase" style={{ letterSpacing: '0.12em' }}>Electracom</span>
          </div>
          <p className="text-xs text-zinc-400">
            Electracom Projects Ltd &mdash; A Sauter Group Company
          </p>
        </div>
      </footer>
    </div>
  )
}
