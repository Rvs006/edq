import { describe, expect, it } from 'vitest'

import { summarizeRunProgress } from './testUi'

describe('summarizeRunProgress', () => {
  it('keeps seeded pending runs in a waiting state until execution actually starts', () => {
    const summary = summarizeRunProgress(
      [
        { tier: 'automatic', verdict: 'pending' },
        { tier: 'guided_manual', verdict: 'pending' },
      ],
      null,
      'pending'
    )

    expect(summary.progressLabel).toBe('Waiting to start')
    expect(summary.detailText).toMatch(/connect the device and start the session/i)
  })

  it('shows a connectivity pause when the cable/device is unavailable', () => {
    const summary = summarizeRunProgress(
      [{ tier: 'automatic', verdict: 'pending' }],
      null,
      'paused_cable'
    )

    expect(summary.progressLabel).toBe('Paused for connectivity')
    expect(summary.detailText).toMatch(/automatic tests will resume/i)
  })

  it('only marks manual review as active once the run reaches the manual stage', () => {
    const summary = summarizeRunProgress(
      [
        { tier: 'automatic', verdict: 'pass' },
        { tier: 'guided_manual', verdict: 'pending' },
      ],
      null,
      'awaiting_manual'
    )

    expect(summary.progressLabel).toBe('Manual review remaining')
    expect(summary.detailText).toMatch(/manual test/i)
  })
})
