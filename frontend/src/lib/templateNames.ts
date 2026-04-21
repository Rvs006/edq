export function normalizeTemplateName(name: string | null | undefined): string | null {
  if (!name) return null

  const trimmed = name.trim()
  if (!trimmed) return null

  if (trimmed === 'Universal (Smart Profiling)') return 'Full Security Assessment'

  return trimmed.replace(/\s+\(Dylan Template\)$/i, '')
}
