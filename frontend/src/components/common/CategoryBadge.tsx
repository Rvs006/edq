import { Camera, Cpu, Phone, DoorOpen, Lightbulb, Thermometer, Radio, Gauge, HelpCircle } from 'lucide-react'

type DeviceCategory = 'camera' | 'controller' | 'intercom' | 'access_panel' | 'lighting' | 'hvac' | 'iot_sensor' | 'meter' | 'unknown' | string

const categoryConfig: Record<string, { label: string; icon: React.ElementType; bg: string; text: string; border: string }> = {
  camera: { label: 'Camera', icon: Camera, bg: 'bg-purple-50', text: 'text-purple-700', border: 'border-purple-200' },
  controller: { label: 'Controller', icon: Cpu, bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200' },
  intercom: { label: 'Intercom', icon: Phone, bg: 'bg-teal-50', text: 'text-teal-700', border: 'border-teal-200' },
  access_panel: { label: 'Access Panel', icon: DoorOpen, bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200' },
  lighting: { label: 'Lighting', icon: Lightbulb, bg: 'bg-yellow-50', text: 'text-yellow-700', border: 'border-yellow-200' },
  hvac: { label: 'HVAC', icon: Thermometer, bg: 'bg-cyan-50', text: 'text-cyan-700', border: 'border-cyan-200' },
  iot_sensor: { label: 'IoT Sensor', icon: Radio, bg: 'bg-green-50', text: 'text-green-700', border: 'border-green-200' },
  meter: { label: 'Meter', icon: Gauge, bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-200' },
  unknown: { label: 'Unknown', icon: HelpCircle, bg: 'bg-zinc-50', text: 'text-zinc-600', border: 'border-zinc-200' },
}

interface CategoryBadgeProps {
  category: DeviceCategory
  showIcon?: boolean
  className?: string
}

export default function CategoryBadge({ category, showIcon = true, className = '' }: CategoryBadgeProps) {
  const config = categoryConfig[category?.toLowerCase()] || categoryConfig.unknown
  const Icon = config.icon

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border ${config.bg} ${config.text} ${config.border} ${className}`}>
      {showIcon && <Icon className="w-3 h-3" />}
      {config.label}
    </span>
  )
}
