import { useState, useEffect, useCallback } from 'react'

interface SystemStatus {
  isOnline: boolean
  backendHealthy: boolean
  toolsHealthy: boolean
  lastChecked: Date | null
}

export function useOnlineStatus(): SystemStatus {
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const [backendHealthy, setBackendHealthy] = useState(true)
  const [toolsHealthy, setToolsHealthy] = useState(true)
  const [lastChecked, setLastChecked] = useState<Date | null>(null)

  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/health', { credentials: 'include' })
      if (!res.ok) {
        setBackendHealthy(false)
        setToolsHealthy(false)
        return
      }
      const data = await res.json()
      setBackendHealthy(data.status === 'ok')
      setToolsHealthy(data.tools_sidecar !== 'unhealthy' && data.tools_sidecar !== 'unavailable')
      setLastChecked(new Date())
    } catch {
      setBackendHealthy(false)
    }
  }, [])

  useEffect(() => {
    checkHealth()
    const interval = setInterval(checkHealth, 30000)
    return () => clearInterval(interval)
  }, [checkHealth])

  return { isOnline, backendHealthy, toolsHealthy, lastChecked }
}
