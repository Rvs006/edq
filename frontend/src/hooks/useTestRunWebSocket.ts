import { useCallback, useEffect, useRef, useState } from 'react'

import {
  normalizeTestRunProgressMessage,
  type TestRunProgressMessage,
} from '@/lib/testContracts'

type CableStatus = 'connected' | 'disconnected' | 'reconnecting'

export function useTestRunWebSocket(runId: string | undefined) {
  const [messages, setMessages] = useState<TestRunProgressMessage[]>([])
  const [lastProgress, setLastProgress] = useState<TestRunProgressMessage | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [cableStatus, setCableStatus] = useState<CableStatus>('connected')
  const [terminalOutput, setTerminalOutput] = useState<Record<string, string>>({})
  const [reconnectCount, setReconnectCount] = useState(0)
  const [cableProbe, setCableProbe] = useState<{
    reachable: boolean
    consecutiveFailures: number
    failThreshold: number
    timestamp: string
  } | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cableReconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttempts = useRef(0)
  const maxReconnectAttempts = 10

  const connect = useCallback(() => {
    if (!runId) return

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const url = `${proto}//${host}/api/ws/test-run/${runId}`

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setIsConnected(true)
        if (reconnectAttempts.current > 0) {
          setReconnectCount(c => c + 1)
          console.warn('[WS] Reconnected — triggering state sync')
        }
        reconnectAttempts.current = 0
      }

      ws.onmessage = (event) => {
        let msg: TestRunProgressMessage | null = null
        try {
          msg = normalizeTestRunProgressMessage(JSON.parse(event.data))
        } catch {
          msg = null
        }
        if (!msg) return

        setMessages((prev) => {
          const next = [...prev, msg]
          return next.length > 500 ? next.slice(-500) : next
        })
        setLastProgress(msg)

        if (msg.type === 'stdout_line' && msg.data.test_id) {
          setTerminalOutput((prev) => {
            const existing = prev[msg.data.test_id!] || ''
            const updated = existing + (msg.data.stdout_line || '') + '\n'
            return {
              ...prev,
              [msg.data.test_id!]: updated.length > 50000
                ? '[output truncated]\n' + updated.slice(-50000)
                : updated,
            }
          })
        }

        if (msg.type === 'cable_disconnected') {
          console.warn('[EDQ] Cable status changed: disconnected (WS cable_disconnected)')
          if (cableReconnectTimer.current) {
            clearTimeout(cableReconnectTimer.current)
            cableReconnectTimer.current = null
          }
          setCableStatus('disconnected')
        }

        if (msg.type === 'cable_timeout') {
          console.warn('[EDQ] Cable status changed: disconnected (WS cable_timeout)')
          if (cableReconnectTimer.current) {
            clearTimeout(cableReconnectTimer.current)
            cableReconnectTimer.current = null
          }
          setCableStatus('disconnected')
        }

        if (msg.type === 'cable_probe') {
          setCableProbe({
            reachable: Boolean(msg.data.reachable),
            consecutiveFailures: Number(msg.data.consecutive_failures) || 0,
            failThreshold: Number(msg.data.fail_threshold) || 2,
            timestamp: String(msg.data.timestamp || ''),
          })
        }

        if (msg.type === 'cable_reconnected') {
          console.warn('[EDQ] Cable status changed: reconnecting (WS cable_reconnected)')
          setCableStatus('reconnecting')
          if (cableReconnectTimer.current) {
            clearTimeout(cableReconnectTimer.current)
          }
          cableReconnectTimer.current = setTimeout(() => {
            cableReconnectTimer.current = null
            setCableStatus('connected')
          }, 5000)
        }
      }

      ws.onclose = () => {
        console.warn('[EDQ] WebSocket closed, marking WS as disconnected')
        setIsConnected(false)
        wsRef.current = null

        if (reconnectAttempts.current < maxReconnectAttempts) {
          const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 30000)
          if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
          reconnectTimer.current = setTimeout(() => {
            reconnectAttempts.current += 1
            connect()
          }, delay)
        }
      }

      ws.onerror = () => {
        console.warn('[EDQ] WebSocket error — cable status may be unreliable')
        ws.close()
      }
    } catch {
      // Connection failed.
    }
  }, [runId])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (cableReconnectTimer.current) clearTimeout(cableReconnectTimer.current)
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  const clearTerminalOutput = useCallback((testId: string) => {
    setTerminalOutput((prev) => {
      const next = { ...prev }
      delete next[testId]
      return next
    })
  }, [])

  return {
    messages,
    lastProgress,
    isConnected,
    cableStatus,
    terminalOutput,
    clearTerminalOutput,
    reconnectCount,
    cableProbe,
  }
}
