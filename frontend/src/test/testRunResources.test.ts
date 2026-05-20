import { describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({
  testRunsApi: {
    list: vi.fn(),
    get: vi.fn(),
  },
  testResultsApi: {
    list: vi.fn(),
  },
}))

import {
  invalidateTestRunResource,
  testRunKeys,
} from '@/lib/testRunResources'

describe('testRunResources', () => {
  it('builds stable list, detail, and result keys under one root', () => {
    expect(testRunKeys.list({ status: 'completed' })).toEqual([
      'test-runs',
      'list',
      { status: 'completed' },
    ])
    expect(testRunKeys.detail('run-1')).toEqual(['test-runs', 'detail', 'run-1'])
    expect(testRunKeys.results('run-1')).toEqual(['test-runs', 'results', 'run-1'])
  })

  it('invalidates only detail and result cache entries for a run by default', () => {
    const queryClient = {
      invalidateQueries: vi.fn(),
    }

    invalidateTestRunResource(queryClient as never, 'run-1')

    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['test-runs', 'detail', 'run-1'],
    })
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['test-runs', 'results', 'run-1'],
    })
    expect(queryClient.invalidateQueries).not.toHaveBeenCalledWith({
      queryKey: ['test-runs', 'list'],
    })
  })

  it('invalidates list cache entries only when requested', () => {
    const queryClient = {
      invalidateQueries: vi.fn(),
    }

    invalidateTestRunResource(queryClient as never, 'run-1', { includeLists: true })

    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['test-runs', 'list'],
    })
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['test-runs', 'detail', 'run-1'],
    })
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['test-runs', 'results', 'run-1'],
    })
  })
})
