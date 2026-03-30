import { Sun, Moon } from 'lucide-react'
import { useTheme } from '@/contexts/ThemeContext'

/** Compact icon-only toggle for the header bar */
export default function ThemeToggle() {
  const { mode, setMode, isDark } = useTheme()

  const toggle = () => setMode(isDark ? 'light' : 'dark')
  const Icon = isDark ? Moon : Sun

  return (
    <button
      onClick={toggle}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
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
