export const MIN_SCAN_CIDR_PREFIX = 16
export const MAX_SCAN_CIDR_PREFIX = 32

export function isValidIpv4(value: string): boolean {
  const parts = value.trim().split('.')
  if (parts.length !== 4) return false
  return parts.every((part) => {
    if (!/^\d{1,3}$/.test(part)) return false
    const octet = Number(part)
    return Number.isInteger(octet) && octet >= 0 && octet <= 255
  })
}

export function parseIpv4Cidr(
  value: string,
  minPrefix = MIN_SCAN_CIDR_PREFIX,
  maxPrefix = MAX_SCAN_CIDR_PREFIX,
): {
  formatValid: boolean
  prefix: number
  prefixInRange: boolean
  hostCount: number
} {
  const trimmed = value.trim()
  const parts = trimmed.split('/')
  if (parts.length !== 2 || !isValidIpv4(parts[0]) || !/^\d{1,2}$/.test(parts[1])) {
    return { formatValid: false, prefix: 0, prefixInRange: false, hostCount: 0 }
  }

  const prefix = Number(parts[1])
  const prefixInRange = Number.isInteger(prefix) && prefix >= minPrefix && prefix <= maxPrefix
  const hostCount = prefixInRange
    ? prefix >= 31 ? Math.pow(2, 32 - prefix) : Math.pow(2, 32 - prefix) - 2
    : 0

  return { formatValid: true, prefix, prefixInRange, hostCount }
}

export function isValidIpv4Cidr(
  value: string,
  minPrefix = MIN_SCAN_CIDR_PREFIX,
  maxPrefix = MAX_SCAN_CIDR_PREFIX,
): boolean {
  const parsed = parseIpv4Cidr(value, minPrefix, maxPrefix)
  return parsed.formatValid && parsed.prefixInRange
}
