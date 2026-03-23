import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { reportsApi, testRunsApi } from '@/lib/api'
import { Download, FileSpreadsheet, FileText, Loader2, LayoutTemplate } from 'lucide-react'
import toast from 'react-hot-toast'

const TEMPLATE_OPTIONS = [
  { key: 'generic', label: 'Generic IP Device (C00)', category: 'generic' },
  { key: 'pelco_camera', label: 'Pelco Camera (Rev 2)', category: 'camera' },
  { key: 'easyio_controller', label: 'EasyIO Controller (FW08)', category: 'controller' },
]

export default function ReportsPage() {
  const [selectedRun, setSelectedRun] = useState('')
  const [reportType, setReportType] = useState<'excel' | 'word'>('excel')
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
        window.open(data.download_url, '_blank')
      }
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Report generation failed')
    } finally {
      setGenerating(false)
    }
  }

  const availableTemplates = templates || TEMPLATE_OPTIONS

  return (
    <div className="page-container">
      <div className="mb-5">
        <h1 className="section-title">Reports</h1>
        <p className="section-subtitle">Generate Excel and Word qualification reports from test results</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Report Generator */}
        <div className="lg:col-span-2 card p-5">
          <h2 className="font-semibold text-slate-900 mb-4">Generate Report</h2>

          <div className="space-y-4">
            <div>
              <label className="label">Test Run</label>
              <select value={selectedRun} onChange={(e) => setSelectedRun(e.target.value)} className="input">
                <option value="">Select a completed test run...</option>
                {runs?.map((run: any) => (
                  <option key={run.id} value={run.id}>
                    Run {run.id.slice(0, 8)} — {run.passed_tests}/{run.total_tests} passed — {new Date(run.created_at).toLocaleDateString()}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="label">Report Format</label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setReportType('excel')}
                  className={`flex items-center gap-3 p-4 rounded-lg border-2 transition-colors ${
                    reportType === 'excel'
                      ? 'border-brand-500 bg-brand-50'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <FileSpreadsheet className={`w-6 h-6 ${reportType === 'excel' ? 'text-brand-500' : 'text-slate-400'}`} />
                  <div className="text-left">
                    <p className="text-sm font-semibold text-slate-900">Excel</p>
                    <p className="text-xs text-slate-500">.xlsx format</p>
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => setReportType('word')}
                  className={`flex items-center gap-3 p-4 rounded-lg border-2 transition-colors ${
                    reportType === 'word'
                      ? 'border-brand-500 bg-brand-50'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <FileText className={`w-6 h-6 ${reportType === 'word' ? 'text-brand-500' : 'text-slate-400'}`} />
                  <div className="text-left">
                    <p className="text-sm font-semibold text-slate-900">Word</p>
                    <p className="text-xs text-slate-500">.docx format</p>
                  </div>
                </button>
              </div>
            </div>

            {reportType === 'excel' && (
              <div>
                <label className="label flex items-center gap-2">
                  <LayoutTemplate className="w-4 h-4 text-slate-400" />
                  Report Template
                </label>
                <select
                  value={templateKey}
                  onChange={(e) => setTemplateKey(e.target.value)}
                  className="input"
                >
                  {availableTemplates.map((t: any) => (
                    <option key={t.key} value={t.key}>
                      {t.name || t.label}
                      {t.device_category ? ` (${t.device_category})` : ''}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-slate-500 mt-1">
                  Select the Electracom template matching the device type. The report will use the original template formatting.
                </p>
              </div>
            )}

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="synopsis"
                checked={includeSynopsis}
                onChange={(e) => setIncludeSynopsis(e.target.checked)}
                className="w-4 h-4 rounded border-slate-300 text-brand-500 focus:ring-brand-500"
              />
              <label htmlFor="synopsis" className="text-sm text-slate-700">
                Include AI-generated synopsis (if available)
              </label>
            </div>

            <button onClick={handleGenerate} disabled={generating || !selectedRun} className="btn-primary">
              {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
              {generating ? 'Generating...' : 'Generate Report'}
            </button>
          </div>
        </div>

        {/* Report Info */}
        <div className="space-y-4">
          <div className="card p-4">
            <h3 className="font-semibold text-slate-900 mb-3">Report Contents</h3>
            <ul className="space-y-2 text-sm text-slate-600">
              <li className="flex items-start gap-2">
                <span className="text-brand-500 mt-0.5">•</span>
                Executive summary with overall verdict
              </li>
              <li className="flex items-start gap-2">
                <span className="text-brand-500 mt-0.5">•</span>
                Device information and network details
              </li>
              <li className="flex items-start gap-2">
                <span className="text-brand-500 mt-0.5">•</span>
                Individual test results with findings
              </li>
              <li className="flex items-start gap-2">
                <span className="text-brand-500 mt-0.5">•</span>
                Compliance mapping (ISO 27001, CE, SOC2)
              </li>
              <li className="flex items-start gap-2">
                <span className="text-brand-500 mt-0.5">•</span>
                AI-generated narrative synopsis
              </li>
              <li className="flex items-start gap-2">
                <span className="text-brand-500 mt-0.5">•</span>
                Recommendations and remediation steps
              </li>
            </ul>
          </div>

          <div className="card p-4">
            <h3 className="font-semibold text-slate-900 mb-3">Template Formats</h3>
            <div className="space-y-2">
              {[
                { name: 'Generic C00', desc: 'Universal IP device template (43 tests)' },
                { name: 'Pelco Camera', desc: 'Camera qualification Rev 2 (31 tests)' },
                { name: 'EasyIO FW08', desc: 'Controller testing plan v1.1 (46 tests)' },
              ].map(fw => (
                <div key={fw.name} className="flex items-center gap-2 py-1">
                  <div className="w-2 h-2 rounded-full bg-brand-500" />
                  <div>
                    <p className="text-sm font-medium text-slate-900">{fw.name}</p>
                    <p className="text-xs text-slate-500">{fw.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card p-4">
            <h3 className="font-semibold text-slate-900 mb-3">Compliance Frameworks</h3>
            <div className="space-y-2">
              {[
                { name: 'ISO 27001', desc: 'Information security management' },
                { name: 'Cyber Essentials', desc: 'UK government security standard' },
                { name: 'SOC2', desc: 'Service organisation controls' },
              ].map(fw => (
                <div key={fw.name} className="flex items-center gap-2 py-1">
                  <div className="w-2 h-2 rounded-full bg-brand-500" />
                  <div>
                    <p className="text-sm font-medium text-slate-900">{fw.name}</p>
                    <p className="text-xs text-slate-500">{fw.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
