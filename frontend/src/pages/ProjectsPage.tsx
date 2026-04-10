import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, getApiErrorMessage } from '@/lib/api'
import type { Project } from '@/lib/types'
import { FolderOpen, Plus, Archive, Trash2, MapPin, Building2, Monitor, Play } from 'lucide-react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'

export default function ProjectsPage() {
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [clientName, setClientName] = useState('')
  const [location, setLocation] = useState('')
  const queryClient = useQueryClient()

  const { data, isLoading, isError } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: () => projectsApi.create({ name, description, client_name: clientName, location }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setShowCreate(false)
      setName(''); setDescription(''); setClientName(''); setLocation('')
      toast.success('Project created')
    },
    onError: (err: unknown) => {
      toast.error(getApiErrorMessage(err, 'Failed to create project'))
    },
  })

  const archiveMutation = useMutation({
    mutationFn: (id: string) => projectsApi.update(id, { is_archived: true }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['projects'] }); toast.success('Project archived') },
    onError: (err: unknown) => toast.error(getApiErrorMessage(err, 'Failed to archive project')),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => projectsApi.delete(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['projects'] }); toast.success('Project deleted') },
    onError: (err: unknown) => toast.error(getApiErrorMessage(err, 'Failed to delete project')),
  })

  const projects: Project[] = data?.items || []

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">Projects</h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
            Organize devices and test runs into project folders
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Project
        </button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1,2,3].map(i => (
            <div key={i} className="h-48 bg-zinc-100 dark:bg-slate-800 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : isError ? (
        <div className="text-center py-16 bg-white dark:bg-dark-surface rounded-xl border border-zinc-200 dark:border-slate-700">
          <FolderOpen className="w-12 h-12 text-zinc-300 dark:text-slate-600 mx-auto mb-3" />
          <h3 className="text-lg font-medium text-zinc-700 dark:text-zinc-300">Failed to load projects</h3>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1 mb-4">Try refreshing the page.</p>
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ['projects'] })}
            className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-medium"
          >
            Retry
          </button>
        </div>
      ) : projects.length === 0 ? (
        <div className="text-center py-16 bg-white dark:bg-dark-surface rounded-xl border border-zinc-200 dark:border-slate-700">
          <FolderOpen className="w-12 h-12 text-zinc-300 dark:text-slate-600 mx-auto mb-3" />
          <h3 className="text-lg font-medium text-zinc-700 dark:text-zinc-300">No projects yet</h3>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1 mb-4">Create your first project to organize devices and test runs</p>
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-medium"
          >
            Create Project
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map(project => (
            <div key={project.id} className="bg-white dark:bg-dark-surface rounded-xl border border-zinc-200 dark:border-slate-700 p-5 hover:border-brand-300 dark:hover:border-brand-600 transition-colors group">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-brand-50 dark:bg-brand-900/30 flex items-center justify-center">
                    <FolderOpen className="w-5 h-5 text-brand-600 dark:text-brand-400" />
                  </div>
                  <div>
                    <Link to={`/devices?project_id=${project.id}`} className="text-base font-semibold text-zinc-900 dark:text-white hover:text-brand-600 dark:hover:text-brand-400">
                      {project.name}
                    </Link>
                    <span className={`ml-2 inline-flex px-2 py-0.5 text-[10px] font-medium rounded-full ${
                      project.status === 'active' ? 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                      project.status === 'completed' ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' :
                      'bg-zinc-100 text-zinc-500 dark:bg-slate-700 dark:text-slate-400'
                    }`}>
                      {project.status}
                    </span>
                  </div>
                </div>
                <div className="flex gap-1 opacity-100 md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100 transition-opacity">
                  <button onClick={() => archiveMutation.mutate(project.id)} className="p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-slate-700" title="Archive" aria-label={`Archive ${project.name}`}>
                    <Archive className="w-4 h-4 text-zinc-400" />
                  </button>
                  <button onClick={() => { if (confirm('Delete this project? Devices will be unlinked, not deleted.')) deleteMutation.mutate(project.id) }} className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20" title="Delete" aria-label={`Delete ${project.name}`}>
                    <Trash2 className="w-4 h-4 text-zinc-400 hover:text-red-500" />
                  </button>
                </div>
              </div>

              {project.description && (
                <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-3 line-clamp-2">{project.description}</p>
              )}

              <div className="flex flex-wrap gap-3 text-xs text-zinc-400 dark:text-zinc-500 mb-3">
                {project.client_name && (
                  <span className="flex items-center gap-1"><Building2 className="w-3.5 h-3.5" />{project.client_name}</span>
                )}
                {project.location && (
                  <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5" />{project.location}</span>
                )}
              </div>

              <div className="flex items-center gap-4 pt-3 border-t border-zinc-100 dark:border-slate-700/50">
                <span className="flex items-center gap-1.5 text-sm text-zinc-600 dark:text-zinc-300">
                  <Monitor className="w-4 h-4 text-zinc-400" />
                  {project.device_count} device{project.device_count !== 1 ? 's' : ''}
                </span>
                <span className="flex items-center gap-1.5 text-sm text-zinc-600 dark:text-zinc-300">
                  <Play className="w-4 h-4 text-zinc-400" />
                  {project.test_run_count} run{project.test_run_count !== 1 ? 's' : ''}
                </span>
                <span className="ml-auto text-xs text-zinc-400">
                  {new Date(project.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowCreate(false)}>
          <div className="bg-white dark:bg-dark-surface rounded-xl shadow-xl w-full max-w-md mx-4 p-6" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-zinc-900 dark:text-white mb-4">New Project</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">Project Name *</label>
                <input
                  value={name} onChange={e => setName(e.target.value)}
                  className="w-full px-3 py-2 border border-zinc-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-zinc-900 dark:text-white text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none"
                  placeholder="e.g. London Office Retrofit"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">Description</label>
                <textarea
                  value={description} onChange={e => setDescription(e.target.value)}
                  className="w-full px-3 py-2 border border-zinc-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-zinc-900 dark:text-white text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none"
                  rows={2}
                  placeholder="Brief project description..."
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">Client</label>
                  <input
                    value={clientName} onChange={e => setClientName(e.target.value)}
                    className="w-full px-3 py-2 border border-zinc-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-zinc-900 dark:text-white text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none"
                    placeholder="Client name"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">Location</label>
                  <input
                    value={location} onChange={e => setLocation(e.target.value)}
                    className="w-full px-3 py-2 border border-zinc-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-zinc-900 dark:text-white text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none"
                    placeholder="Site location"
                  />
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-slate-700 rounded-lg">
                Cancel
              </button>
              <button
                onClick={() => createMutation.mutate()}
                disabled={!name.trim() || createMutation.isPending}
                className="px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium"
              >
                {createMutation.isPending ? 'Creating...' : 'Create Project'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
