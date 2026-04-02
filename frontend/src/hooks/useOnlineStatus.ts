import { useState, useEffect, useCallback } from 'react'
import { healthApi } from '@/lib/api'

interface SystemStatus {
  isOnline: boolean
  frontendHealthy: boolean
  backendHealthy: boolean
  databaseHealthy: boolean
  toolsHealthy: boolean
  toolVersions: Record<string, string>
  lastChecked: Date | null
}

export function useOnlineStatus(): SystemStatus {
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const [frontendHealthy] = useState(true)
  const [backendHealthy, setBackendHealthy] = useState(true)
  const [databaseHealthy, setDatabaseHealthy] = useState(true)
  const [toolsHealthy, setToolsHealthy] = useState(true)
  const [toolVersions, setToolVersions] = useState<Record<string, string>>({})
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
      const res = await healthApi.systemStatus()
      const data = res.data
      setBackendHealthy(data.backend?.status === 'ok')
      setDatabaseHealthy(data.database?.status === 'ok')
      setToolsHealthy(data.tools_sidecar?.status === 'ok')
      setToolVersions(data.tools || {})
      setLastChecked(data.checked_at ? new Date(data.checked_at) : new Date())
    } catch {
      setBackendHealthy(false)
      setDatabaseHealthy(false)
      setToolsHealthy(false)
      setToolVersions({})
    }
  }, [])

  useEffect(() => {
    checkHealth()
    const interval = setInterval(checkHealth, 30000)
    return () => clearInterval(interval)
  }, [checkHealth])

  return {
    isOnline,
    frontendHealthy,
    backendHealthy,
    databaseHealthy,
    toolsHealthy,
    toolVersions,
    lastChecked,
  }
}
