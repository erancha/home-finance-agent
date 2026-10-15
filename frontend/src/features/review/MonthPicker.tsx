import type { MonthView } from '../../api/types.ts'
import { formatTimestamp } from '../../format.ts'

/** Reviews are by billing month, so the latest statement is the one charged this month. */
export function currentMonth(today: Date): string {
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
}

function monthNote(view: MonthView, clearable: boolean): string {
  if (view.review !== null) {
    return clearable
      ? 'This month has its review. Clear it to review the month again.'
      : "This month's review is running; it can be cleared once it stops."
  }
  if (view.nextStart !== null) {
    return `All ${view.limit} reviews of the last 24 hours are used; the next can start at ${formatTimestamp(view.nextStart)}.`
  }
  return `${view.startsLeft} of ${view.limit} reviews left in any 24 hours.`
}

interface Props {
  month: string
  /** What the server says of the month; null until it answered. */
  view: MonthView | null
  clearable: boolean
  busy: boolean
  onMonth: (month: string) => void
  onStart: () => void
  onClear: () => void
}

/** A month holds one review: Start is offered while it has none, and Clear once it has. */
export function MonthPicker({ month, view, clearable, busy, onMonth, onStart, onClear }: Props) {
  return (
    <form
      className="month-picker"
      onSubmit={(e) => {
        e.preventDefault()
        onStart()
      }}
    >
      <label>
        Billing month
        <input
          type="month"
          value={month}
          onChange={(e) => onMonth(e.target.value)}
          aria-describedby="billing-month-hint"
          required
        />
      </label>
      {view !== null && view.review !== null ? (
        <button type="button" disabled={busy || !clearable} onClick={onClear}>
          Clear review
        </button>
      ) : (
        <button type="submit" disabled={busy || view === null || view.nextStart !== null}>
          Start review
        </button>
      )}
      <p id="billing-month-hint" className="muted">
        The month the card is charged: October's statement mostly holds September's purchases.
      </p>
      {view !== null && <p className="muted">{monthNote(view, clearable)}</p>}
    </form>
  )
}
