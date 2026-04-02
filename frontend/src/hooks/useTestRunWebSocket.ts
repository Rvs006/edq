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
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
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

        setMessages((prev) => [...prev, msg])
        setLastProgress(msg)

        if (msg.type === 'stdout_line' && msg.data.test_id) {
          setTerminalOutput((prev) => ({
            ...prev,
            [msg.data.test_id!]:
              (prev[msg.data.test_id!] || '') + (msg.data.stdout_line || '') + '\n',
          }))
        }

        if (msg.type === 'cable_disconnected') {
          setCableStatus('disconnected')
        }

        if (msg.type === 'cable_timeout') {
          setCableStatus('disconnected')
        }

        if (msg.type === 'cable_reconnected') {
          setCableStatus('reconnecting')
          setTimeout(() => setCableStatus('connected'), 5000)
        }
      }

      ws.onclose = () => {
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
  }
}
