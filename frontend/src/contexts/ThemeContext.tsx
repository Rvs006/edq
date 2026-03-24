import { createContext, useContext, useEffect, useState } from 'react'

type ThemeMode = 'light' | 'dark' | 'system'

interface ThemeContextType {
  mode: ThemeMode
  setMode: (mode: ThemeMode) => void
  isDark: boolean
}

const ThemeContext = createContext<ThemeContextType>({
  mode: 'system',
  setMode: () => {},
  isDark: false,
})

export function useTheme() {
  return useContext(ThemeContext)
}

function getSystemDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(() => {
    const stored = localStorage.getItem('edq-theme')
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
    return 'system'
  })
  // Separate state to track the resolved system preference so isDark stays fresh
  const [systemDark, setSystemDark] = useState(getSystemDark)

  const isDark = mode === 'dark' || (mode === 'system' && systemDark)

  const setMode = (newMode: ThemeMode) => {
    setModeState(newMode)
    localStorage.setItem('edq-theme', newMode)
  }

  // Apply/remove 'dark' class on <html>
  useEffect(() => {
    const root = document.documentElement
    if (isDark) {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
  }, [isDark])

  // Listen for system preference changes — update systemDark state to trigger re-render
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => setSystemDark(mq.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  return (
    <ThemeContext.Provider value={{ mode, setMode, isDark }}>
      {children}
    </ThemeContext.Provider>
  )
}
