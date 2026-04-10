/**
 * TopologyMap -- SVG-based network topology visualization.
 *
 * Pure SVG, zero external graph dependencies. Devices are grouped by /24 subnet
 * and arranged in clusters around a central gateway node.
 *
 * Visual encoding:
 *   - Node fill color reflects device category
 *   - Node border (stroke) reflects last_verdict (green=pass, red=fail, gray=untested)
 *   - Node radius scales with the number of open ports
 *   - Hover shows a tooltip with device name and IP
 *   - Click navigates to the device detail page
 */

import { useMemo, useState, useCallback, useRef, useEffect } from 'react'
import type { Device } from '@/lib/types'
import { getPreferredDeviceName } from '@/lib/deviceLabels'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface TopologyMapProps {
  devices: Device[]
  onDeviceClick?: (device: Device) => void
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SVG_WIDTH = 900
const SVG_HEIGHT = 620

const CATEGORY_COLORS: Record<string, string> = {
  camera: '#3b82f6',        // blue
  controller: '#22c55e',    // green
  intercom: '#06b6d4',      // cyan
  access_panel: '#f97316',  // orange
  access_control: '#f97316', // orange alias
  lighting: '#eab308',      // yellow
  hvac: '#0ea5e9',          // sky
  iot_sensor: '#a855f7',    // purple
  sensor: '#a855f7',        // purple alias
  meter: '#f59e0b',         // amber
  switch: '#eab308',        // yellow
  gateway: '#ec4899',       // pink
  other: '#6b7280',         // gray
  unknown: '#6b7280',       // gray
}

const VERDICT_STROKES: Record<string, string> = {
  pass: '#16a34a',
  qualified: '#16a34a',
  fail: '#dc2626',
  failed: '#dc2626',
}
const VERDICT_STROKE_DEFAULT = '#a1a1aa'

const MIN_NODE_RADIUS = 16
const MAX_NODE_RADIUS = 32
const GATEWAY_RADIUS = 28

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Extract the /24 subnet label from an IP address. */
function subnetOf(ip: string | null): string {
  if (!ip) return 'unknown'
  const parts = ip.split('.')
  if (parts.length !== 4) return 'unknown'
  return `${parts[0]}.${parts[1]}.${parts[2]}.0/24`
}

/** Compute node radius based on the number of open ports (clamped). */
function nodeRadius(device: Device): number {
  const portCount = device.open_ports?.length ?? 0
  // 0 ports -> MIN, 10+ ports -> MAX
  const t = Math.min(portCount / 10, 1)
  return MIN_NODE_RADIUS + t * (MAX_NODE_RADIUS - MIN_NODE_RADIUS)
}

function verdictStroke(device: Device): string {
  const v = (device.last_verdict ?? '').toLowerCase()
  return VERDICT_STROKES[v] ?? VERDICT_STROKE_DEFAULT
}

function categoryFill(device: Device): string {
  return CATEGORY_COLORS[device.category] ?? CATEGORY_COLORS.unknown
}

// ---------------------------------------------------------------------------
// Layout: position subnets in a ring, devices within each subnet cluster
// ---------------------------------------------------------------------------

interface NodeLayout {
  device: Device
  x: number
  y: number
  r: number
}

interface SubnetLayout {
  subnet: string
  cx: number
  cy: number
  nodes: NodeLayout[]
}

function computeLayout(devices: Device[]): {
  subnets: SubnetLayout[]
  gatewayCx: number
  gatewayCy: number
} {
  const cx = SVG_WIDTH / 2
  const cy = SVG_HEIGHT / 2

  // Group by subnet
  const groups = new Map<string, Device[]>()
  for (const d of devices) {
    const key = subnetOf(d.ip_address)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(d)
  }

  const subnetKeys = Array.from(groups.keys()).sort()
  const subnetCount = subnetKeys.length

  // Radius of the ring on which subnet cluster centers sit
  const ringRadius = Math.min(SVG_WIDTH, SVG_HEIGHT) * 0.32

  const subnets: SubnetLayout[] = subnetKeys.map((subnet, si) => {
    const angle =
      subnetCount === 1
        ? -Math.PI / 2
        : (2 * Math.PI * si) / subnetCount - Math.PI / 2
    const clusterCx = cx + ringRadius * Math.cos(angle)
    const clusterCy = cy + ringRadius * Math.sin(angle)

    const devs = groups.get(subnet)!
    const devCount = devs.length

    // Arrange devices in a small arc around the cluster center
    const clusterRadius = Math.max(40, devCount * 14)
    const nodes: NodeLayout[] = devs.map((device, di) => {
      if (devCount === 1) {
        return { device, x: clusterCx, y: clusterCy, r: nodeRadius(device) }
      }
      const a =
        devCount <= 6
          ? (2 * Math.PI * di) / devCount - Math.PI / 2
          : (2 * Math.PI * di) / devCount - Math.PI / 2
      return {
        device,
        x: clusterCx + clusterRadius * Math.cos(a),
        y: clusterCy + clusterRadius * Math.sin(a),
        r: nodeRadius(device),
      }
    })

    return { subnet, cx: clusterCx, cy: clusterCy, nodes }
  })

  return { subnets, gatewayCx: cx, gatewayCy: cy }
}

// ---------------------------------------------------------------------------
// Tooltip state
// ---------------------------------------------------------------------------

interface TooltipState {
  visible: boolean
  x: number
  y: number
  name: string
  ip: string
  category: string
  ports: number
  verdict: string
}

const TOOLTIP_INITIAL: TooltipState = {
  visible: false,
  x: 0,
  y: 0,
  name: '',
  ip: '',
  category: '',
  ports: 0,
  verdict: '',
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TopologyMap({ devices, onDeviceClick }: TopologyMapProps) {
  const [tooltip, setTooltip] = useState<TooltipState>(TOOLTIP_INITIAL)
  const containerRef = useRef<HTMLDivElement>(null)

  const layout = useMemo(() => computeLayout(devices), [devices])

  // Convert SVG coords to screen coords for tooltip positioning
  const svgRef = useRef<SVGSVGElement>(null)

  const showTooltip = useCallback(
    (device: Device, svgX: number, svgY: number) => {
      if (!svgRef.current || !containerRef.current) return
      const svgRect = svgRef.current.getBoundingClientRect()
      const containerRect = containerRef.current.getBoundingClientRect()
      // Map SVG coordinate space to screen pixels
      const scaleX = svgRect.width / SVG_WIDTH
      const scaleY = svgRect.height / SVG_HEIGHT
      const screenX = svgRect.left - containerRect.left + svgX * scaleX
      const screenY = svgRect.top - containerRect.top + svgY * scaleY
      setTooltip({
        visible: true,
        x: screenX,
        y: screenY,
        name: getPreferredDeviceName(device),
        ip: device.ip_address ?? 'No IP',
        category: device.category,
        ports: device.open_ports?.length ?? 0,
        verdict: device.last_verdict ?? 'untested',
      })
    },
    [],
  )

  const hideTooltip = useCallback(() => {
    setTooltip((prev) => ({ ...prev, visible: false }))
  }, [])

  // Hide tooltip on scroll / resize
  useEffect(() => {
    const hide = () => setTooltip((p) => ({ ...p, visible: false }))
    window.addEventListener('scroll', hide, true)
    window.addEventListener('resize', hide)
    return () => {
      window.removeEventListener('scroll', hide, true)
      window.removeEventListener('resize', hide)
    }
  }, [])

  if (devices.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-zinc-400 dark:text-slate-500 text-sm">
        No devices to visualize. Add devices to see the network topology.
      </div>
    )
  }

  return (
    <div ref={containerRef} className="relative w-full">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
        className="w-full h-auto max-h-[620px] rounded-xl"
        role="img"
        aria-label="Network topology map"
      >
        {/* Background */}
        <rect
          width={SVG_WIDTH}
          height={SVG_HEIGHT}
          rx={12}
          className="fill-zinc-50 dark:fill-slate-900"
        />

        {/* Subnet cluster backgrounds and links to gateway */}
        {layout.subnets.map((sub) => {
          // Compute bounding circle for the cluster
          let maxDist = 0
          for (const n of sub.nodes) {
            const dx = n.x - sub.cx
            const dy = n.y - sub.cy
            const dist = Math.sqrt(dx * dx + dy * dy) + n.r + 8
            if (dist > maxDist) maxDist = dist
          }
          const bgRadius = Math.max(maxDist, 50)

          return (
            <g key={`subnet-${sub.subnet}`}>
              {/* Link from gateway to subnet center */}
              <line
                x1={layout.gatewayCx}
                y1={layout.gatewayCy}
                x2={sub.cx}
                y2={sub.cy}
                className="stroke-zinc-300 dark:stroke-slate-700"
                strokeWidth={2}
                strokeDasharray="6,4"
              />
              {/* Cluster background bubble */}
              <circle
                cx={sub.cx}
                cy={sub.cy}
                r={bgRadius}
                className="fill-zinc-100/50 dark:fill-slate-800/30 stroke-zinc-200 dark:stroke-slate-700/50"
                strokeWidth={1}
                strokeDasharray="3,3"
              />
              {/* Subnet label */}
              <text
                x={sub.cx}
                y={sub.cy - bgRadius - 6}
                textAnchor="middle"
                className="fill-zinc-400 dark:fill-slate-500"
                fontSize={10}
                fontWeight={600}
                fontFamily="ui-monospace, monospace"
              >
                {sub.subnet}
              </text>
            </g>
          )
        })}

        {/* Lines from subnet center to each device node */}
        {layout.subnets.map((sub) =>
          sub.nodes.map((n) => (
            <line
              key={`edge-${n.device.id}`}
              x1={sub.cx}
              y1={sub.cy}
              x2={n.x}
              y2={n.y}
              className="stroke-zinc-200 dark:stroke-slate-700"
              strokeWidth={1}
            />
          )),
        )}

        {/* Central gateway node */}
        <g>
          <circle
            cx={layout.gatewayCx}
            cy={layout.gatewayCy}
            r={GATEWAY_RADIUS}
            className="fill-slate-800 dark:fill-slate-200 stroke-slate-900 dark:stroke-slate-100"
            strokeWidth={2}
          />
          <text
            x={layout.gatewayCx}
            y={layout.gatewayCy + 1}
            textAnchor="middle"
            dominantBaseline="central"
            className="fill-white dark:fill-slate-900"
            fontSize={10}
            fontWeight={700}
          >
            GATEWAY
          </text>
        </g>

        {/* Device nodes */}
        {layout.subnets.map((sub) =>
          sub.nodes.map((n) => {
            const fill = categoryFill(n.device)
            const stroke = verdictStroke(n.device)
            return (
              <g
                key={`node-${n.device.id}`}
                style={{ cursor: onDeviceClick ? 'pointer' : 'default' }}
                onClick={() => onDeviceClick?.(n.device)}
                onMouseEnter={() => showTooltip(n.device, n.x, n.y)}
                onMouseLeave={hideTooltip}
                role="button"
                tabIndex={0}
                aria-label={`Device: ${getPreferredDeviceName(n.device)}`}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onDeviceClick?.(n.device)
                  }
                }}
              >
                {/* Outer verdict ring */}
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={n.r + 3}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={3}
                  opacity={0.7}
                />
                {/* Main node */}
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={n.r}
                  fill={fill}
                  opacity={0.85}
                />
                {/* Inner label: short IP last octet or category initial */}
                <text
                  x={n.x}
                  y={n.y + 1}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill="white"
                  fontSize={n.r > 22 ? 11 : 9}
                  fontWeight={600}
                >
                  {n.device.ip_address
                    ? `.${n.device.ip_address.split('.').pop()}`
                    : n.device.category.charAt(0).toUpperCase()}
                </text>
              </g>
            )
          }),
        )}

        {/* Legend -- categories */}
        <g transform="translate(14, 14)">
          <text
            className="fill-zinc-500 dark:fill-slate-400"
            fontSize={9}
            fontWeight={700}
          >
            Category
          </text>
          {[
            ['camera', 'Camera', '#3b82f6'],
            ['controller', 'Controller', '#22c55e'],
            ['intercom', 'Intercom', '#06b6d4'],
            ['access_panel', 'Access Panel', '#f97316'],
            ['lighting', 'Lighting', '#eab308'],
            ['hvac', 'HVAC', '#0ea5e9'],
            ['iot_sensor', 'IoT Sensor', '#a855f7'],
            ['meter', 'Meter', '#f59e0b'],
            ['unknown', 'Unknown / Other', '#6b7280'],
          ].map(([, label, color], i) => (
            <g key={label} transform={`translate(0, ${16 + i * 16})`}>
              <circle cx={6} cy={0} r={5} fill={color} opacity={0.85} />
              <text
                x={16}
                y={3}
                className="fill-zinc-600 dark:fill-slate-400"
                fontSize={9}
              >
                {label}
              </text>
            </g>
          ))}
        </g>

        {/* Legend -- verdicts */}
        <g transform={`translate(14, ${14 + 8 * 16 + 30})`}>
          <text
            className="fill-zinc-500 dark:fill-slate-400"
            fontSize={9}
            fontWeight={700}
          >
            Verdict (border)
          </text>
          {[
            ['Pass', '#16a34a'],
            ['Fail', '#dc2626'],
            ['Untested', '#a1a1aa'],
          ].map(([label, color], i) => (
            <g key={label} transform={`translate(0, ${16 + i * 16})`}>
              <circle
                cx={6}
                cy={0}
                r={5}
                fill="none"
                stroke={color}
                strokeWidth={2.5}
              />
              <text
                x={16}
                y={3}
                className="fill-zinc-600 dark:fill-slate-400"
                fontSize={9}
              >
                {label}
              </text>
            </g>
          ))}
        </g>

        {/* Legend -- node size */}
        <g transform={`translate(14, ${14 + 8 * 16 + 30 + 3 * 16 + 30})`}>
          <text
            className="fill-zinc-500 dark:fill-slate-400"
            fontSize={9}
            fontWeight={700}
          >
            Size = open ports
          </text>
          <circle
            cx={8}
            cy={20}
            r={6}
            className="fill-zinc-300 dark:fill-slate-600"
          />
          <text
            x={20}
            y={23}
            className="fill-zinc-500 dark:fill-slate-400"
            fontSize={8}
          >
            0 ports
          </text>
          <circle
            cx={8}
            cy={40}
            r={12}
            className="fill-zinc-300 dark:fill-slate-600"
          />
          <text
            x={24}
            y={43}
            className="fill-zinc-500 dark:fill-slate-400"
            fontSize={8}
          >
            10+ ports
          </text>
        </g>
      </svg>

      {/* HTML tooltip overlay */}
      {tooltip.visible && (
        <div
          className="absolute z-10 pointer-events-none px-3 py-2 rounded-lg shadow-lg border border-zinc-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs"
          style={{
            left: tooltip.x,
            top: tooltip.y - 60,
            transform: 'translateX(-50%)',
          }}
        >
          <p className="font-semibold text-zinc-900 dark:text-slate-100">
            {tooltip.name}
          </p>
          <p className="text-zinc-500 dark:text-slate-400 font-mono">
            {tooltip.ip}
          </p>
          <p className="text-zinc-400 dark:text-slate-500 mt-0.5">
            {tooltip.category} &middot; {tooltip.ports} port
            {tooltip.ports !== 1 ? 's' : ''} &middot; {tooltip.verdict}
          </p>
        </div>
      )}
    </div>
  )
}
