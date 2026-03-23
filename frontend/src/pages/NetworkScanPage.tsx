import { Network, Construction } from 'lucide-react'

export default function NetworkScanPage() {
  return (
    <div className="page-container">
      <div className="mb-5">
        <h1 className="section-title">Network Scan</h1>
        <p className="section-subtitle">Discover devices on the connected network</p>
      </div>

      <div className="card p-12 text-center">
        <div className="w-16 h-16 rounded-full bg-zinc-100 flex items-center justify-center mx-auto mb-4">
          <Network className="w-8 h-8 text-zinc-400" />
        </div>
        <h3 className="text-base font-semibold text-zinc-700 mb-2">Coming Soon</h3>
        <p className="text-sm text-zinc-500 max-w-md mx-auto">
          Network scanning functionality is under development. This will allow automatic
          discovery of IP devices on the connected network segment.
        </p>
        <div className="flex items-center justify-center gap-2 mt-4 text-xs text-zinc-400">
          <Construction className="w-4 h-4" />
          <span>Implementation in progress</span>
        </div>
      </div>
    </div>
  )
}
