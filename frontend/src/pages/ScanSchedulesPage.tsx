import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { scanSchedulesApi, devicesApi, templatesApi } from '@/lib/api'
import type { ScanSchedule, Device, TestTemplate } from '@/lib/types'
import {
  Clock, Plus, Trash2, Pause, Play, Loader2, AlertCircle,
  CalendarClock, RefreshCw, ChevronDown,
} from 'lucide-react'

function FrequencyBadge({ frequency }: { frequency: string }) {
  const colors: Record<string, string> = {
    daily: 'bg-blue-50 text-blue-700',
    weekly: 'bg-purple-50 text-purple-700',
    monthly: 'bg-amber-50 text-amber-700',
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[frequency] || 'bg-zinc-100 text-zinc-700'}`}>
      {frequency}
    </span>
  )
}

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
      active ? 'bg-green-50 text-green-700' : 'bg-zinc-100 text-zinc-500'
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-green-500' : 'bg-zinc-400'}`} />
      {active ? 'Active' : 'Paused'}
    </span>
  )
}

function CreateScheduleDialog({
  open,
  onClose,
  devices,
  templates,
}: {
  open: boolean
  onClose: () => void
  devices: Device[]
  templates: TestTemplate[]
}) {
  const queryClient = useQueryClient()
  const [deviceId, setDeviceId] = useState('')
  const [templateId, setTemplateId] = useState('')
  const [frequency, setFrequency] = useState<'daily' | 'weekly' | 'monthly'>('weekly')
  const [maxRuns, setMaxRuns] = useState('')
  const [error, setError] = useState('')

  const createMutation = useMutation({
    mutationFn: (data: { device_id: string; template_id: string; frequency: string; max_runs?: number }) =>
      scanSchedulesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scan-schedules'] })
      onClose()
      setDeviceId('')
      setTemplateId('')
      setFrequency('weekly')
      setMaxRuns('')
      setError('')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to create schedule'
      setError(msg)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!deviceId || !templateId) {
      setError('Please select a device and template')
      return
    }
    setError('')
    createMutation.mutate({
      device_id: deviceId,
      template_id: templateId,
      frequency,
      ...(maxRuns ? { max_runs: parseInt(maxRuns) } : {}),
    })
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-5 border-b border-zinc-100">
          <h2 className="text-lg font-semibold text-zinc-900">Create Scan Schedule</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-600">&times;</button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-lg p-3">
              <AlertCircle className="w-4 h-4 shrink-0" />
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">Device</label>
            <div className="relative">
              <select
                value={deviceId}
                onChange={(e) => setDeviceId(e.target.value)}
                className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm appearance-none pr-8"
              >
                <option value="">Select a device...</option>
                {devices.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.hostname || d.ip_address} ({d.ip_address})
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-2 top-2.5 w-4 h-4 text-zinc-400 pointer-events-none" />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">Test Template</label>
            <div className="relative">
              <select
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
                className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm appearance-none pr-8"
              >
                <option value="">Select a template...</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.test_ids.length} tests)
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-2 top-2.5 w-4 h-4 text-zinc-400 pointer-events-none" />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">Frequency</label>
            <div className="flex gap-2">
              {(['daily', 'weekly', 'monthly'] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFrequency(f)}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    frequency === f
                      ? 'border-brand-500 bg-brand-50 text-brand-700'
                      : 'border-zinc-200 text-zinc-600 hover:border-zinc-300'
                  }`}
                >
                  {f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">
              Max Runs <span className="text-zinc-400 font-normal">(optional)</span>
            </label>
            <input
              type="number"
              min="1"
              value={maxRuns}
              onChange={(e) => setMaxRuns(e.target.value)}
              placeholder="Unlimited"
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="btn-primary text-sm"
            >
              {createMutation.isPending ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Creating...</>
              ) : (
                <><Plus className="w-4 h-4" /> Create Schedule</>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function ScanSchedulesPage() {
  const [showCreate, setShowCreate] = useState(false)
  const queryClient = useQueryClient()

  const { data: schedules, isLoading } = useQuery({
    queryKey: ['scan-schedules'],
    queryFn: () => scanSchedulesApi.list().then((r) => r.data as ScanSchedule[]),
  })

  const { data: devices } = useQuery({
    queryKey: ['devices-for-schedules'],
    queryFn: () => devicesApi.list({ limit: 500 }).then((r) => r.data),
  })

  const { data: templates } = useQuery({
    queryKey: ['templates-for-schedules'],
    queryFn: () => templatesApi.list({ limit: 500 }).then((r) => r.data),
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      scanSchedulesApi.update(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scan-schedules'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => scanSchedulesApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scan-schedules'] }),
  })

  const deviceMap = new Map((devices || []).map((d) => [d.id, d]))
  const templateMap = new Map((templates || []).map((t) => [t.id, t]))

  return (
    <div className="page-container">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-zinc-900">Scan Schedules</h1>
          <p className="text-sm text-zinc-500 mt-1">Schedule recurring security scans for your devices</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="btn-primary text-sm">
          <Plus className="w-4 h-4" /> New Schedule
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-brand-500" />
        </div>
      ) : !schedules || schedules.length === 0 ? (
        <div className="card p-12 text-center">
          <CalendarClock className="w-12 h-12 text-zinc-300 mx-auto mb-3" />
          <h3 className="text-lg font-semibold text-zinc-900 mb-1">No scan schedules</h3>
          <p className="text-sm text-zinc-500 mb-4">
            Create a schedule to automatically re-scan devices on a recurring basis.
          </p>
          <button onClick={() => setShowCreate(true)} className="btn-primary text-sm mx-auto">
            <Plus className="w-4 h-4" /> Create First Schedule
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {schedules.map((schedule) => {
            const device = deviceMap.get(schedule.device_id)
            const template = templateMap.get(schedule.template_id)
            return (
              <div key={schedule.id} className="card p-4">
                <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                      schedule.is_active ? 'bg-brand-50' : 'bg-zinc-100'
                    }`}>
                      <RefreshCw className={`w-5 h-5 ${schedule.is_active ? 'text-brand-500' : 'text-zinc-400'}`} />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-semibold text-zinc-900 truncate">
                          {device?.hostname || device?.ip_address || 'Unknown Device'}
                        </p>
                        <FrequencyBadge frequency={schedule.frequency} />
                        <StatusBadge active={schedule.is_active} />
                      </div>
                      <p className="text-xs text-zinc-500 mt-0.5">
                        Template: {template?.name || 'Unknown'} &middot;
                        Runs: {schedule.run_count}{schedule.max_runs ? `/${schedule.max_runs}` : ''} &middot;
                        Next: {new Date(schedule.next_run_at).toLocaleString()}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      onClick={() => toggleMutation.mutate({ id: schedule.id, is_active: !schedule.is_active })}
                      disabled={toggleMutation.isPending}
                      className="p-2 rounded-lg hover:bg-zinc-100 transition-colors text-zinc-500 hover:text-zinc-700"
                      title={schedule.is_active ? 'Pause schedule' : 'Resume schedule'}
                    >
                      {schedule.is_active ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                    </button>
                    <button
                      onClick={() => {
                        if (confirm('Delete this schedule? This cannot be undone.')) {
                          deleteMutation.mutate(schedule.id)
                        }
                      }}
                      disabled={deleteMutation.isPending}
                      className="p-2 rounded-lg hover:bg-red-50 transition-colors text-zinc-400 hover:text-red-600"
                      title="Delete schedule"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {schedule.last_run_at && (
                  <div className="mt-3 pt-3 border-t border-zinc-100 flex items-center gap-2 text-xs text-zinc-500">
                    <Clock className="w-3.5 h-3.5" />
                    Last run: {new Date(schedule.last_run_at).toLocaleString()}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {showCreate && (
        <CreateScheduleDialog
          open={showCreate}
          onClose={() => setShowCreate(false)}
          devices={devices || []}
          templates={templates || []}
        />
      )}
    </div>
  )
}
