import '@testing-library/jest-dom'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
})

Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
  configurable: true,
  writable: true,
  value: vi.fn(() => ({
    canvas: document.createElement('canvas'),
    measureText: () => ({ width: 0 }),
  })) as unknown as typeof HTMLCanvasElement.prototype.getContext,
})
