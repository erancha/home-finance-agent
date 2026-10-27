import { describe, expect, it } from 'vitest'
import {
  formatAmount,
  formatDate,
  formatShekels,
  formatShekelsSum,
  formatTimestamp,
} from './format.ts'

describe('formatAmount', () => {
  it('rounds to whole units and separates thousands', () => {
    expect(formatAmount('1248.82')).toBe('1,249')
    expect(formatAmount('120.49')).toBe('120')
    expect(formatAmount('-35.50')).toBe('-36')
    expect(formatAmount('1234567')).toBe('1,234,567')
  })

  it('refuses text that is not a number', () => {
    expect(() => formatAmount('abc')).toThrow('not an amount: abc')
  })
})

describe('formatShekels', () => {
  it('shows a card-currency amount as whole shekels with the shekel sign', () => {
    expect(formatShekels('1248.82')).toBe('₪1,249')
    expect(formatShekels('-35.50')).toBe('-₪36')
  })

  it('refuses text that is not a number', () => {
    expect(() => formatShekels('abc')).toThrow('not an amount: abc')
  })
})

describe('formatShekelsSum', () => {
  it('adds amounts up and shows the sum as whole shekels', () => {
    expect(formatShekelsSum(['1200.10', '130.20', '0.20'])).toBe('₪1,331')
    expect(formatShekelsSum([])).toBe('₪0')
  })

  it('refuses text that is not a number', () => {
    expect(() => formatShekelsSum(['1.00', 'abc'])).toThrow('not an amount: abc')
  })
})

describe('formatDate', () => {
  it('shows an ISO date as DD/MM/YYYY, whatever the time zone', () => {
    expect(formatDate('2026-01-02')).toBe('02/01/2026')
    expect(formatDate('2026-12-31')).toBe('31/12/2026')
  })

  it('refuses text that is not an ISO date', () => {
    expect(() => formatDate('2026-1-2')).toThrow('not a date: 2026-1-2')
    expect(() => formatDate('02/01/2026')).toThrow('not a date: 02/01/2026')
  })
})

describe('formatTimestamp', () => {
  it('shows an ISO time as local DD/MM/YYYY HH:MM:SS', () => {
    expect(formatTimestamp(new Date(2026, 0, 2, 3, 4, 5).toISOString())).toBe('02/01/2026 03:04:05')
  })

  it('refuses text that is not a time', () => {
    expect(() => formatTimestamp('soon')).toThrow('not a time: soon')
  })
})
