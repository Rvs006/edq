/**
 * Electracom logo using the actual brand PNG with Device Qualifier subtitle.
 * Uses the tightly-cropped assets/electracom-logo.png (1600x296).
 */
export function ElectracomLogo({
  size = 'md',
}: {
  /** sm = footer, md = header/sidebar, lg = login */
  size?: 'sm' | 'md' | 'lg'
}) {
  const config = {
    sm: { img: 'h-5', sub: 'text-[8px]' },
    md: { img: 'h-7', sub: 'text-[10px]' },
    lg: { img: 'h-9', sub: 'text-[10px]' },
  }[size]

  return (
    <div className="flex flex-col">
      <img
        src="/electracom-logo.png"
        alt="Electracom"
        className={`${config.img} object-contain object-left dark:hidden`}
      />
      <img
        src="/electracom-logo.png"
        alt="Electracom"
        className={`${config.img} object-contain object-left hidden dark:block`}
        style={{ filter: 'brightness(2) saturate(1.3)' }}
      />
      <span className={`${config.sub} font-medium tracking-wide text-zinc-400 dark:text-slate-500 -mt-0.5`}>
        Device Qualifier
      </span>
    </div>
  )
}
