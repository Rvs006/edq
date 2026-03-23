import { useEffect, useRef } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'

interface LiveTerminalProps {
  output: string
  className?: string
}

export default function LiveTerminal({ output, className = '' }: LiveTerminalProps) {
  const termRef = useRef<HTMLDivElement>(null)
  const xtermRef = useRef<Terminal | null>(null)
  const fitRef = useRef<FitAddon | null>(null)

  useEffect(() => {
    if (!termRef.current) return

    const term = new Terminal({
      theme: {
        background: '#18181b',
        foreground: '#e4e4e7',
        cursor: '#e4e4e7',
        cursorAccent: '#18181b',
        selectionBackground: '#3f3f46',
        selectionForeground: '#fafafa',
        black: '#18181b',
        red: '#ef4444',
        green: '#22c55e',
        yellow: '#eab308',
        blue: '#3b82f6',
        magenta: '#a855f7',
        cyan: '#06b6d4',
        white: '#e4e4e7',
        brightBlack: '#52525b',
        brightRed: '#f87171',
        brightGreen: '#4ade80',
        brightYellow: '#facc15',
        brightBlue: '#60a5fa',
        brightMagenta: '#c084fc',
        brightCyan: '#22d3ee',
        brightWhite: '#fafafa',
      },
      fontSize: 13,
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      lineHeight: 1.4,
      convertEol: true,
      disableStdin: true,
      scrollback: 5000,
      cursorBlink: false,
      cursorStyle: 'bar',
      cursorInactiveStyle: 'none',
    })

    const fit = new FitAddon()
    const webLinks = new WebLinksAddon()
    term.loadAddon(fit)
    term.loadAddon(webLinks)
    term.open(termRef.current)

    requestAnimationFrame(() => fit.fit())

    xtermRef.current = term
    fitRef.current = fit

    const resizeObserver = new ResizeObserver(() => {
      requestAnimationFrame(() => fit.fit())
    })
    resizeObserver.observe(termRef.current)

    return () => {
      resizeObserver.disconnect()
      term.dispose()
      xtermRef.current = null
      fitRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!xtermRef.current) return
    xtermRef.current.clear()
    if (output) {
      xtermRef.current.write(output)
    }
  }, [output])

  return (
    <div
      ref={termRef}
      className={`rounded-lg overflow-hidden border border-zinc-700/50 ${className}`}
      style={{ minHeight: 200 }}
    />
  )
}
