export function parseBoolean(value: string | undefined, fallback = false) {
  if (value === undefined) {
    return fallback
  }
  const normalized = value.trim().toLowerCase()
  if (['1', 'true', 'yes', 'on'].includes(normalized)) {
    return true
  }
  if (['0', 'false', 'no', 'off'].includes(normalized)) {
    return false
  }
  return fallback
}
