import { useEffect, useState } from 'react'
import { WifiOff, Wifi, Cable } from 'lucide-react'

type CableStatus = 'connected' | 'disconnected' | 'reconnecting'

interface CableProbe {
  reachable: boolean
  consecutiveFailures: number
  failThreshold: number
}

interface WobblyCableAlertProps {
  status: CableStatus
  probe?: CableProbe | null
}

export default function WobblyCableAlert({ status, probe }: WobblyCableAlertProps) {
  const [visible, setVisible] = useState(false)
  const [hiding, setHiding] = useState(false)

  useEffect(() => {
    if (status === 'disconnected') {
      setVisible(true)
      setHiding(false)
    } else if (status === 'reconnecting') {
      setVisible(true)
      setHiding(false)
      const timer = setTimeout(() => {
        setHiding(true)
        setTimeout(() => setVisible(false), 500)
      }, 5000)
      return () => clearTimeout(timer)
    } else {
      if (visible) {
        setHiding(true)
        const timer = setTimeout(() => setVisible(false), 500)
        return () => clearTimeout(timer)
      }
    }
  }, [status])

  const showProbeOnly = !visible && status === 'connected' && probe
  const probeWarning = probe && probe.consecutiveFailures > 0 && probe.consecutiveFailures < probe.failThreshold

  if (!visible && !showProbeOnly) return null

  if (showProbeOnly) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 text-xs rounded-md border border-transparent">
        {probeWarning ? (
          <>
            <span className="inline-block w-2 h-2 rounded-full bg-yellow-400" />
            <span className="text-yellow-700 dark:text-yellow-300">
              Cable: {probe.consecutiveFailures}/{probe.failThreshold} checks failed
            </span>
          </>
        ) : (
          <>
            <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
            <span className="text-green-700 dark:text-green-300">Cable OK</span>
          </>
        )}
      </div>
    )
  }

  const isDisconnected = status === 'disconnected'
  const isReconnecting = status === 'reconnecting'

  return (
    <div
      className={`transition-all duration-500 ${hiding ? 'opacity-0 -translate-y-2' : 'opacity-100 translate-y-0'}`}
    >
      <div
        className={`flex items-center gap-3 px-4 py-3 rounded-lg border ${
          isDisconnected
            ? 'bg-red-50 border-red-200 text-red-800 dark:bg-red-950/30 dark:border-red-800/50 dark:text-red-200'
            : 'bg-green-50 border-green-200 text-green-800 dark:bg-green-950/30 dark:border-green-800/50 dark:text-green-200'
        }`}
      >
        <div
          className={`flex-shrink-0 ${isDisconnected ? 'animate-pulse' : ''}`}
        >
          {isDisconnected ? (
            <WifiOff className="w-5 h-5 text-red-600 dark:text-red-400" />
          ) : (
            <Wifi className="w-5 h-5 text-green-600 dark:text-green-400" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium">
            {isDisconnected
              ? 'Network cable disconnected \u2014 testing paused'
              : 'Cable reconnected \u2014 resuming tests...'}
          </p>
          <p className="text-xs mt-0.5 opacity-75">
            {isDisconnected
              ? probe
                ? `Checking connection\u2026 ${probe.consecutiveFailures}/${probe.failThreshold} probes failed. Retrying every few seconds.`
                : 'Reconnect the cable to continue. Retrying every few seconds.'
              : isReconnecting
                ? 'Stabilising connection before resuming automated tests.'
                : 'Connection restored.'}
          </p>
        </div>
        <Cable
          className={`w-4 h-4 flex-shrink-0 ${
            isDisconnected ? 'text-red-400' : 'text-green-400'
          }`}
        />
      </div>
    </div>
  )
}
