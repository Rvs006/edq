export function ElectracomLogo({
  size = 'md',
  className = '',
}: {
  /** sm = footer/sidebar, md = header, lg = login */
  size?: 'sm' | 'md' | 'lg'
  className?: string
}) {
  const config = {
    sm: { wrapper: 'gap-2', icon: 'h-7', img: 'h-[26px]', sub: 'text-[8px]' },
    md: { wrapper: 'gap-2.5', icon: 'h-8', img: 'h-[30px]', sub: 'text-[9px]' },
    lg: { wrapper: 'gap-3', icon: 'h-12', img: 'h-[56px]', sub: 'text-[12px]' },
  }[size]

  return (
    <div className={`flex flex-col items-center text-center ${className}`}>
      <div className={`flex items-end justify-center ${config.wrapper}`}>
        <img src="/icon.png" alt="" className={`${config.icon} w-auto shrink-0 dark:hidden`} />
        <img src="/icon-white.png" alt="" className={`${config.icon} w-auto shrink-0 hidden dark:block`} />
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
          <span className={`${config.sub} font-medium tracking-wide text-zinc-400 dark:text-slate-500 mt-0.5`}>
            Device Qualifier
          </span>
        </div>
      </div>
    </div>
  )
}
