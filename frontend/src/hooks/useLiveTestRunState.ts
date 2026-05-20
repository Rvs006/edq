import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { useTestRunWebSocket } from '@/hooks/useTestRunWebSocket'
import { isExecutingTestRunStatus } from '@/lib/testContracts'
import { invalidateTestRunResource } from '@/lib/testRunResources'

export function useLiveTestRunState(
  runId: string | undefined,
  runStatus: string | undefined,
) {
  const queryClient = useQueryClient()
  const invalidateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const ws = useTestRunWebSocket(
    runId && isExecutingTestRunStatus(runStatus) ? runId : undefined,
  )

  useEffect(() => {
    return () => {
      if (invalidateTimerRef.current) {
        clearTimeout(invalidateTimerRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (!ws.lastProgress || !runId) return
    const msg = ws.lastProgress

    const refreshRun =
      msg.type === 'run_started'
      || msg.type === 'run_complete'
      || msg.type === 'run_failed'
      || msg.type === 'run_error'
      || msg.type === 'cable_disconnected'
      || msg.type === 'cable_reconnected'
      || msg.type === 'cable_timeout'
    const refreshResults = msg.type === 'test_complete'

    if (!refreshRun && !refreshResults) return

    if (invalidateTimerRef.current) clearTimeout(invalidateTimerRef.current)
    invalidateTimerRef.current = setTimeout(() => {
      invalidateTimerRef.current = null
      invalidateTestRunResource(queryClient, runId)
    }, 500)
  }, [queryClient, runId, ws.lastProgress])

  useEffect(() => {
    if (ws.reconnectCount > 0 && runId) {
      invalidateTestRunResource(queryClient, runId)
    }
  }, [queryClient, runId, ws.reconnectCount])

  return ws
}
