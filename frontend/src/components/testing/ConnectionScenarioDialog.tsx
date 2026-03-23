import { useState } from 'react'
import { Cable, AlertTriangle, Shield, Building2, Wifi, X } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'

type ConnectionScenario = 'direct_cable' | 'test_lab' | 'site_network'

interface ConnectionScenarioDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (scenario: ConnectionScenario) => void
  isLoading: boolean
}

const scenarios: {
  value: ConnectionScenario
  label: string
  description: string
  icon: React.ElementType
  intensity: string
  warning?: boolean
}[] = [
  {
    value: 'direct_cable',
    label: 'Direct Cable',
    description: 'Device connected directly to test laptop via Ethernet cable.',
    icon: Cable,
    intensity: 'Full scan intensity',
  },
  {
    value: 'test_lab',
    label: 'Test Lab',
    description: 'Device on an isolated test network.',
    icon: Building2,
    intensity: 'Moderate scan intensity',
  },
  {
    value: 'site_network',
    label: 'Site Network',
    description: 'Device on a live production network.',
    icon: Wifi,
    intensity: 'Low scan intensity',
    warning: true,
  },
]

export default function ConnectionScenarioDialog({
  open,
  onOpenChange,
  onConfirm,
  isLoading,
}: ConnectionScenarioDialogProps) {
  const [selected, setSelected] = useState<ConnectionScenario>('direct_cable')
  const [siteConfirmed, setSiteConfirmed] = useState(false)

  const selectedScenario = scenarios.find((s) => s.value === selected)!
  const needsConfirm = selected === 'site_network' && !siteConfirmed

  const handleConfirm = () => {
    if (needsConfirm) {
      setSiteConfirmed(true)
      return
    }
    onConfirm(selected)
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 z-50 animate-fade-in" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50
                                   w-[90vw] max-w-lg bg-white rounded-xl shadow-xl
                                   animate-fade-in">
          <div className="p-5 border-b border-zinc-100">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Shield className="w-5 h-5 text-brand-500" />
                <Dialog.Title className="text-base font-semibold text-zinc-900">
                  Connection Scenario
                </Dialog.Title>
              </div>
              <Dialog.Close className="p-1 rounded-lg hover:bg-zinc-100 transition-colors">
                <X className="w-4 h-4 text-zinc-400" />
              </Dialog.Close>
            </div>
            <Dialog.Description className="text-sm text-zinc-500 mt-1">
              Select how the device under test is connected. This determines scan intensity.
            </Dialog.Description>
          </div>

          <div className="p-5 space-y-3">
            {scenarios.map((scenario) => {
              const Icon = scenario.icon
              const isActive = selected === scenario.value
              return (
                <button
                  key={scenario.value}
                  onClick={() => {
                    setSelected(scenario.value)
                    setSiteConfirmed(false)
                  }}
                  className={`w-full flex items-start gap-3 p-3 rounded-lg border transition-all text-left
                    ${isActive
                      ? 'border-brand-500 bg-brand-50 ring-2 ring-brand-500/20'
                      : 'border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50'
                    }`}
                >
                  <div
                    className={`flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center ${
                      isActive ? 'bg-brand-500 text-white' : 'bg-zinc-100 text-zinc-500'
                    }`}
                  >
                    <Icon className="w-4.5 h-4.5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-medium ${isActive ? 'text-brand-700' : 'text-zinc-900'}`}>
                        {scenario.label}
                      </span>
                      {scenario.warning && (
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                      )}
                    </div>
                    <p className="text-xs text-zinc-500 mt-0.5">{scenario.description}</p>
                    <p className="text-[10px] text-zinc-400 mt-0.5 font-medium uppercase tracking-wider">
                      {scenario.intensity}
                    </p>
                  </div>
                  <div
                    className={`flex-shrink-0 w-4 h-4 rounded-full border-2 mt-0.5 ${
                      isActive ? 'border-brand-500 bg-brand-500' : 'border-zinc-300'
                    }`}
                  >
                    {isActive && (
                      <div className="w-full h-full flex items-center justify-center">
                        <div className="w-1.5 h-1.5 rounded-full bg-white" />
                      </div>
                    )}
                  </div>
                </button>
              )
            })}

            {selected === 'site_network' && siteConfirmed && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-red-800">Live Network Warning</p>
                    <p className="text-xs text-red-600 mt-0.5">
                      Scanning a device on a production network may cause service disruption.
                      Scan intensity will be reduced to minimise risk.
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center justify-end gap-2 p-4 border-t border-zinc-100">
            <Dialog.Close className="btn-secondary text-sm">Cancel</Dialog.Close>
            <button
              onClick={handleConfirm}
              disabled={isLoading}
              className={`text-sm ${needsConfirm ? 'btn-danger' : 'btn-primary'}`}
            >
              {isLoading ? (
                'Starting...'
              ) : needsConfirm ? (
                <>
                  <AlertTriangle className="w-4 h-4" />
                  Confirm Live Network Scan
                </>
              ) : (
                'Start Tests'
              )}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
