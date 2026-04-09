import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center py-24 px-4">
      <h1 className="text-6xl font-bold text-zinc-300 dark:text-slate-600">404</h1>
      <p className="mt-4 text-lg text-zinc-600 dark:text-slate-400">Page not found</p>
      <Link
        to="/"
        className="mt-6 px-4 py-2 text-sm font-medium bg-brand-500 text-white rounded-lg hover:bg-brand-600 transition-colors"
      >
        Back to Dashboard
      </Link>
    </div>
  )
}
