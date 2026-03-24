import { useState } from 'react'
import { Camera, Cpu, Radio, Mic, Box, ChevronRight, Shield, Check } from 'lucide-react'

interface DeviceProfile {
  id: string
  name: string
  icon: React.ElementType
  description: string
  color: string
  testIds: string[]
}

const PROFILES: DeviceProfile[] = [
  {
    id: 'camera',
    name: 'IP Camera',
    icon: Camera,
    description: 'RTSP/ONVIF video surveillance cameras with streaming capabilities',
    color: 'blue',
    testIds: ['U01', 'U02', 'U06', 'U07', 'U08', 'U09', 'U10', 'U11', 'U12', 'U15', 'U16', 'U19', 'U34', 'U35', 'U36'],
  },
  {
    id: 'controller',
    name: 'Access Controller',
    icon: Cpu,
    description: 'Door controllers, alarm panels, and building management systems',
    color: 'purple',
    testIds: ['U01', 'U02', 'U06', 'U08', 'U10', 'U11', 'U15', 'U16', 'U19', 'U34'],
  },
  {
    id: 'iot_gateway',
    name: 'IoT Gateway',
    icon: Radio,
    description: 'Edge gateways bridging IoT protocols (Zigbee, Z-Wave, BACnet)',
    color: 'green',
    testIds: ['U01', 'U02', 'U06', 'U07', 'U08', 'U10', 'U11', 'U12', 'U15', 'U16', 'U19'],
  },
  {
    id: 'intercom',
    name: 'Intercom / VoIP',
    icon: Mic,
    description: 'SIP-based intercoms, door stations, and VoIP endpoints',
    color: 'amber',
    testIds: ['U01', 'U02', 'U06', 'U08', 'U10', 'U11', 'U15', 'U16', 'U34', 'U35'],
  },
  {
    id: 'generic',
    name: 'Generic Device',
    icon: Box,
    description: 'Default profile for uncategorised network devices',
    color: 'zinc',
    testIds: ['U01', 'U02', 'U06', 'U08', 'U10', 'U16'],
  },
]

const colorMap: Record<string, { bg: string; border: string; text: string; badge: string; iconBg: string }> = {
  blue: { bg: 'bg-blue-50 dark:bg-blue-950/30', border: 'border-blue-200 dark:border-blue-800', text: 'text-blue-700 dark:text-blue-300', badge: 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300', iconBg: 'bg-blue-100 dark:bg-blue-900' },
  purple: { bg: 'bg-purple-50 dark:bg-purple-950/30', border: 'border-purple-200 dark:border-purple-800', text: 'text-purple-700 dark:text-purple-300', badge: 'bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300', iconBg: 'bg-purple-100 dark:bg-purple-900' },
  green: { bg: 'bg-green-50 dark:bg-green-950/30', border: 'border-green-200 dark:border-green-800', text: 'text-green-700 dark:text-green-300', badge: 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300', iconBg: 'bg-green-100 dark:bg-green-900' },
  amber: { bg: 'bg-amber-50 dark:bg-amber-950/30', border: 'border-amber-200 dark:border-amber-800', text: 'text-amber-700 dark:text-amber-300', badge: 'bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-300', iconBg: 'bg-amber-100 dark:bg-amber-900' },
  zinc: { bg: 'bg-zinc-50 dark:bg-zinc-800/50', border: 'border-zinc-200 dark:border-zinc-700', text: 'text-zinc-700 dark:text-zinc-300', badge: 'bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300', iconBg: 'bg-zinc-100 dark:bg-zinc-800' },
}

export default function DeviceProfilesPage() {
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null)
  const selected = PROFILES.find((p) => p.id === selectedProfile)

  return (
    <div className="page-container">
      <div className="mb-5">
        <h1 className="section-title">Device Profiles</h1>
        <p className="section-subtitle">
          Pre-configured test suites tailored for specific device categories.
          Select a profile to see which tests are included.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3 mb-6">
        {PROFILES.map((profile) => {
          const c = colorMap[profile.color]
          const isSelected = selectedProfile === profile.id
          const Icon = profile.icon
          return (
            <button
              key={profile.id}
              onClick={() => setSelectedProfile(isSelected ? null : profile.id)}
              className={`text-left p-4 rounded-xl border-2 transition-all duration-200 ${
                isSelected
                  ? `${c.bg} ${c.border} ring-2 ring-offset-1 ring-${profile.color}-400/30`
                  : 'border-zinc-200 dark:border-zinc-700 hover:border-zinc-300 dark:hover:border-zinc-600 bg-white dark:bg-zinc-900'
              }`}
            >
              <div className={`w-10 h-10 rounded-lg ${c.iconBg} flex items-center justify-center mb-3`}>
                <Icon className={`w-5 h-5 ${c.text}`} />
              </div>
              <h3 className={`text-sm font-semibold mb-1 ${isSelected ? c.text : 'text-zinc-900 dark:text-zinc-100'}`}>
                {profile.name}
              </h3>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 line-clamp-2 mb-2">
                {profile.description}
              </p>
              <div className="flex items-center justify-between">
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${c.badge}`}>
                  {profile.testIds.length} tests
                </span>
                {isSelected && <Check className={`w-4 h-4 ${c.text}`} />}
              </div>
            </button>
          )
        })}
      </div>

      {selected && (
        <div className="card p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className={`w-8 h-8 rounded-lg ${colorMap[selected.color].iconBg} flex items-center justify-center`}>
              <selected.icon className={`w-4 h-4 ${colorMap[selected.color].text}`} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                {selected.name} — Included Tests
              </h3>
              <p className="text-xs text-zinc-500">
                {selected.testIds.length} tests will run when this profile is assigned
              </p>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
            {selected.testIds.map((testId) => (
              <div
                key={testId}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700"
              >
                <Shield className="w-3.5 h-3.5 text-brand-500 flex-shrink-0" />
                <span className="text-xs font-mono text-zinc-700 dark:text-zinc-300">{testId}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!selected && (
        <div className="card p-8 text-center">
          <div className="w-12 h-12 rounded-full bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center mx-auto mb-3">
            <ChevronRight className="w-6 h-6 text-zinc-400" />
          </div>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Select a device profile above to see the included test suite
          </p>
        </div>
      )}
    </div>
  )
}
