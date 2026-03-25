import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { reportsApi, testRunsApi } from '@/lib/api'
import type { TestRun, ReportTemplate } from '@/lib/types'
import { Download, FileSpreadsheet, FileText, Loader2, LayoutTemplate, FileDown } from 'lucide-react'
import toast from 'react-hot-toast'

const TEMPLATE_OPTIONS = [
  { key: 'generic', label: 'Generic IP Device (C00)', category: 'generic' },
  { key: 'pelco_camera', label: 'Pelco Camera (Rev 2)', category: 'camera' },
  { key: 'easyio_controller', label: 'EasyIO Controller (FW08)', category: 'controller' },
]

type ReportFormat = 'excel' | 'word' | 'pdf'

export default function ReportsPage() {
  const [selectedRun, setSelectedRun] = useState('')
  const [reportType, setReportType] = useState<ReportFormat>('excel')
  const [templateKey, setTemplateKey] = useState('generic')
  const [includeSynopsis, setIncludeSynopsis] = useState(true)
  const [generating, setGenerating] = useState(false)

  const { data: runs } = useQuery({
    queryKey: ['completed-runs'],
    queryFn: () => testRunsApi.list({ status: 'completed' }).then(r => r.data),
  })

  const { data: templates } = useQuery({
    queryKey: ['report-templates'],
    queryFn: () => reportsApi.templates().then(r => r.data),
  })

  const handleGenerate = async () => {
    if (!selectedRun) { toast.error('Select a test run'); return }
    setGenerating(true)
    try {
      const { data } = await reportsApi.generate({
        test_run_id: selectedRun,
        report_type: reportType,
        include_synopsis: includeSynopsis,
        template_key: reportType === 'excel' ? templateKey : undefined,
      })
      toast.success(`Report generated: ${data.filename}`)
      if (data.download_url) {
        const mimeMap: Record<ReportFormat, string> = {
          excel: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          word: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          pdf: 'application/pdf',
        }
        try {
          const blob = await reportsApi.download(data.filename)
          const url = URL.createObjectURL(new Blob([blob.data], { type: mimeMap[reportType] }))
          const a = document.createElement('a')
          a.href = url
          a.download = data.filename
          a.click()
          URL.revokeObjectURL(url)
        } catch {
          window.open(data.download_url, '_blank')
        }
      }
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      toast.error(axiosErr.response?.data?.detail || 'Report generation failed')
    } finally {
      setGenerating(false)
    }
  }

  const availableTemplates = templates || TEMPLATE_OPTIONS

  const formatOptions: { key: ReportFormat; label: string; ext: string; icon: typeof FileSpreadsheet }[] = [
    { key: 'excel', label: 'Excel', ext: '.xlsx', icon: FileSpreadsheet },
    { key: 'word', label: 'Word', ext: '.docx', icon: FileText },
    { key: 'pdf', label: 'PDF', ext: '.pdf', icon: FileDown },
  ]

  return (
    <div className="page-container">
      <div className="mb-5">
        <h1 className="section-title">Reports</h1>
        <p className="section-subtitle">Generate Excel, Word, and PDF qualification reports from test results</p>
      </div>

      <div data-tour="report-form" className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 card p-5">
          <h2 className="font-semibold text-zinc-900 dark:text-slate-100 mb-4">Generate Report</h2>

          <div className="space-y-4">
            <div>
              <label className="label">Test Run</label>
              <select value={selectedRun} onChange={(e) => setSelectedRun(e.target.value)} className="input">
                <option value="">Select a completed test run...</option>
                {runs?.map((run: TestRun) => (
                  <option key={run.id} value={run.id}>
                    Run {run.id.slice(0, 8)} &mdash; {run.passed_tests}/{run.total_tests} passed &mdash; {new Date(run.created_at).toLocaleDateString()}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="label">Report Format</label>
              <div className="grid grid-cols-3 gap-3">
                {formatOptions.map(({ key, label, ext, icon: Icon }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setReportType(key)}
                    className={`flex items-center gap-3 p-4 rounded-lg border transition-colors ${
                      reportType === key
                        ? 'border-brand-500 bg-brand-50'
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

            {reportType === 'excel' && (
              <div>
                <label className="label flex items-center gap-2">
                  <LayoutTemplate className="w-4 h-4 text-zinc-400" />
                  Report Template
                </label>
                <select value={templateKey} onChange={(e) => setTemplateKey(e.target.value)} className="input">
                  {availableTemplates.map((t: ReportTemplate) => (
                    <option key={t.key} value={t.key}>
                      {t.name || t.label}
                      {t.device_category ? ` (${t.device_category})` : ''}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-zinc-500 mt-1">
                  Select the Electracom template matching the device type.
                </p>
              </div>
            )}

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

            <button onClick={handleGenerate} disabled={generating || !selectedRun}
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 active:bg-green-800 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-green-500/50 disabled:opacity-50 disabled:cursor-not-allowed"
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
                { name: 'Generic C00', desc: 'Universal IP device template (43 tests)' },
                { name: 'Pelco Camera', desc: 'Camera qualification Rev 2 (31 tests)' },
                { name: 'EasyIO FW08', desc: 'Controller testing plan v1.1 (46 tests)' },
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
                'Executive summary with overall verdict',
                'Device information and network details',
                'Individual test results with findings',
                'Protocol whitelist comparison',
                'Detailed findings for FAIL/ADVISORY tests',
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
