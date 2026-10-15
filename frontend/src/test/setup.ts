import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(cleanup)

// Recharts' ResponsiveContainer measures itself through ResizeObserver, which jsdom lacks, and
// jsdom lays nothing out. The stub reports one fixed size on observe so charts render their marks.
const CHART_SIZE = {
  width: 320, height: 240,
  top: 0, left: 0, right: 320, bottom: 240, x: 0, y: 0, toJSON: () => ({}),
}

class ResizeObserverStub {
  private readonly callback: ResizeObserverCallback

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
  }

  observe(target: Element) {
    const entry = { target, contentRect: CHART_SIZE } as ResizeObserverEntry
    this.callback([entry], this as unknown as ResizeObserver)
  }

  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver
