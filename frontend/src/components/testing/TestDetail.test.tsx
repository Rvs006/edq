import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import TestDetail, { type TestResultDetail } from './TestDetail'

const baseResult: TestResultDetail = {
  id: 'result-1',
  test_id: 'U20',
  test_name: 'Cable recovery',
  tier: 'guided_manual',
  tool: null,
  raw_output: null,
  parsed_data: null,
  findings: null,
  verdict: 'pending',
  comment: null,
  engineer_notes: null,
  is_overridden: false,
  override_reason: null,
  override_verdict: null,
  overridden_by_username: null,
  started_at: null,
  completed_at: null,
}

describe('TestDetail manual gating', () => {
  it('keeps manual actions locked before the run reaches manual review', () => {
    render(
      <TestDetail
        result={baseResult}
        liveOutput=""
        isRunning={false}
        runStatus="pending"
        userRole="engineer"
        onSubmitManual={vi.fn()}
        onOverride={vi.fn()}
        onSaveNotes={vi.fn()}
        isSubmitting={false}
        manualProgress={null}
      />
    )

    expect(screen.getByText(/manual assessment unlocks after the automatic checks finish/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /submit result/i })).not.toBeInTheDocument()
  })

  it('shows manual controls once the run is awaiting manual input', () => {
    render(
      <TestDetail
        result={baseResult}
        liveOutput=""
        isRunning={false}
        runStatus="awaiting_manual"
        userRole="engineer"
        onSubmitManual={vi.fn()}
        onOverride={vi.fn()}
        onSaveNotes={vi.fn()}
        isSubmitting={false}
        manualProgress={{ current: 1, total: 1 }}
      />
    )

    expect(screen.getByRole('button', { name: /submit result/i })).toBeInTheDocument()
  })
})
