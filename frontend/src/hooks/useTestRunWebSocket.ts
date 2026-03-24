import { useEffect, useRef, useState, useCallback } from 'react'

export interface TestProgressData {
  test_number?: string
  test_name?: string
  status?: string
  verdict?: string
  progress_pct?: number
  stdout_line?: string
  elapsed_seconds?: number
  parsed_findings?: Record<string, unknown> | unknown[]
  auto_comment?: string
  error?: string
}

export interface TestProgressMessage {
  type:
    | 'test_start'
    | 'test_complete'
    | 'run_complete'
    | 'run_error'
    | 'cable_disconnected'
    | 'cable_reconnected'
    | 'stdout_line'
    | 'test_progress'
  data: TestProgressData
}

type CableStatus = 'connected' | 'disconnected' | 'reconnecting'

export function useTestRunWebSocket(runId: string | undefined) {
  const [messages, setMessages] = useState<TestProgressMessage[]>([])
  const [lastProgress, setLastProgress] = useState<TestProgressMessage | null>(null)
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
        try {
          const msg: TestProgressMessage = JSON.parse(event.data)
          setMessages((prev) => [...prev, msg])
          setLastProgress(msg)

          if (msg.type === 'stdout_line' && msg.data.test_number) {
            setTerminalOutput((prev) => ({
              ...prev,
              [msg.data.test_number!]:
                (prev[msg.data.test_number!] || '') + (msg.data.stdout_line || '') + '\n',
            }))
          }

          if (msg.type === 'cable_disconnected') {
            setCableStatus('disconnected')
          }

          if (msg.type === 'cable_reconnected') {
            setCableStatus('reconnecting')
            setTimeout(() => setCableStatus('connected'), 5000)
          }
        } catch {
          // ignore malformed messages
        }
      }

      ws.onclose = () => {
        setIsConnected(false)
        wsRef.current = null

        if (reconnectAttempts.current < maxReconnectAttempts) {
          const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 30000)
          reconnectTimer.current = setTimeout(() => {
            reconnectAttempts.current++
            connect()
          }, delay)
        }
      }

      ws.onerror = () => {
        ws.close()
      }
    } catch {
      // connection failed
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

  const clearTerminalOutput = useCallback((testNumber: string) => {
    setTerminalOutput((prev) => {
      const next = { ...prev }
      delete next[testNumber]
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
