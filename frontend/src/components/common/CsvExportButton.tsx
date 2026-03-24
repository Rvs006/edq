import { Download } from 'lucide-react'

interface CsvRow {
  test_number: string
  test_name: string
  tier: string
  verdict: string | null
  tool_used?: string | null
  essential_pass?: boolean
}

interface CsvExportButtonProps {
  results: CsvRow[]
  deviceName?: string
  className?: string
}

export default function CsvExportButton({ results, deviceName, className = '' }: CsvExportButtonProps) {
  const handleExport = () => {
    const headers = ['Test Number', 'Test Name', 'Tier', 'Verdict', 'Tool Used', 'Essential']
    const rows = results.map((r) => [
      r.test_number,
      `"${(r.test_name || '').replace(/"/g, '""')}"`,
      r.tier,
      r.verdict || 'pending',
      r.tool_used || '',
      r.essential_pass ? 'Yes' : 'No',
    ])

    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const timestamp = new Date().toISOString().slice(0, 10)
    const safeName = (deviceName || 'results').replace(/[^a-zA-Z0-9-_]/g, '_')
    a.download = `edq-${safeName}-${timestamp}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <button
      onClick={handleExport}
      disabled={results.length === 0}
      className={`btn-secondary text-xs ${className}`}
      title="Export results as CSV"
    >
      <Download className="w-3.5 h-3.5" />
      Export CSV
    </button>
  )
}
