import { describe, expect, it } from 'vitest'
import { ACTIVE_UNIVERSAL_TESTS, getEffectiveTestTier, UNIVERSAL_TESTS } from './universal-tests'

function testById(id: string) {
  const test = UNIVERSAL_TESTS.find((item) => item.id === id)
  if (!test) throw new Error(`Missing test fixture ${id}`)
  return test
}

describe('getEffectiveTestTier', () => {
  it('keeps the system-status scanner tools represented in active tests', () => {
    expect(ACTIVE_UNIVERSAL_TESTS).toHaveLength(49)
    expect(ACTIVE_UNIVERSAL_TESTS.find((test) => test.id === 'U31')?.name).toBe('SNMP Version Check')
  })

  it('keeps template-scriptable lab checks automatic', () => {
    expect(getEffectiveTestTier(testById('U04'), 'test_lab')).toBe('automatic')
    expect(getEffectiveTestTier(testById('U09'), 'test_lab')).toBe('automatic')
    expect(getEffectiveTestTier(testById('U26'), 'test_lab')).toBe('automatic')
    expect(getEffectiveTestTier(testById('U28'), 'test_lab')).toBe('automatic')
    expect(getEffectiveTestTier(testById('U29'), 'test_lab')).toBe('automatic')
  })

  it('reroutes only site-network checks the template cannot script', () => {
    expect(getEffectiveTestTier(testById('U04'), 'site_network')).toBe('guided_manual')
    expect(getEffectiveTestTier(testById('U09'), 'site_network')).toBe('automatic')
    expect(getEffectiveTestTier(testById('U26'), 'site_network')).toBe('guided_manual')
    expect(getEffectiveTestTier(testById('U28'), 'site_network')).toBe('automatic')
    expect(getEffectiveTestTier(testById('U29'), 'site_network')).toBe('guided_manual')
  })
})
