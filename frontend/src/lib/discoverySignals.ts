import type { DiscoveredDevice } from '@/lib/types'

export function hasDiscoverySignal(dev: Pick<DiscoveredDevice, 'open_ports' | 'mac_address' | 'hostname'>): boolean {
  return (dev.open_ports?.length ?? 0) > 0 || !!dev.mac_address || !!dev.hostname
}
