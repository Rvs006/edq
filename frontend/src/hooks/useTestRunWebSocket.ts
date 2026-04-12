import { useCallback, useEffect, useRef, useState } from 'react'

import {
  normalizeTestRunProgressMessage,
  type TestRunProgressMessage,
} from '@/lib/testContracts'

type CableStatus = 'connected' | 'disconnected' | 'reconnecting'

const STALE_AFTER_MS = 45_000

export function useTestRunWebSocket(runId: string | undefined) {
  const [messages, setMessages] = useState<TestRunProgressMessage[]>([])
  const [lastProgress, setLastProgress] = useState<TestRunProgressMessage | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [isFresh, setIsFresh] = useState(false)
  const [cableStatus, setCableStatus] = useState<CableStatus>('connected')
  const [terminalOutput, setTerminalOutput] = useState<Record<string, string>>({})
  const [reconnectCount, setReconnectCount] = useState(0)
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null)
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
  const previousRunIdRef = useRef<string | undefined>(undefined)
  const shouldReconnectRef = useRef(false)
  const maxReconnectAttempts = 10

  const markSocketAlive = useCallback(() => {
    const now = Date.now()
    setLastMessageAt(now)
    setIsFresh(true)
  }, [])

  const connect = useCallback(() => {
    if (!runId || !shouldReconnectRef.current) return

    // Close any existing socket to prevent duplicates
    if (wsRef.current) {
      const old = wsRef.current
      wsRef.current = null
      old.onclose = null  // prevent reconnect from old socket
      old.close()
    }

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const url = `${proto}//${host}/api/ws/test-run/${runId}`

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setIsConnected(true)
        if (reconnectAttempts.current > 0) {
          setReconnectCount((count: number) => count + 1)
          console.warn('[WS] Reconnected - triggering state sync')
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
        markSocketAlive()

        setMessages((prev: TestRunProgressMessage[]) => {
          const next = [...prev, msg]
          return next.length > 500 ? next.slice(-500) : next
        })
        if (msg.type !== 'stdout_line' && msg.type !== 'cable_probe') {
          setLastProgress(msg)
        }

        if (msg.type === 'stdout_line' && msg.data.test_id) {
          setTerminalOutput((prev: Record<string, string>) => {
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
          const probeData = {
            reachable: Boolean(msg.data.reachable),
            consecutiveFailures: Number(msg.data.consecutive_failures) || 0,
            failThreshold: Number(msg.data.fail_threshold) || 3,
            timestamp: String(msg.data.timestamp || ''),
          }
          setCableProbe(probeData)

          // During paused state, if the device becomes reachable, show
          // "reconnecting" in the UI before the server confirms full resume.
          // If it goes back to unreachable, revert to "disconnected".
          if (msg.data.paused && probeData.reachable) {
            setCableStatus('reconnecting')
          } else if (msg.data.paused && !probeData.reachable) {
            setCableStatus('disconnected')
          }
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
        setIsFresh(false)
        setLastMessageAt(null)
        wsRef.current = null

        if (shouldReconnectRef.current && reconnectAttempts.current < maxReconnectAttempts) {
          const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 30000)
          if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
          reconnectTimer.current = setTimeout(() => {
            reconnectAttempts.current += 1
            connect()
          }, delay)
        }
      }

      ws.onerror = () => {
        console.warn('[EDQ] WebSocket error - cable status may be unreliable')
        ws.close()
      }
    } catch {
      // Connection failed.
    }
  }, [markSocketAlive, runId])

  useEffect(() => {
    if (!isConnected || lastMessageAt == null) {
      setIsFresh(false)
      return
    }

    const staleTimer = setTimeout(() => {
      setIsFresh(false)
    }, STALE_AFTER_MS)

    return () => clearTimeout(staleTimer)
  }, [isConnected, lastMessageAt])

  useEffect(() => {
    shouldReconnectRef.current = Boolean(runId)
    if (!runId) {
      previousRunIdRef.current = undefined
      setMessages([])
      setLastProgress(null)
      setIsConnected(false)
      setIsFresh(false)
      setCableStatus('connected')
      setTerminalOutput({})
      setReconnectCount(0)
      setLastMessageAt(null)
      setCableProbe(null)
      reconnectAttempts.current = 0
      return
    }

    if (previousRunIdRef.current !== runId) {
      previousRunIdRef.current = runId
      setMessages([])
      setLastProgress(null)
      setIsConnected(false)
      setIsFresh(false)
      setCableStatus('connected')
      setTerminalOutput({})
      setReconnectCount(0)
      setLastMessageAt(null)
      setCableProbe(null)
      reconnectAttempts.current = 0
    }

    connect()
    return () => {
      shouldReconnectRef.current = false
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (cableReconnectTimer.current) clearTimeout(cableReconnectTimer.current)
      if (wsRef.current) {
        const socket = wsRef.current
        wsRef.current = null
        socket.close()
      }
    }
  }, [connect, runId])

  const clearTerminalOutput = useCallback((testId: string) => {
    setTerminalOutput((prev: Record<string, string>) => {
      const next = { ...prev }
      delete next[testId]
      return next
    })
  }, [])

  return {
    messages,
    lastProgress,
    isConnected,
    isFresh,
    cableStatus,
    terminalOutput,
    clearTerminalOutput,
    reconnectCount,
    lastMessageAt,
    cableProbe,
  }
}
