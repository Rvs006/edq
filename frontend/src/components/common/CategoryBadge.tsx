import { Camera, Cpu, Phone, DoorOpen, Lightbulb, Thermometer, Radio, Gauge, HelpCircle } from 'lucide-react'

type DeviceCategory = 'camera' | 'controller' | 'intercom' | 'access_panel' | 'lighting' | 'hvac' | 'iot_sensor' | 'meter' | 'unknown' | string

const categoryConfig: Record<string, { label: string; icon: React.ElementType; bg: string; text: string; border: string }> = {
  camera: { label: 'Camera', icon: Camera, bg: 'bg-purple-50 dark:bg-purple-950/40', text: 'text-purple-700 dark:text-purple-400', border: 'border-purple-200 dark:border-purple-800' },
  controller: { label: 'Controller', icon: Cpu, bg: 'bg-blue-50 dark:bg-blue-950/40', text: 'text-blue-700 dark:text-blue-400', border: 'border-blue-200 dark:border-blue-800' },
  intercom: { label: 'Intercom', icon: Phone, bg: 'bg-teal-50 dark:bg-teal-950/40', text: 'text-teal-700 dark:text-teal-400', border: 'border-teal-200 dark:border-teal-800' },
  access_panel: { label: 'Access Panel', icon: DoorOpen, bg: 'bg-amber-50 dark:bg-amber-950/40', text: 'text-amber-700 dark:text-amber-400', border: 'border-amber-200 dark:border-amber-800' },
  lighting: { label: 'Lighting', icon: Lightbulb, bg: 'bg-yellow-50 dark:bg-yellow-950/40', text: 'text-yellow-700 dark:text-yellow-400', border: 'border-yellow-200 dark:border-yellow-800' },
  hvac: { label: 'HVAC', icon: Thermometer, bg: 'bg-cyan-50 dark:bg-cyan-950/40', text: 'text-cyan-700 dark:text-cyan-400', border: 'border-cyan-200 dark:border-cyan-800' },
  iot_sensor: { label: 'IoT Sensor', icon: Radio, bg: 'bg-green-50 dark:bg-green-950/40', text: 'text-green-700 dark:text-green-400', border: 'border-green-200 dark:border-green-800' },
  meter: { label: 'Meter', icon: Gauge, bg: 'bg-orange-50 dark:bg-orange-950/40', text: 'text-orange-700 dark:text-orange-400', border: 'border-orange-200 dark:border-orange-800' },
  unknown: { label: 'Unknown', icon: HelpCircle, bg: 'bg-zinc-50 dark:bg-zinc-800', text: 'text-zinc-600 dark:text-zinc-400', border: 'border-zinc-200 dark:border-zinc-700' },
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
