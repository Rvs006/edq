import { Sun, Moon, Monitor } from 'lucide-react'
import { useTheme } from '@/contexts/ThemeContext'

const modes = [
  { value: 'light' as const, icon: Sun, label: 'Light' },
  { value: 'system' as const, icon: Monitor, label: 'System' },
  { value: 'dark' as const, icon: Moon, label: 'Dark' },
]

export default function ThemeToggle() {
  const { mode, setMode } = useTheme()

  return (
    <div className="flex items-center bg-zinc-800 rounded-lg p-0.5 gap-0.5">
      {modes.map((m) => {
        const active = mode === m.value
        const Icon = m.icon
        return (
          <button
            key={m.value}
            onClick={() => setMode(m.value)}
            title={m.label}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors ${
              active
                ? 'bg-zinc-700 text-white'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            <span className="hidden xl:inline">{m.label}</span>
          </button>
        )
      })}
    </div>
  )
}
