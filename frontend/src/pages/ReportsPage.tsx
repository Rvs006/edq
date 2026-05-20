import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { reportsApi, getApiErrorMessage } from '@/lib/api'
import type { TestRun, ReportTemplate } from '@/lib/types'
import { toLocalDateOnly, toLocalDateString } from '@/lib/testContracts'
import { fetchTestRuns, testRunKeys } from '@/lib/testRunResources'
import { Download, FileSpreadsheet, FileText, Loader2, LayoutTemplate } from 'lucide-react'
import Callout from '@/components/common/Callout'
import toast from 'react-hot-toast'
import { getPreferredDeviceName } from '@/lib/deviceLabels'
import { normalizeTemplateName } from '@/lib/templateNames'

const TEMPLATE_OPTIONS = [
  { key: 'generic', label: 'Generic IP Device (Rev00 C00)', category: 'generic' },
]

type ReportFormat = 'excel' | 'word'

type FormatGroup = {
  title: string
  description: string
  formats: { key: ReportFormat; label: string; ext: string; icon: typeof FileSpreadsheet }[]
}

function getReportRunTimestamp(run: TestRun): string {
  return run.completed_at || run.started_at || run.created_at || ''
}

function buildReportRunGroups(runs: TestRun[]) {
  const sortedRuns = [...runs].sort((a, b) => getReportRunTimestamp(b).localeCompare(getReportRunTimestamp(a)))
  const latestRunId = sortedRuns[0]?.id || null
  const groups = new Map<string, TestRun[]>()

  for (const run of sortedRuns) {
    const device = getPreferredDeviceName(run)
    groups.set(device, [...(groups.get(device) || []), run])
  }

  return {
    latestRunId,
    groups: Array.from(groups.entries()).map(([device, deviceRuns]) => ({
      device,
      runs: deviceRuns,
    })),
  }
}

const FORMAT_PREVIEW: Record<ReportFormat, { title: string; highlights: string[] }> = {
  excel: {
    title: 'Excel Workbook Preview',
    highlights: [
      'Workbook tabs: General Test Information, Test Results, Additional Device Information, Raw Evidence',
      'Per-test rows with verdict, comments, engineer notes, and evidence summary',
      'Detailed observer/tool evidence is preserved in the Raw Evidence tab',
    ],
  },
  word: {
    title: 'Word Report Preview',
    highlights: [
      'Editable document using the same sections and report model as Excel',
      'Good for handoff and client editing',
      'Raw evidence is included as a detailed evidence section',
    ],
  },
}

export default function ReportsPage() {
  const [selectedRun, setSelectedRun] = useState('')
  const [reportType, setReportType] = useState<ReportFormat>('excel')
  const [templateKey, setTemplateKey] = useState('generic')
  const [includeSynopsis, setIncludeSynopsis] = useState(true)
  const [generating, setGenerating] = useState(false)

  const { data: runs, isError } = useQuery({
    queryKey: testRunKeys.list({ status: 'completed' }),
    queryFn: () => fetchTestRuns({ status: 'completed' }),
  })

  const { data: templates } = useQuery({
    queryKey: ['report-templates'],
    queryFn: () => reportsApi.templates().then(r => r.data),
  })

  const completedRuns = useMemo(
    () => [...((runs || []) as TestRun[])].sort((a, b) => getReportRunTimestamp(b).localeCompare(getReportRunTimestamp(a))),
    [runs]
  )
  const reportRunGroups = useMemo(() => buildReportRunGroups(completedRuns), [completedRuns])
  const selectedRunDetails = completedRuns.find((run: TestRun) => run.id === selectedRun) || null
  const selectedReadiness = selectedRunDetails?.readiness_summary || null
  const selectedRunHasSynopsis = Boolean(selectedRunDetails?.synopsis?.trim())

  const triggerBlobDownload = async (filename: string, expectedExt: string) => {
    const response = await reportsApi.download(filename)
    const blob = response.data as Blob
    const contentType = (response.headers?.['content-type'] as string | undefined) || ''
    if (contentType.includes('application/json') || contentType.startsWith('text/')) {
      const text = await blob.text()
      throw new Error(`Server returned ${contentType || 'unexpected'} instead of the report. ${text.slice(0, 200)}`)
    }
    if (!filename.toLowerCase().endsWith(expectedExt)) {
      throw new Error(`Backend produced ${filename} but a ${expectedExt} file was requested`)
    }
    const objectUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = objectUrl
    a.download = filename
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    setTimeout(() => {
      document.body.removeChild(a)
      URL.revokeObjectURL(objectUrl)
    }, 100)
  }

  const handleGenerate = async () => {
    if (!selectedRun) { toast.error('Select a test run'); return }
    setGenerating(true)
    try {
      const { data } = await reportsApi.generate({
        test_run_id: selectedRun,
        report_type: reportType,
        include_synopsis: includeSynopsis,
        template_key: templateKey,
      })
      if (!data.filename) {
        toast.error('Report generation returned no file. Check backend logs.')
        return
      }
      const extensionMap: Record<ReportFormat, string> = {
        excel: '.xlsx',
        word: '.docx',
      }
      const downloadName = data.filename

      await triggerBlobDownload(downloadName, extensionMap[reportType])
      toast.success(`Report generated: ${downloadName}`)
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Report generation failed'))
    } finally {
      setGenerating(false)
    }
  }

  const availableTemplates = templates?.length ? templates : TEMPLATE_OPTIONS
  const selectedFormatPreview = FORMAT_PREVIEW[reportType]

  const formatGroups: FormatGroup[] = [
    {
      title: 'Spreadsheet Exports',
      description: 'Excel workbook matching the canonical qualification report.',
      formats: [
        { key: 'excel', label: 'Excel', ext: '.xlsx', icon: FileSpreadsheet },
      ],
    },
    {
      title: 'Document Exports',
      description: 'Editable Word deliverable with the same report sections as Excel.',
      formats: [
        { key: 'word', label: 'Word', ext: '.docx', icon: FileText },
      ],
    },
  ]

  return (
    <div className="page-container">
      <div className="mb-5">
        <h1 className="section-title">Reports</h1>
        <p className="section-subtitle">Generate spreadsheet and document qualification reports from the same run, template profile, and shared report model</p>
      </div>

      {isError && (
        <div className="mb-5">
          <Callout variant="error">Failed to load completed test runs. Please try again.</Callout>
        </div>
      )}

      <div data-tour="report-form" className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 card p-5">
          <h2 className="font-semibold text-zinc-900 dark:text-slate-100 mb-4">Generate Report</h2>

          <div className="space-y-4">
            <div>
              <label className="label">Test Run</label>
              <select value={selectedRun} onChange={(e) => setSelectedRun(e.target.value)} aria-label="Select test run" className="input">
                <option value="">Select a report-ready test run...</option>
                {reportRunGroups.groups.map((group) => (
                  <optgroup key={group.device} label={`${group.device} (${group.runs.length})`}>
                    {group.runs.map((run: TestRun) => {
                      const timestamp = getReportRunTimestamp(run)
                      const template = normalizeTemplateName(run.template_name)
                      return (
                        <option key={run.id} value={run.id}>
                          {run.id === reportRunGroups.latestRunId ? 'Latest - ' : ''}
                          {getPreferredDeviceName(run)} - {toLocalDateString(timestamp)}
                          {template ? ` - ${template}` : ''}
                          {` - ${run.readiness_summary?.score ?? run.confidence ?? 1}/10`}
                        </option>
                      )
                    })}
                  </optgroup>
                ))}
              </select>
              {selectedRunDetails && (
                <div className="mt-2 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-600 dark:border-slate-700/50 dark:bg-slate-900/40 dark:text-slate-300">
                  <div className="flex flex-wrap gap-x-3 gap-y-1">
                    <span><strong>Device:</strong> {getPreferredDeviceName(selectedRunDetails)}</span>
                    <span><strong>Run:</strong> {toLocalDateString(getReportRunTimestamp(selectedRunDetails))}</span>
                    {selectedRunDetails.template_name && (
                      <span><strong>Template:</strong> {normalizeTemplateName(selectedRunDetails.template_name)}</span>
                    )}
                  </div>
                </div>
              )}
              {selectedReadiness && (
                <div className="mt-2">
                  <Callout
                    variant={selectedReadiness.report_ready ? 'success' : selectedReadiness.level === 'blocked' ? 'error' : 'warning'}
                    title={`Readiness: ${selectedReadiness.label} (${selectedReadiness.score}/10)`}
                  >
                    {selectedReadiness.summary}
                  </Callout>
                </div>
              )}
            </div>

            <div>
              <label className="label flex items-center gap-2">
                <LayoutTemplate className="w-4 h-4 text-zinc-400" />
                Report Template Profile
              </label>
              <select value={templateKey} onChange={(e) => setTemplateKey(e.target.value)} aria-label="Select report template" className="input">
                {availableTemplates.map((t: ReportTemplate) => (
                  <option key={t.key} value={t.key}>
                    {normalizeTemplateName(t.name || t.label) || 'Report profile'}
                    {t.device_category ? ` (${t.device_category})` : ''}
                  </option>
                ))}
              </select>
              <p className="text-xs text-zinc-500 mt-1">
                The canonical report profile applies to Excel and Word outputs.
              </p>
            </div>

            <div>
              <label className="label">Report Format</label>
              <div className="space-y-3">
                {formatGroups.map((group) => (
                  <div key={group.title} className="rounded-lg border border-zinc-200 dark:border-slate-700/50 p-3">
                    <div className="mb-3">
                      <p className="text-sm font-semibold text-zinc-900 dark:text-slate-100">{group.title}</p>
                      <p className="text-xs text-zinc-500">{group.description}</p>
                    </div>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      {group.formats.map(({ key, label, ext, icon: Icon }) => (
                        <button
                          key={key}
                          type="button"
                          onClick={() => setReportType(key)}
                          className={`flex items-center gap-3 p-4 rounded-lg border transition-colors ${
                            reportType === key
                              ? 'border-brand-500 bg-brand-50 dark:bg-brand-950/30'
                              : 'border-zinc-200 dark:border-slate-700/50 hover:border-zinc-300 dark:hover:border-slate-600'
                          }`}
                        >
                          <Icon className={`w-6 h-6 ${reportType === key ? 'text-brand-500' : 'text-zinc-400'}`} />
                          <div className="text-left">
                            <p className="text-sm font-semibold text-zinc-900 dark:text-slate-100">{label}</p>
                            <p className="text-xs text-zinc-500">{ext} format</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="synopsis"
                checked={includeSynopsis}
                onChange={(e) => setIncludeSynopsis(e.target.checked)}
                className="w-4 h-4 rounded border-zinc-300 text-brand-500 focus:ring-brand-500"
              />
              <label htmlFor="synopsis" className="text-sm text-zinc-700 dark:text-slate-300">
                Include saved synopsis text (if present on this run)
              </label>
            </div>
            <p className="text-xs text-zinc-500 -mt-2">
              {selectedRun
                ? selectedRunHasSynopsis
                  ? 'This run already has synopsis text saved in EDQ and can include it in the report.'
                  : 'No synopsis is currently saved for this run. Reports still generate normally without it. Synopsis drafting, when enabled, uses EDQ server-side provider settings rather than each user\'s Codex or Claude login.'
                : 'Reports can include synopsis text only when it is already saved on the selected run. Any synopsis drafting uses EDQ server-side provider settings.'}
            </p>

            <button type="button" onClick={handleGenerate} disabled={generating || !selectedRun || Boolean(selectedReadiness && !selectedReadiness.report_ready)}
              title={selectedReadiness && !selectedReadiness.report_ready ? selectedReadiness.next_step : 'Generate official report'}
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 active:bg-green-800 transition-colors duration-150 focus:outline-hidden focus:ring-2 focus:ring-green-500/50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
              {generating ? 'Generating...' : 'Generate Report'}
            </button>
          </div>
        </div>

        <div className="space-y-4">
          <div className="card p-4">
            <h3 className="font-semibold text-zinc-900 dark:text-slate-100 mb-3">Report Profile</h3>
            <div className="space-y-2">
              {availableTemplates.map((template: ReportTemplate) => (
                <div key={template.key} className="flex items-center gap-2 py-1">
                  <div className="w-2 h-2 rounded-full bg-brand-500" />
                  <div>
                    <p className="text-sm font-medium text-zinc-900 dark:text-slate-100">
                      {normalizeTemplateName(template.name || template.label) || 'Report profile'}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {template.description || `${template.device_category || template.category || 'Device'} profile shared across report outputs.`}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card p-4">
            <h3 className="font-semibold text-zinc-900 dark:text-slate-100 mb-3">{selectedFormatPreview.title}</h3>
            <ul className="space-y-2 text-sm text-zinc-600 dark:text-slate-400">
              {selectedFormatPreview.highlights.map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <span className="text-brand-500 mt-0.5">&bull;</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="card p-4">
            <h3 className="font-semibold text-zinc-900 dark:text-slate-100 mb-3">Report Contents</h3>
            <ul className="space-y-2 text-sm text-zinc-600 dark:text-slate-400">
              {[
                'Operational readiness score and trust summary',
                'Device information and network details',
                'Per-test result rows with detailed raw evidence',
                'Detailed findings for FAIL and ADVISORY results',
                'Saved synopsis narrative when one exists on the run',
              ].map(item => (
                <li key={item} className="flex items-start gap-2">
                  <span className="text-brand-500 mt-0.5">&bull;</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="card p-4">
            <h3 className="font-semibold text-zinc-900 dark:text-slate-100 mb-3">Verdict Legend</h3>
            <div className="space-y-1.5">
              {[
                { label: 'PASS', color: 'bg-green-500', desc: 'All tests passed' },
                { label: 'QUALIFIED PASS', color: 'bg-amber-500', desc: 'Essential pass, advisories noted' },
                { label: 'FAIL', color: 'bg-red-500', desc: 'Essential test(s) failed' },
              ].map(v => (
                <div key={v.label} className="flex items-center gap-2">
                  <div className={`w-2.5 h-2.5 rounded-full ${v.color}`} />
                  <span className="text-xs font-medium text-zinc-900 dark:text-slate-100 w-28">{v.label}</span>
                  <span className="text-xs text-zinc-500">{v.desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
