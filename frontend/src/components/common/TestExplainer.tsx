import { useState } from 'react'
import { ChevronDown, ChevronUp, Target, HelpCircle, CheckCircle2, XCircle } from 'lucide-react'

interface TestExplainerProps {
  testNumber: string
  testName: string
  description?: string | null
  passCriteria?: string | null
  toolUsed?: string | null
  tier?: string | null
  className?: string
}

const TEST_EXPLAINERS: Record<string, { what: string; why: string; pass: string; fail: string }> = {
  U01: {
    what: 'Sends ICMP echo requests (ping) to verify the device is reachable on the network.',
    why: 'Basic reachability must be confirmed before any other tests can run.',
    pass: 'Device responds to ping — network connectivity confirmed.',
    fail: 'No ping response. Device may be offline, IP incorrect, or ICMP blocked by firewall.',
  },
  U02: {
    what: 'Looks up the device MAC address against the IEEE OUI database to identify the manufacturer.',
    why: 'Confirming the manufacturer helps verify you are testing the correct device.',
    pass: 'MAC address found and vendor identified.',
    fail: 'MAC address not in OUI database — manufacturer could not be confirmed.',
  },
  U03: {
    what: 'Checks Ethernet link speed and duplex negotiation between the device and the switch.',
    why: 'Misconfigured link settings (e.g., half-duplex) can cause packet loss and instability.',
    pass: 'Link negotiated at expected speed and full duplex.',
    fail: 'Half-duplex detected or speed mismatch with switch port configuration.',
  },
  U04: {
    what: 'Determines whether the device uses DHCP for automatic IP assignment or a static IP.',
    why: 'Understanding IP assignment helps assess network management and re-addressing risks.',
    pass: 'DHCP lease confirmed — device accepts automatic IP assignment.',
    fail: 'Could not determine DHCP behaviour — check device network settings manually.',
  },
  U05: {
    what: 'Probes the device to check if IPv6 is enabled and responding.',
    why: 'Unmanaged IPv6 interfaces can bypass IPv4-only firewall rules and create hidden attack surfaces.',
    pass: 'IPv6 status determined — either enabled (for awareness) or disabled.',
    fail: 'IPv6 is active but may not be managed by network policy.',
  },
  U06: {
    what: 'Scans all 65,535 TCP ports to discover every open service on the device.',
    why: 'Open ports are potential entry points. Unnecessary services should be disabled to reduce risk.',
    pass: 'Only expected ports are open (e.g., 80/443 for web-managed devices).',
    fail: 'Unexpected ports found that could be exploited (e.g., Telnet on port 23).',
  },
  U07: {
    what: 'Scans the top 100 most common UDP ports for open services.',
    why: 'UDP services (SNMP, NTP, DNS) are often overlooked but can be exploited for amplification attacks.',
    pass: 'Only expected UDP ports are open.',
    fail: 'Unexpected UDP services found that should be reviewed.',
  },
  U08: {
    what: 'Identifies exact software versions running on each open port (e.g., nginx 1.29.7).',
    why: 'Known vulnerable versions can be matched against CVE databases for risk assessment.',
    pass: 'Service versions identified for documentation and vulnerability tracking.',
    fail: 'Service versions could not be determined — manual investigation needed.',
  },
  U09: {
    what: 'Compares discovered open ports against the approved protocol whitelist for your organisation.',
    why: 'Only pre-approved services should be running. Non-whitelisted ports indicate policy violations.',
    pass: 'All open ports match the approved whitelist.',
    fail: 'Non-whitelisted ports found — disable them or add to whitelist with justification.',
  },
  U10: {
    what: 'Tests which TLS protocol versions the HTTPS service supports (TLS 1.0, 1.1, 1.2, 1.3).',
    why: 'TLS 1.0 and 1.1 have known vulnerabilities. Only TLS 1.2+ should be accepted.',
    pass: 'Only TLS 1.2 or 1.3 supported — secure configuration.',
    fail: 'Weak TLS versions (1.0/1.1 or SSLv3) accepted — disable them in the web server.',
  },
  U11: {
    what: 'Evaluates the cipher suites offered by the TLS service for cryptographic strength.',
    why: 'Weak ciphers (RC4, DES, NULL) can be broken, allowing traffic decryption.',
    pass: 'All cipher suites are strong (AES-GCM, ChaCha20, etc.).',
    fail: 'Weak or deprecated ciphers found — update TLS configuration to remove them.',
  },
  U12: {
    what: 'Checks the TLS certificate for expiry date, chain validity, and trust status.',
    why: 'Expired or self-signed certificates cause browser warnings and may indicate a compromised connection.',
    pass: 'Certificate is valid, trusted, and not expired.',
    fail: 'Certificate is expired, self-signed, or has chain issues — replace it.',
  },
  U13: {
    what: 'Checks for the Strict-Transport-Security (HSTS) header in HTTPS responses.',
    why: 'Without HSTS, browsers can be tricked into using plain HTTP, exposing traffic to interception.',
    pass: 'HSTS header present — browsers will enforce HTTPS-only connections.',
    fail: 'HSTS header missing — add it to prevent protocol downgrade attacks.',
  },
  U14: {
    what: 'Checks HTTP responses for security headers: CSP, X-Frame-Options, X-Content-Type-Options, etc.',
    why: 'Missing security headers leave the web interface vulnerable to XSS, clickjacking, and MIME attacks.',
    pass: 'All recommended security headers are present and correctly configured.',
    fail: 'One or more security headers are missing or misconfigured.',
  },
  U15: {
    what: 'Audits the SSH server for protocol version, key exchange, cipher, and MAC algorithm strength.',
    why: 'Weak SSH algorithms can allow brute-force attacks or session hijacking.',
    pass: 'SSH v2 only, with strong key exchange, ciphers, and MACs.',
    fail: 'Weak algorithms found (e.g., SSH v1, DES, MD5) — update SSH server configuration.',
  },
  U16: {
    what: 'Attempts login using common default credentials (admin/admin, root/root, etc.) on all services.',
    why: 'Default credentials are the #1 attack vector for IoT and building automation devices.',
    pass: 'No default credential pairs succeeded — device uses custom passwords.',
    fail: 'Default credentials work — change the password immediately.',
  },
  U17: {
    what: 'Sends rapid login attempts to check if the device locks out or rate-limits after failures.',
    why: 'Without brute-force protection, attackers can try thousands of passwords automatically.',
    pass: 'Account lockout or rate limiting detected after repeated failed logins.',
    fail: 'No lockout detected — the device may be vulnerable to brute-force attacks.',
  },
  U18: {
    what: 'Tests whether HTTP (port 80) requests are automatically redirected to HTTPS (port 443).',
    why: 'Without redirection, users may unknowingly send credentials over unencrypted HTTP.',
    pass: 'HTTP correctly redirects to HTTPS.',
    fail: 'HTTP does not redirect — configure the web server to redirect port 80 to 443.',
  },
  U19: {
    what: 'Uses nmap OS fingerprinting to identify the device operating system and version.',
    why: 'Knowing the OS helps assess patch status and identify OS-specific vulnerabilities.',
    pass: 'OS identified — recorded for documentation.',
    fail: 'OS could not be determined — the device may block fingerprinting probes.',
  },
  U20: {
    what: 'Physically disconnect and reconnect the network cable, observing how the device recovers.',
    why: 'Devices must recover gracefully from network interruptions without losing configuration.',
    pass: 'Device reconnects automatically with same IP and settings within a reasonable time.',
    fail: 'Device fails to reconnect, loses settings, or requires a manual reboot.',
  },
  U21: {
    what: 'Log in to the web interface and attempt to change the device password.',
    why: 'Users must be able to change default passwords to secure the device after deployment.',
    pass: 'Password changed successfully via the web interface.',
    fail: 'Cannot change password — device may be stuck with default credentials.',
  },
  U22: {
    what: 'Check how firmware updates are delivered and applied (manual upload, auto-update, etc.).',
    why: 'Devices without a clear update mechanism may never receive security patches.',
    pass: 'Firmware update mechanism exists and is documented by the manufacturer.',
    fail: 'No update mechanism found — device may become permanently vulnerable.',
  },
  U23: {
    what: 'Log in to the web interface, wait without activity, and check if the session expires.',
    why: 'Sessions that never expire allow attackers to hijack abandoned browser tabs.',
    pass: 'Session times out after a reasonable period of inactivity (e.g., 15-30 minutes).',
    fail: 'Session never expires — configure session timeout in device settings.',
  },
  U24: {
    what: 'Inspect the device for physical reset buttons, USB ports, serial consoles, and debug interfaces.',
    why: 'Exposed physical interfaces can allow an attacker with physical access to bypass all security.',
    pass: 'No exposed debug interfaces, or they are documented and can be disabled.',
    fail: 'Unprotected reset button, USB, or JTAG port found — assess physical access risk.',
  },
  U25: {
    what: 'Check if the manufacturer provides a security hardening guide for this device.',
    why: 'Without vendor guidance, engineers may miss critical security configuration steps.',
    pass: 'Manufacturer provides security documentation (hardening guide, security advisories).',
    fail: 'No security documentation available from the manufacturer.',
  },
  U26: {
    what: 'Checks if the device has NTP (port 123) enabled for network time synchronisation.',
    why: 'Accurate time is critical for log correlation, certificate validation, and scheduled operations.',
    pass: 'NTP service detected — device can synchronise time with a network server.',
    fail: 'No NTP service — device clock may drift, affecting logs and certificates.',
  },
  U27: {
    what: 'Check device settings for 802.1x / EAP-TLS network access control support.',
    why: '802.1x prevents unauthorised devices from connecting to the network.',
    pass: 'Device supports 802.1x authentication.',
    fail: 'No 802.1x support — device cannot participate in port-based access control.',
  },
  U28: {
    what: 'Probes port 47808 to detect BACnet/IP building automation services.',
    why: 'BACnet traffic should be isolated to the BAS VLAN. Unexpected exposure is a risk.',
    pass: 'BACnet status determined — present or absent, recorded for documentation.',
    fail: 'BACnet exposed on an unexpected network segment.',
  },
  U29: {
    what: 'Checks if the device runs a DNS service or supports DNS resolution.',
    why: 'DNS configuration affects how the device resolves hostnames for updates and NTP.',
    pass: 'DNS status determined and recorded.',
    fail: 'DNS configuration could not be verified.',
  },
  U30: {
    what: 'Assess password complexity requirements: minimum length, character rules, history.',
    why: 'Weak password policies allow easily-guessed credentials.',
    pass: 'Device enforces reasonable password complexity (8+ chars, mixed case/numbers).',
    fail: 'No password policy — device accepts trivially simple passwords.',
  },
  U31: {
    what: 'Detects SNMP services and checks if insecure versions (v1/v2c) are enabled.',
    why: 'SNMP v1/v2c transmit community strings in cleartext — easily intercepted.',
    pass: 'Only SNMPv3 detected, or no SNMP service running.',
    fail: 'SNMP v1/v2c found — upgrade to SNMPv3 with authentication and encryption.',
  },
  U32: {
    what: 'Checks for UPnP/SSDP services on port 1900.',
    why: 'UPnP can automatically open firewall ports and expose internal services to the network.',
    pass: 'No UPnP/SSDP service detected.',
    fail: 'UPnP is active — disable it unless specifically required.',
  },
  U33: {
    what: 'Checks for mDNS/Bonjour services on port 5353.',
    why: 'mDNS broadcasts device information to the local network, aiding attacker reconnaissance.',
    pass: 'No mDNS/Bonjour service detected.',
    fail: 'mDNS is active — disable it to prevent information leakage.',
  },
  U34: {
    what: 'Scans for Telnet (port 23), FTP (port 21), and other cleartext protocols.',
    why: 'Telnet and FTP transmit credentials in plain text — trivially intercepted on the network.',
    pass: 'No insecure cleartext protocols detected.',
    fail: 'Telnet/FTP found — disable them and use SSH/SFTP instead.',
  },
  U35: {
    what: 'Runs the Nikto web vulnerability scanner against the device HTTP/HTTPS service.',
    why: 'Web interfaces often have misconfigurations, outdated software, or known vulnerabilities.',
    pass: 'No significant vulnerabilities found by Nikto.',
    fail: 'Vulnerabilities found — review findings and patch or reconfigure the web server.',
  },
  U36: {
    what: 'Examines service banners on all open ports for version strings, internal IPs, or debug info.',
    why: 'Leaked version numbers help attackers find matching CVE exploits. Internal IPs reveal network layout.',
    pass: 'No sensitive information found in service banners.',
    fail: 'Banners reveal software versions or internal details — configure services to suppress them.',
  },
  U37: {
    what: 'Tests whether RTSP video streams (port 554) can be accessed without authentication.',
    why: 'Unauthenticated RTSP allows anyone on the network to view camera feeds.',
    pass: 'RTSP stream requires authentication before access is granted.',
    fail: 'Stream accessible without credentials — enable RTSP authentication immediately.',
  },
  U38: {
    what: 'Check if the device supports MQTT and whether TLS and authentication are enforced.',
    why: 'Unsecured MQTT allows interception and spoofing of sensor/control messages.',
    pass: 'MQTT uses TLS encryption and requires authentication.',
    fail: 'MQTT unencrypted or allows anonymous connections.',
  },
  U39: {
    what: 'Check device settings for 802.1Q VLAN tagging support.',
    why: 'VLAN tagging enables network segmentation, isolating building systems from IT traffic.',
    pass: 'Device supports VLAN tagging and can be assigned to a dedicated VLAN.',
    fail: 'No VLAN support — device cannot be network-segmented.',
  },
  U40: {
    what: 'Test all API endpoints with and without authentication tokens/credentials.',
    why: 'Unauthenticated APIs allow remote control or data extraction without authorisation.',
    pass: 'All API endpoints require valid authentication.',
    fail: 'One or more endpoints accessible without credentials.',
  },
  U41: {
    what: 'Review the device audit log for security events (logins, config changes, failures).',
    why: 'Without logs, security incidents cannot be detected or investigated after the fact.',
    pass: 'Logging is enabled and captures security-relevant events.',
    fail: 'No logging capability, or logs are empty/insufficient.',
  },
  U42: {
    what: 'Check if stored data (recordings, configs, credentials) is encrypted on the device.',
    why: 'If the device is stolen or decommissioned, unencrypted data can be extracted from storage.',
    pass: 'Stored data is encrypted or the device stores no sensitive data.',
    fail: 'Sensitive data stored in cleartext — enable encryption or document the risk.',
  },
  U43: {
    what: 'Verify the device is not end-of-life and the manufacturer provides active security patches.',
    why: 'End-of-life devices receive no security updates, leaving known vulnerabilities unpatched forever.',
    pass: 'Device is actively supported with documented security patch process.',
    fail: 'Device is end-of-life or manufacturer provides no security updates.',
  },
}

export default function TestExplainer({ testNumber, testName, description, passCriteria, toolUsed, tier, className = '' }: TestExplainerProps) {
  const [expanded, setExpanded] = useState(false)
  const explainer = TEST_EXPLAINERS[testNumber]

  const what = description || explainer?.what
  const pass = passCriteria || explainer?.pass
  const why = explainer?.why
  const fail = explainer?.fail

  if (!what && !pass) return null

  return (
    <div className={`border border-zinc-200 dark:border-slate-700/50 rounded-lg overflow-hidden ${className}`}>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left bg-zinc-50 dark:bg-slate-800 hover:bg-zinc-100 dark:hover:bg-slate-700 transition-colors"
      >
        <HelpCircle className="w-4 h-4 text-zinc-400 shrink-0" />
        <span className="text-xs font-medium text-zinc-700 dark:text-slate-300 flex-1">
          What does this test do?
        </span>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-zinc-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-zinc-400" />
        )}
      </button>

      {expanded && (
        <div className="p-3 space-y-3 text-xs bg-white dark:bg-slate-900/40">
          {what && (
            <div className="flex gap-2">
              <Target className="w-3.5 h-3.5 text-blue-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-zinc-700 dark:text-slate-200">What: </span>
                <span className="text-zinc-600 dark:text-slate-400">{what}</span>
              </div>
            </div>
          )}
          {why && (
            <div className="flex gap-2">
              <HelpCircle className="w-3.5 h-3.5 text-purple-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-zinc-700 dark:text-slate-200">Why: </span>
                <span className="text-zinc-600 dark:text-slate-400">{why}</span>
              </div>
            </div>
          )}
          {pass && (
            <div className="flex gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-zinc-700 dark:text-slate-200">Pass: </span>
                <span className="text-zinc-600 dark:text-slate-400">{pass}</span>
              </div>
            </div>
          )}
          {fail && (
            <div className="flex gap-2">
              <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-zinc-700 dark:text-slate-200">Fail: </span>
                <span className="text-zinc-600 dark:text-slate-400">{fail}</span>
              </div>
            </div>
          )}
          <div className="flex gap-2">
            <HelpCircle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
            <div>
              <span className="font-medium text-zinc-700 dark:text-slate-200">How to use it: </span>
              <span className="text-zinc-600 dark:text-slate-400">
                {tier === 'guided_manual'
                  ? 'Read the steps below, perform the check on the real device, then record Pass, Fail, Advisory, or N/A with notes that explain what you saw.'
                  : 'Watch the terminal output and parsed findings together. Use the pass/fail text above to decide whether the result looks expected before moving on.'}
              </span>
            </div>
          </div>
          {toolUsed && (
            <p className="text-[10px] text-zinc-400 pt-1 border-t border-zinc-100">
              Tool: <span className="font-mono">{toolUsed}</span>
            </p>
          )}
        </div>
      )}
    </div>
  )
}
