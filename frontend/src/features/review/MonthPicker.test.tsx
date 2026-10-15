import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { MonthView } from '../../api/types.ts'
import { MonthPicker, currentMonth } from './MonthPicker.tsx'

const free: MonthView = {
  month: '2026-10', review: null, limit: 3, startsLeft: 2, nextStart: null,
}
const reviewed: MonthView = { ...free, review: { id: 'r1', status: 'completed' } }

function renderPicker(view: MonthView | null, clearable = true) {
  const handlers = { onMonth: vi.fn(), onStart: vi.fn(), onClear: vi.fn() }
  render(
    <MonthPicker month="2026-10" view={view} clearable={clearable} busy={false} {...handlers} />,
  )
  return handlers
}

describe('MonthPicker', () => {
  it('defaults to the current month, the billing month of the latest statement', () => {
    expect(currentMonth(new Date(2026, 9, 13))).toBe('2026-10')
    expect(currentMonth(new Date(2027, 0, 1))).toBe('2027-01')
  })

  it('offers Start for a month without a review, counting the starts left', async () => {
    const { onStart } = renderPicker(free)
    expect(screen.getByLabelText('Billing month')).toHaveAccessibleDescription(
      /the month the card is charged/i,
    )
    expect(screen.getByText('2 of 3 reviews left in any 24 hours.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Start review' }))
    expect(onStart).toHaveBeenCalledOnce()
  })

  it('offers no Start before the month was read', () => {
    renderPicker(null)
    expect(screen.getByRole('button', { name: 'Start review' })).toBeDisabled()
  })

  it('says when the next start is allowed once none are left', () => {
    renderPicker({ ...free, startsLeft: 0, nextStart: '2026-10-15T09:30:00+00:00' })
    expect(screen.getByRole('button', { name: 'Start review' })).toBeDisabled()
    expect(screen.getByText(/All 3 reviews of the last 24 hours are used/)).toBeInTheDocument()
  })

  it('offers Clear instead of Start for a month that has its review', async () => {
    const { onClear } = renderPicker(reviewed)
    expect(screen.queryByRole('button', { name: 'Start review' })).toBeNull()
    expect(screen.getByText(/Clear it to review the month again/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Clear review' }))
    expect(onClear).toHaveBeenCalledOnce()
  })

  it('holds Clear while the review runs', () => {
    renderPicker({ ...reviewed, review: { id: 'r1', status: 'running' } }, false)
    expect(screen.getByRole('button', { name: 'Clear review' })).toBeDisabled()
    expect(screen.getByText(/can be cleared once it stops/)).toBeInTheDocument()
  })

  it('reports the picked month', () => {
    const { onMonth } = renderPicker(free)
    fireEvent.change(screen.getByLabelText('Billing month'), { target: { value: '2026-09' } })
    expect(onMonth).toHaveBeenCalledExactlyOnceWith('2026-09')
  })
})
