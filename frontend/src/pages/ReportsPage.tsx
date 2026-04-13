import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { reportsApi, resolveApiUrl, testRunsApi, getApiErrorMessage } from '@/lib/api'
import type { TestRun, ReportTemplate } from '@/lib/types'
import { toLocalDateOnly } from '@/lib/testContracts'
import { Download, FileSpreadsheet, FileText, Loader2, LayoutTemplate, FileDown } from 'lucide-react'
import Callout from '@/components/common/Callout'
import toast from 'react-hot-toast'
import { getPreferredDeviceName } from '@/lib/deviceLabels'

const TEMPLATE_OPTIONS = [
  { key: 'generic', label: 'Generic IP Device (C00)', category: 'generic' },
  { key: 'pelco_camera', label: 'Pelco Camera (Rev 2)', category: 'camera' },
  { key: 'easyio_controller', label: 'EasyIO Controller', category: 'controller' },
]

type ReportFormat = 'excel' | 'word' | 'pdf' | 'csv'

type FormatGroup = {
  title: string
  description: string
  formats: { key: ReportFormat; label: string; ext: string; icon: typeof FileSpreadsheet }[]
}

export default function ReportsPage() {
  const [selectedRun, setSelectedRun] = useState('')
  const [reportType, setReportType] = useState<ReportFormat>('excel')
  const [templateKey, setTemplateKey] = useState('generic')
  const [includeSynopsis, setIncludeSynopsis] = useState(true)
  const [generating, setGenerating] = useState(false)

  const { data: runs, isError } = useQuery({
    queryKey: ['completed-runs'],
    queryFn: () => testRunsApi.list({ status: 'completed' }).then(r => r.data),
  })

  const { data: templates } = useQuery({
    queryKey: ['report-templates'],
    queryFn: () => reportsApi.templates().then(r => r.data),
  })

  const selectedRunDetails = runs?.find((run: TestRun) => run.id === selectedRun) || null
  const selectedReadiness = selectedRunDetails?.readiness_summary || null

  const triggerBlobDownload = (blobData: Blob, filename: string, mimeType: string) => {
    const blob = new Blob([blobData], { type: mimeType })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    // Small delay before cleanup to ensure download starts
    setTimeout(() => {
      URL.revokeObjectURL(url)
      document.body.removeChild(a)
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
      if (!data.filename && !data.download_url) {
        toast.error('Report generation returned no file. Check backend logs.')
        return
      }
      const mimeMap: Record<ReportFormat, string> = {
        excel: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        word: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        pdf: 'application/pdf',
        csv: 'text/csv',
      }
      const extensionMap: Record<ReportFormat, string> = {
        excel: 'xlsx',
        word: 'docx',
        pdf: 'pdf',
        csv: 'csv',
      }
      const downloadName = data.filename || `report-${selectedRun}.${extensionMap[reportType]}`

      toast.success(`Report generated: ${downloadName}`)

      try {
        if (!data.filename) throw new Error('No direct filename returned')
        const blob = await reportsApi.download(data.filename)
        triggerBlobDownload(blob.data, downloadName, mimeMap[reportType])
      } catch {
        // Blob download failed — try direct download as fallback (no navigation)
        const url = data.download_url
        if (!url) {
          toast.error('Download failed and no fallback URL available')
          return
        }
        const a = document.createElement('a')
        a.href = resolveApiUrl(url)
        a.download = downloadName
        a.style.display = 'none'
        document.body.appendChild(a)
        a.click()
        setTimeout(() => document.body.removeChild(a), 100)
      }
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, 'Report generation failed'))
    } finally {
      setGenerating(false)
    }
  }

  const availableTemplates = templates || TEMPLATE_OPTIONS

  const formatOptions: { key: ReportFormat; label: string; ext: string; icon: typeof FileSpreadsheet }[] = [
    { key: 'excel', label: 'Excel', ext: '.xlsx', icon: FileSpreadsheet },
    { key: 'word', label: 'Word', ext: '.docx', icon: FileText },
    { key: 'pdf', label: 'PDF', ext: '.pdf', icon: FileDown },
    { key: 'csv', label: 'CSV', ext: '.csv', icon: FileSpreadsheet },
  ]
  const formatGroups: FormatGroup[] = [
    {
      title: 'Spreadsheet Exports',
      description: 'Canonical workbook and flat data exports using the same template profile.',
      formats: formatOptions.filter((option) => option.key === 'excel' || option.key === 'csv'),
    },
    {
      title: 'Document Exports',
      description: 'Word and PDF outputs generated from the same run, template profile, and shared report model.',
      formats: formatOptions.filter((option) => option.key === 'word' || option.key === 'pdf'),
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
                {runs?.map((run: TestRun) => (
                <option key={run.id} value={run.id}>
                    {getPreferredDeviceName(run)} &mdash; {run.readiness_summary?.score ?? run.confidence ?? 1}/10 readiness &mdash; {toLocalDateOnly(run.created_at)}
                  </option>
                ))}
              </select>
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
                    {t.name || t.label}
                    {t.device_category ? ` (${t.device_category})` : ''}
                  </option>
                ))}
              </select>
              <p className="text-xs text-zinc-500 mt-1">
                The selected template profile now applies to Excel, CSV, Word, and PDF outputs.
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
                Include AI-generated synopsis (if available)
              </label>
            </div>

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
            <h3 className="font-semibold text-zinc-900 dark:text-slate-100 mb-3">Template Formats</h3>
            <div className="space-y-2">
              {[
                { name: 'Generic C00', desc: 'Universal IP device workbook with mapped rows reused across every export format.' },
                { name: 'Pelco Camera', desc: 'Camera qualification profile shared by Excel, CSV, Word, and PDF generation.' },
                { name: 'EasyIO Controller', desc: 'Controller profile aligned to the current EDQ workflow across all output types.' },
              ].map(fw => (
                <div key={fw.name} className="flex items-center gap-2 py-1">
                  <div className="w-2 h-2 rounded-full bg-brand-500" />
                  <div>
                    <p className="text-sm font-medium text-zinc-900 dark:text-slate-100">{fw.name}</p>
                    <p className="text-xs text-zinc-500">{fw.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card p-4">
            <h3 className="font-semibold text-zinc-900 dark:text-slate-100 mb-3">Report Contents</h3>
            <ul className="space-y-2 text-sm text-zinc-600 dark:text-slate-400">
              {[
                'Operational readiness score and trust summary',
                'Shared report model across Excel, Word, PDF, and CSV',
                'Selected template profile applied to all export types',
                'Branding and footer metadata carried into report outputs',
                'Executive summary with overall verdict',
                'Device information and network details',
                'Template-backed test-plan rows when a workbook mapping exists',
                'Detailed findings for FAIL and ADVISORY results',
                'Tool versions and connection scenario',
                'AI-generated narrative synopsis',
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
