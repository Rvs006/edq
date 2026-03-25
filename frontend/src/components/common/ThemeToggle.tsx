import { Sun, Moon, Monitor } from 'lucide-react'
import { useTheme } from '@/contexts/ThemeContext'

const modes = [
  { value: 'light' as const, icon: Sun, label: 'Light' },
  { value: 'system' as const, icon: Monitor, label: 'System' },
  { value: 'dark' as const, icon: Moon, label: 'Dark' },
]

/** Compact icon-only toggle for the header bar */
export default function ThemeToggle() {
  const { mode, setMode, isDark } = useTheme()

  // Cycle through: light → system → dark → light
  const cycle = () => {
    const idx = modes.findIndex((m) => m.value === mode)
    setMode(modes[(idx + 1) % modes.length].value)
  }

  const current = modes.find((m) => m.value === mode)!
  const Icon = current.icon

  return (
    <button
      onClick={cycle}
      title={`Theme: ${current.label} — click to cycle`}
      className={`p-2 rounded-lg transition-colors ${
        isDark
          ? 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
          : 'text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100'
      }`}
    >
      <Icon className="w-5 h-5" />
    </button>
  )
}
