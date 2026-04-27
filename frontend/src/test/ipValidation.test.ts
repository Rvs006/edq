import { describe, expect, it } from 'vitest'

import { isValidIpv4, isValidIpv4Cidr, parseIpv4Cidr } from '@/lib/ipValidation'

describe('IP validation helpers', () => {
  it('validates IPv4 octets strictly', () => {
    expect(isValidIpv4('192.168.4.64')).toBe(true)
    expect(isValidIpv4('999.168.4.64')).toBe(false)
    expect(isValidIpv4('192.168.4')).toBe(false)
  })

  it('enforces scan CIDR prefix limits', () => {
    expect(isValidIpv4Cidr('192.168.4.64/32')).toBe(true)
    expect(isValidIpv4Cidr('192.168.0.0/16')).toBe(true)
    expect(isValidIpv4Cidr('192.168.0.0/15')).toBe(false)
    expect(isValidIpv4Cidr('999.168.0.0/24')).toBe(false)
  })

  it('reports host counts for valid scan ranges', () => {
    expect(parseIpv4Cidr('192.168.4.64/32').hostCount).toBe(1)
    expect(parseIpv4Cidr('192.168.4.0/30').hostCount).toBe(2)
  })
})
