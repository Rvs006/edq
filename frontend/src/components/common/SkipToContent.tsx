/**
 * SkipToContent - Keyboard accessibility link that appears on focus.
 *
 * Renders an invisible link that becomes visible when focused via Tab.
 * Allows keyboard users to skip past navigation directly to the main content.
 *
 * Place as the first child inside the App component.
 * The target element should have id="main-content".
 *
 * @example
 * ```tsx
 * import SkipToContent from '@/components/common/SkipToContent'
 *
 * function App() {
 *   return (
 *     <>
 *       <SkipToContent />
 *       <nav>...</nav>
 *       <main id="main-content">...</main>
 *     </>
 *   )
 * }
 * ```
 */
export default function SkipToContent() {
  const handleClick = () => {
    const target = document.getElementById('main-content')
    if (!target) return
    requestAnimationFrame(() => {
      target.focus()
    })
  }

  return (
    <a
      href="#main-content"
      onClick={handleClick}
      className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[200] focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:bg-brand-500 focus:text-white focus:rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:shadow-lg transition-all"
    >
      Skip to main content
    </a>
  )
}
