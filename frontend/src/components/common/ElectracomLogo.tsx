/**
 * Clean Electracom wordmark with rainbow accent bar.
 * Replaces the oversized PNG that rendered poorly at small sizes.
 */
export function ElectracomLogo({
  size = 'md',
  subtitle = true,
}: {
  /** sm = footer, md = header/sidebar, lg = login */
  size?: 'sm' | 'md' | 'lg'
  subtitle?: boolean
}) {
  const config = {
    sm: { text: 'text-[13px]', bar: 'h-[2px]', gap: 'gap-[2px]', sub: 'text-[7px]', barGap: 'gap-[1.5px]' },
    md: { text: 'text-[16px]', bar: 'h-[2.5px]', gap: 'gap-[2.5px]', sub: 'text-[9px]', barGap: 'gap-[2px]' },
    lg: { text: 'text-[20px]', bar: 'h-[3px]', gap: 'gap-[3px]', sub: 'text-[10px]', barGap: 'gap-[2px]' },
  }[size]

  const colors = ['#6a3d9a', '#1f78b4', '#33a02c', '#e6a800', '#e31a1c']

  return (
    <div className={`flex flex-col ${config.gap}`}>
      <span
        className={`${config.text} font-extrabold tracking-[0.18em] text-zinc-500 dark:text-zinc-300 leading-none select-none`}
      >
        ELECTRACOM
      </span>
      <div className={`flex ${config.barGap}`}>
        {colors.map((color) => (
          <div
            key={color}
            className={`flex-1 ${config.bar} rounded-[1px]`}
            style={{ backgroundColor: color }}
          />
        ))}
      </div>
      {subtitle && (
        <span className={`${config.sub} font-medium tracking-wide text-zinc-400 dark:text-slate-500 -mt-0.5 leading-none`}>
          Device Qualifier
        </span>
      )}
    </div>
  )
}
