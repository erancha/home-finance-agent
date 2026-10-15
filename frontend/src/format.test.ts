import { describe, expect, it } from 'vitest'
import { formatAmount, formatTimestamp } from './format.ts'

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

describe('formatTimestamp', () => {
  it('shows an ISO time as local YYYY/MM/DD HH:MM:SS', () => {
    expect(formatTimestamp(new Date(2026, 0, 2, 3, 4, 5).toISOString())).toBe('2026/01/02 03:04:05')
  })

  it('refuses text that is not a time', () => {
    expect(() => formatTimestamp('soon')).toThrow('not a time: soon')
  })
})
