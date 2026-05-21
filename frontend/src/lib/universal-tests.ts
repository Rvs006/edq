/** Single source of truth for the 60 EDQ security tests.
 *  Imported by multiple pages instead of duplicating the test catalog. */

export interface UniversalTest {
  id: string
  name: string
  tier: 'automatic' | 'guided_manual'
  category: string
  essential: boolean
  deprecated?: boolean
}

export const UNIVERSAL_TESTS: UniversalTest[] = [
  { id: 'U01', name: 'Ping Response', tier: 'automatic', category: 'Network', essential: true },
  { id: 'U02', name: 'MAC Address Vendor Lookup', tier: 'automatic', category: 'Network', essential: true },
  { id: 'U03', name: 'Switch Negotiation', tier: 'automatic', category: 'Network', essential: false },
  { id: 'U04', name: 'DHCP Behaviour', tier: 'automatic', category: 'Network', essential: false },
  { id: 'U05', name: 'IPv6 Support Detection', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U06', name: 'TCP/UDP Port Scan', tier: 'automatic', category: 'Network', essential: true },
  { id: 'U07', name: 'UDP Port Scan (Merged into U06)', tier: 'automatic', category: 'Network', essential: false, deprecated: true },
  { id: 'U08', name: 'Service Version Detection', tier: 'automatic', category: 'Network', essential: false },
  { id: 'U09', name: 'Protocol Whitelist Compliance', tier: 'automatic', category: 'Network', essential: false },
  { id: 'U10', name: 'TLS Version Assessment', tier: 'automatic', category: 'TLS', essential: true },
  { id: 'U11', name: 'Cipher Suite Strength', tier: 'automatic', category: 'TLS', essential: false },
  { id: 'U12', name: 'Certificate Validity', tier: 'automatic', category: 'TLS', essential: false },
  { id: 'U13', name: 'HSTS Header Presence (Merged into U35)', tier: 'automatic', category: 'TLS', essential: false, deprecated: true },
  { id: 'U14', name: 'HTTP Security Headers (Merged into U35)', tier: 'automatic', category: 'Web', essential: false, deprecated: true },
  { id: 'U15', name: 'SSH Algorithm Assessment', tier: 'automatic', category: 'SSH', essential: false },
  { id: 'U16', name: 'Default Credential Check', tier: 'automatic', category: 'SSH', essential: true },
  { id: 'U17', name: 'Brute Force Protection', tier: 'automatic', category: 'SSH', essential: false },
  { id: 'U18', name: 'HTTP vs HTTPS Redirect', tier: 'automatic', category: 'Web', essential: false },
  { id: 'U19', name: 'OS Fingerprinting', tier: 'automatic', category: 'Network', essential: false },
  { id: 'U20', name: 'Network Disconnection Behaviour', tier: 'automatic', category: 'Network', essential: false },
  { id: 'U21', name: 'Web Interface Password Change', tier: 'guided_manual', category: 'Manual', essential: true },
  { id: 'U22', name: 'Firmware Update Mechanism', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U23', name: 'Session Timeout Validation', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U24', name: 'Physical Security (Reset/USB)', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U25', name: 'Manufacturer Security Docs', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U26', name: 'NTP Synchronisation Check', tier: 'automatic', category: 'Network', essential: true },
  { id: 'U27', name: '802.1x / EAP-TLS Support', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U28', name: 'BACnet/IP Discovery', tier: 'automatic', category: 'Network', essential: false },
  { id: 'U29', name: 'DNS Support Verification', tier: 'automatic', category: 'Network', essential: false },
  { id: 'U30', name: 'Password Policy Assessment', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U31', name: 'SNMP Version Check (Not Required)', tier: 'automatic', category: 'Network', essential: false, deprecated: true },
  { id: 'U32', name: 'UPnP/SSDP Exposure (Retired)', tier: 'automatic', category: 'Network', essential: false, deprecated: true },
  { id: 'U33', name: 'mDNS/Bonjour Exposure (Retired)', tier: 'automatic', category: 'Network', essential: false, deprecated: true },
  { id: 'U34', name: 'Telnet/Insecure Protocol Detection (Retired)', tier: 'automatic', category: 'Network', essential: true, deprecated: true },
  { id: 'U35', name: 'Web Server and HTTP Header Assessment', tier: 'automatic', category: 'Web', essential: false },
  { id: 'U36', name: 'Banner Grabbing / Info Leakage (Retired)', tier: 'guided_manual', category: 'Manual', essential: false, deprecated: true },
  { id: 'U37', name: 'RTSP Stream Authentication (Retired)', tier: 'automatic', category: 'Network', essential: false, deprecated: true },
  { id: 'U38', name: 'MQTT Support & Security', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U39', name: 'VLAN Tagging Support (Retired)', tier: 'guided_manual', category: 'Manual', essential: false, deprecated: true },
  { id: 'U40', name: 'API Authentication Check (Retired)', tier: 'guided_manual', category: 'Manual', essential: false, deprecated: true },
  { id: 'U41', name: 'Audit/Log Review (Retired)', tier: 'guided_manual', category: 'Manual', essential: false, deprecated: true },
  { id: 'U42', name: 'Data-at-Rest Encryption (Retired)', tier: 'guided_manual', category: 'Manual', essential: false, deprecated: true },
  { id: 'U43', name: 'End-of-Life / Vendor Support', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U44', name: 'Static IP Configuration', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U45', name: 'Hostname Resolution', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U46', name: 'Data Flow Analysis', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U47', name: 'x509 Certificate Replacement', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U48', name: 'BACnet PIC/BIBB Statement', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U49', name: 'MQTT Custom Payloads', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U50', name: 'MQTT Write-back Commands', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U51', name: 'MQTT Over TLS', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U52', name: 'MQTT Client Certificate Auth', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U53', name: 'MQTT Username/Password Auth', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U54', name: 'PKI Integration', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U55', name: 'Wi-Fi Standards Supported', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U56', name: 'Wi-Fi Disablement', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U57', name: 'Wi-Fi Encryption', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U58', name: 'PoE Standards Supported', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U59', name: 'SOAK Test (7-Day Stability)', tier: 'guided_manual', category: 'Manual', essential: false },
  { id: 'U60', name: 'Additional Information / Notes', tier: 'guided_manual', category: 'Manual', essential: false },
]

export const TEST_CATEGORIES = ['Network', 'TLS', 'SSH', 'Web', 'Manual'] as const

export const ACTIVE_UNIVERSAL_TESTS = UNIVERSAL_TESTS.filter((test) => !test.deprecated)

const SCENARIO_MANUAL_TEST_IDS: Record<string, Set<string>> = {
  test_lab: new Set(['U03', 'U20']),
  site_network: new Set(['U03', 'U04', 'U20', 'U26', 'U29']),
}
const DIRECT_SCENARIOS = new Set(['direct', 'direct_cable'])

export function getEffectiveTestTier(
  test: Pick<UniversalTest, 'id' | 'tier'>,
  scenario?: string | null,
): 'automatic' | 'guided_manual' {
  if (test.tier === 'guided_manual') return 'guided_manual'
  if (!scenario || DIRECT_SCENARIOS.has(scenario)) return test.tier
  return SCENARIO_MANUAL_TEST_IDS[scenario]?.has(test.id) ? 'guided_manual' : test.tier
}

export function formatConnectionScenarioLabel(scenario?: string | null): string {
  switch (scenario) {
    case 'direct':
    case 'direct_cable':
      return 'Scenario 1 - Direct Cable'
    case 'test_lab':
      return 'Scenario 2 - Test Lab'
    case 'site_network':
      return 'Scenario 3 - Site Network'
    default:
      return 'Scenario 2 - Test Lab'
  }
}
