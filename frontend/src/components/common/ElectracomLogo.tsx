/**
 * Electracom wordmark with division color badges and Device Qualifier subtitle.
 * Matches the official brand reference exactly.
 */
export function ElectracomLogo({
  size = 'md',
}: {
  /** sm = footer, md = header/sidebar, lg = login */
  size?: 'sm' | 'md' | 'lg'
}) {
  const config = {
    sm: {
      title: 'text-[11px] tracking-[0.15em]',
      badge: 'text-[3.5px] px-[3px] py-[1px]',
      badgeGap: 'gap-[1.5px]',
      sub: 'text-[8px]',
      gap: 'gap-[1.5px]',
    },
    md: {
      title: 'text-[15px] tracking-[0.16em]',
      badge: 'text-[4.5px] px-[4px] py-[1.5px]',
      badgeGap: 'gap-[2px]',
      sub: 'text-[11px]',
      gap: 'gap-[2px]',
    },
    lg: {
      title: 'text-[19px] tracking-[0.16em]',
      badge: 'text-[5.5px] px-[5px] py-[2px]',
      badgeGap: 'gap-[2.5px]',
      sub: 'text-[14px]',
      gap: 'gap-[2.5px]',
    },
  }[size]

  const divisions = [
    { label: 'PROJECTS', color: '#6a3d9a' },
    { label: 'SERVICE', color: '#1f78b4' },
    { label: 'ENERGY', color: '#33a02c' },
    { label: 'CONNECT', color: '#e6a800' },
    { label: 'SMART', color: '#e31a1c' },
  ]

  return (
    <div className={`flex flex-col ${config.gap}`}>
      <span
        className={`${config.title} font-extrabold text-zinc-500 dark:text-zinc-300 leading-none select-none`}
      >
        ELECTRACOM
      </span>
      <div className={`flex ${config.badgeGap}`}>
        {divisions.map((d) => (
          <span
            key={d.label}
            className={`${config.badge} font-bold text-white leading-none select-none rounded-[1px]`}
            style={{ backgroundColor: d.color }}
          >
            {d.label}
          </span>
        ))}
      </div>
      <span className={`${config.sub} font-semibold text-zinc-800 dark:text-slate-200 leading-none select-none`}>
        Device Qualifier
      </span>
    </div>
  )
}
