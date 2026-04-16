import { describe, expect, it } from 'vitest'

import { hasDiscoverySignal } from '@/lib/discoverySignals'

describe('hasDiscoverySignal', () => {
  it('is false when no ports, no mac, no hostname', () => {
    expect(hasDiscoverySignal({ open_ports: null, mac_address: null, hostname: null })).toBe(false)
    expect(hasDiscoverySignal({ open_ports: [], mac_address: null, hostname: null })).toBe(false)
    expect(hasDiscoverySignal({ open_ports: undefined, mac_address: '', hostname: '' })).toBe(false)
  })

  it('is true when there is at least one open port', () => {
    expect(hasDiscoverySignal({
      open_ports: [{ port: 80, protocol: 'tcp', service: 'http' }],
      mac_address: null,
      hostname: null,
    })).toBe(true)
  })

  it('is true when a MAC address is present', () => {
    expect(hasDiscoverySignal({ open_ports: null, mac_address: 'AA:BB:CC:DD:EE:FF', hostname: null })).toBe(true)
  })

  it('is true when a hostname is present', () => {
    expect(hasDiscoverySignal({ open_ports: null, mac_address: null, hostname: 'cam-lobby-01' })).toBe(true)
  })
})
