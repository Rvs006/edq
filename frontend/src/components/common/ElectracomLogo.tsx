/**
 * Electracom logo using the original brand PNG (trimmed) with centered Device Qualifier subtitle.
 */
export function ElectracomLogo({
  size = 'md',
}: {
  /** sm = footer, md = header/sidebar, lg = login */
  size?: 'sm' | 'md' | 'lg'
}) {
  const config = {
    sm: { img: 'h-[18px]', sub: 'text-[7px]' },
    md: { img: 'h-[26px]', sub: 'text-[9px]' },
    lg: { img: 'h-[34px]', sub: 'text-[10px]' },
  }[size]

  return (
    <div className="flex flex-col items-center">
      <img
        src="/electracom-logo.png"
        alt="Electracom"
        className={`${config.img} object-contain dark:hidden`}
      />
      <img
        src="/electracom-logo.png"
        alt="Electracom"
        className={`${config.img} object-contain hidden dark:block`}
        style={{ filter: 'brightness(2) saturate(1.3)' }}
      />
      <span className={`${config.sub} font-medium tracking-wide text-zinc-400 dark:text-slate-500 mt-0.5 text-center`}>
        Device Qualifier
      </span>
    </div>
  )
}
