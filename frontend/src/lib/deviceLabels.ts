type DeviceIdentity = {
  predicted_name?: string | null
  device_name?: string | null
  name?: string | null
  hostname?: string | null
  ip_address?: string | null
  device_ip?: string | null
  manufacturer?: string | null
  device_manufacturer?: string | null
  model?: string | null
  device_model?: string | null
  mac_address?: string | null
  device_mac_address?: string | null
}

function uniqueParts(parts: Array<string | null | undefined>) {
  const seen = new Set<string>()
  const result: string[] = []

  for (const part of parts) {
    const clean = part?.trim()
    if (!clean) continue
    const key = clean.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    result.push(clean)
  }

  return result
}

export function getPreferredDeviceName(identity: DeviceIdentity): string {
  const combined = uniqueParts([
    identity.manufacturer || identity.device_manufacturer,
    identity.model || identity.device_model,
  ]).join(' ')

  return (
    identity.predicted_name?.trim()
    || identity.device_name?.trim()
    || combined
    || identity.hostname?.trim()
    || identity.name?.trim()
    || identity.ip_address?.trim()
    || identity.device_ip?.trim()
    || 'Unknown Device'
  )
}

export function getDeviceMetaSummary(
  identity: DeviceIdentity,
  options: { includeIp?: boolean; includeMac?: boolean } = {},
): string | null {
  const preferred = (
    identity.predicted_name?.trim()
    || identity.device_name?.trim()
    || ''
  ).toLowerCase()
  const manufacturer = identity.manufacturer || identity.device_manufacturer
  const model = identity.model || identity.device_model
  const combined = uniqueParts([manufacturer, model]).join(' ').toLowerCase()
  const parts = uniqueParts([
    combined && combined === preferred ? null : manufacturer,
    combined && combined === preferred ? null : model,
    options.includeIp ? identity.ip_address || identity.device_ip : null,
    options.includeMac ? identity.mac_address || identity.device_mac_address : null,
  ])

  return parts.length > 0 ? parts.join(' · ') : null
}
