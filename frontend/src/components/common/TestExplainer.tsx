import { useState } from 'react'
import { ChevronDown, ChevronUp, Target, HelpCircle, CheckCircle2, XCircle } from 'lucide-react'

interface TestExplainerProps {
  testNumber: string
  testName: string
  description?: string | null
  passCriteria?: string | null
  toolUsed?: string | null
  className?: string
}

const TEST_EXPLAINERS: Record<string, { what: string; why: string; pass: string; fail: string }> = {
  U01: {
    what: 'Scans all 65,535 TCP ports to identify open services on the device.',
    why: 'Open ports expose potential attack surfaces. Unnecessary services should be disabled.',
    pass: 'Only expected ports are open (e.g., 80, 443 for a web-managed device).',
    fail: 'Unexpected ports are open that could be exploited (e.g., Telnet on port 23).',
  },
  U02: {
    what: 'Runs an SSL/TLS configuration audit using testssl.sh against HTTPS services.',
    why: 'Weak TLS configurations allow man-in-the-middle attacks and data interception.',
    pass: 'TLS 1.2+ with strong ciphers, valid certificate chain, no known vulnerabilities.',
    fail: 'Supports SSLv3/TLS 1.0, weak ciphers, expired certificates, or known TLS attacks.',
  },
  U03: {
    what: 'Audits the SSH server configuration using ssh-audit for protocol and key weaknesses.',
    why: 'Weak SSH configs can allow brute-force attacks or unauthorized access.',
    pass: 'SSH v2 only, strong key exchange, no weak MACs or ciphers.',
    fail: 'SSH v1 support, weak algorithms, or known vulnerable implementations.',
  },
  U04: {
    what: 'Tests for default/common credentials using Hydra password auditing tool.',
    why: 'Default credentials are the #1 attack vector for IoT and building devices.',
    pass: 'No default or common username/password combinations succeed.',
    fail: 'One or more default credential pairs grant access to the device.',
  },
  U05: {
    what: 'Runs Nikto web vulnerability scanner against HTTP/HTTPS services.',
    why: 'Web interfaces often have misconfigurations, outdated software, or known vulnerabilities.',
    pass: 'No critical findings; server headers are hardened; no directory listing.',
    fail: 'Critical vulnerabilities found, such as known CVEs or information disclosure.',
  },
  U08: {
    what: 'Performs service version detection to identify exact software versions running on open ports.',
    why: 'Known vulnerable versions can be matched against CVE databases for risk assessment.',
    pass: 'All services are running up-to-date, patched versions.',
    fail: 'Services running versions with known critical vulnerabilities.',
  },
}

export default function TestExplainer({ testNumber, testName, description, passCriteria, toolUsed, className = '' }: TestExplainerProps) {
  const [expanded, setExpanded] = useState(false)
  const explainer = TEST_EXPLAINERS[testNumber]

  const what = description || explainer?.what
  const pass = passCriteria || explainer?.pass
  const why = explainer?.why
  const fail = explainer?.fail

  if (!what && !pass) return null

  return (
    <div className={`border border-zinc-200 rounded-lg overflow-hidden ${className}`}>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left bg-zinc-50 hover:bg-zinc-100 transition-colors"
      >
        <HelpCircle className="w-4 h-4 text-zinc-400 shrink-0" />
        <span className="text-xs font-medium text-zinc-700 flex-1">
          What does this test do?
        </span>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-zinc-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-zinc-400" />
        )}
      </button>

      {expanded && (
        <div className="p-3 space-y-3 text-xs bg-white">
          {what && (
            <div className="flex gap-2">
              <Target className="w-3.5 h-3.5 text-blue-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-zinc-700">What: </span>
                <span className="text-zinc-600">{what}</span>
              </div>
            </div>
          )}
          {why && (
            <div className="flex gap-2">
              <HelpCircle className="w-3.5 h-3.5 text-purple-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-zinc-700">Why: </span>
                <span className="text-zinc-600">{why}</span>
              </div>
            </div>
          )}
          {pass && (
            <div className="flex gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-zinc-700">Pass: </span>
                <span className="text-zinc-600">{pass}</span>
              </div>
            </div>
          )}
          {fail && (
            <div className="flex gap-2">
              <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-zinc-700">Fail: </span>
                <span className="text-zinc-600">{fail}</span>
              </div>
            </div>
          )}
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
