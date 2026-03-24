/**
 * NetworkTopology — SVG-based network topology visualization.
 * Renders devices as nodes in a radial layout around a central gateway node.
 * Color-coded by status: green (qualified/passed), red (failed), amber (testing), gray (discovered).
 */

import { useMemo } from 'react'
import type { Device } from '@/lib/types'

interface NetworkTopologyProps {
  devices: Device[]
  onDeviceClick?: (device: Device) => void
  width?: number
  height?: number
}

const STATUS_COLORS: Record<string, { fill: string; stroke: string; text: string }> = {
  qualified: { fill: '#dcfce7', stroke: '#22c55e', text: '#166534' },
  tested: { fill: '#dbeafe', stroke: '#3b82f6', text: '#1e40af' },
  testing: { fill: '#fef3c7', stroke: '#f59e0b', text: '#92400e' },
  failed: { fill: '#fee2e2', stroke: '#ef4444', text: '#991b1b' },
  discovered: { fill: '#f4f4f5', stroke: '#a1a1aa', text: '#3f3f46' },
  identified: { fill: '#e0e7ff', stroke: '#6366f1', text: '#3730a3' },
}

const CATEGORY_ICONS: Record<string, string> = {
  camera: '\uD83D\uDCF7',
  controller: '\uD83C\uDFAE',
  intercom: '\uD83D\uDCDE',
  access_panel: '\uD83D\uDEAA',
  lighting: '\uD83D\uDCA1',
  hvac: '\u2744\uFE0F',
  iot_sensor: '\uD83D\uDCE1',
  meter: '\uD83D\uDCCA',
  unknown: '\uD83D\uDD0C',
}

export default function NetworkTopology({
  devices,
  onDeviceClick,
  width = 700,
  height = 500,
}: NetworkTopologyProps) {
  const centerX = width / 2
  const centerY = height / 2

  const nodePositions = useMemo(() => {
    if (devices.length === 0) return []
    const radius = Math.min(width, height) * 0.35
    const angleStep = (2 * Math.PI) / devices.length
    return devices.map((device, i) => {
      const angle = angleStep * i - Math.PI / 2
      return {
        device,
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      }
    })
  }, [devices, width, height, centerX, centerY])

  if (devices.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-zinc-400 text-sm">
        No devices to visualize. Add devices to see the network topology.
      </div>
    )
  }

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full h-auto max-h-[500px]"
      style={{ background: '#fafafa', borderRadius: '0.75rem' }}
    >
      {/* Connection lines from gateway to each device */}
      {nodePositions.map(({ device, x, y }) => (
        <line
          key={`line-${device.id}`}
          x1={centerX}
          y1={centerY}
          x2={x}
          y2={y}
          stroke="#e4e4e7"
          strokeWidth={1.5}
          strokeDasharray="4,4"
        />
      ))}

      {/* Central gateway node */}
      <g>
        <circle cx={centerX} cy={centerY} r={30} fill="#1e293b" stroke="#0f172a" strokeWidth={2} />
        <text x={centerX} y={centerY - 4} textAnchor="middle" fill="white" fontSize={18}>
          {'\uD83C\uDF10'}
        </text>
        <text x={centerX} y={centerY + 16} textAnchor="middle" fill="white" fontSize={8} fontWeight={600}>
          GATEWAY
        </text>
      </g>

      {/* Device nodes */}
      {nodePositions.map(({ device, x, y }) => {
        const colors = STATUS_COLORS[device.status] || STATUS_COLORS.discovered
        const icon = CATEGORY_ICONS[device.category] || CATEGORY_ICONS.unknown
        return (
          <g
            key={device.id}
            onClick={() => onDeviceClick?.(device)}
            style={{ cursor: onDeviceClick ? 'pointer' : 'default' }}
          >
            {/* Node circle */}
            <circle
              cx={x}
              cy={y}
              r={24}
              fill={colors.fill}
              stroke={colors.stroke}
              strokeWidth={2}
            />
            {/* Category icon */}
            <text x={x} y={y - 2} textAnchor="middle" fontSize={16} dominantBaseline="central">
              {icon}
            </text>
            {/* IP address label */}
            <text
              x={x}
              y={y + 36}
              textAnchor="middle"
              fontSize={9}
              fontWeight={500}
              fill={colors.text}
            >
              {device.ip_address}
            </text>
            {/* Hostname or manufacturer label */}
            <text
              x={x}
              y={y + 47}
              textAnchor="middle"
              fontSize={8}
              fill="#71717a"
            >
              {device.hostname || device.manufacturer || device.category}
            </text>
            {/* Status indicator dot */}
            <circle cx={x + 18} cy={y - 18} r={5} fill={colors.stroke} stroke="white" strokeWidth={1.5} />
          </g>
        )
      })}

      {/* Legend */}
      <g transform={`translate(10, ${height - 70})`}>
        <text fontSize={9} fontWeight={600} fill="#71717a">Status</text>
        {Object.entries(STATUS_COLORS).slice(0, 4).map(([status, colors], i) => (
          <g key={status} transform={`translate(0, ${14 + i * 14})`}>
            <circle cx={6} cy={0} r={4} fill={colors.fill} stroke={colors.stroke} strokeWidth={1.5} />
            <text x={14} y={3} fontSize={8} fill="#52525b" style={{ textTransform: 'capitalize' }}>
              {status}
            </text>
          </g>
        ))}
      </g>
    </svg>
  )
}
