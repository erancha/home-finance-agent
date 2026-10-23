import { useState } from 'react'
import { CollapsibleSection } from '../../components/CollapsibleSection.tsx'
import type {
  MerchantCategories,
  ReviewEvent,
  TotalsData,
  Transaction,
} from '../../api/types.ts'
import { formatAmount } from '../../format.ts'
import { transactionDetails } from './transactionDetails.ts'

/** A "continue" can resend rows already shown, so rows are unique by agent and id. */
export function uniqueTransactions(events: ReviewEvent[]): Transaction[] {
  const rows = new Map<string, Transaction>()
  for (const event of events) {
    if (event.type !== 'transactions.batch') continue
    for (const row of event.data.transactions) rows.set(`${row.agent}\u0000${row.id}`, row)
  }
  return [...rows.values()]
}

interface Props {
  events: ReviewEvent[]
  /** Charges the month still expects; listed first, unfolding the section, never recategorized. */
  expected: Transaction[]
  /** The latest totals; each row shows the category they counted it under, once they exist. */
  totals: TotalsData | null
  /** Set while the review is completed and idle; resolves to whether the server accepted. */
  onRecategorize: ((categories: MerchantCategories) => Promise<boolean>) | null
  /** Only rows counted under this category are listed; null lists all. */
  category: string | null
  /** Only standing-order rows are listed. */
  standingOrders: boolean
  onStandingOrders: (only: boolean) => void
  /** The review is still running or waiting in this page, not reopened after it ended. */
  inProgress: boolean
  /** Counts the choices made in the totals; each one unfolds the section. */
  picks: number
}

/** The charges still expected, when shown, then every row the card agents sent; folded so the long
 * list does not push the totals down. */
export function TransactionsSection({
  events,
  expected,
  totals,
  onRecategorize,
  category,
  standingOrders,
  onStandingOrders,
  inProgress,
  picks,
}: Props) {
  const [pending, setPending] = useState<MerchantCategories>({})
  const [applying, setApplying] = useState(false)
  // Counts the category changes; each one remounts the apply button so it takes focus and its
  // edge sweep starts over.
  const [edits, setEdits] = useState(0)
  // Latched: the first low-confidence row seen while the review is in progress unfolds the
  // section once; folding it afterwards, or the review ending, does not reopen or close it.
  const [unfoldedForLow, setUnfoldedForLow] = useState(false)
  const all = uniqueTransactions(events)
  if (!unfoldedForLow && inProgress && all.some((t) => t.confidence === 'low')) {
    setUnfoldedForLow(true)
  }
  const isExpected = new Set(expected)
  const rows = [...expected, ...all]
  if (rows.length === 0) return null
  // A row streamed after the latest totals is not counted yet and shows the card's category.
  const counted = (t: Transaction) => totals?.categories[t.agent]?.[t.id] ?? t.category
  const chosen = (t: Transaction) => totals?.chosen[t.agent]?.includes(t.id) === true
  const transactions = rows.filter(
    (t) => (category === null || counted(t) === category) && (!standingOrders || t.standingOrder),
  )
  const filters = [category, standingOrders ? 'standing orders' : null].filter((f) => f !== null)
  const title =
    filters.length === 0
      ? `Raw transactions (${rows.length})`
      : `Raw transactions: ${filters.join(', ')} (${transactions.length} of ${rows.length})`
  const editable = onRecategorize !== null && totals !== null && !applying
  const changed = Object.keys(pending).length

  async function apply() {
    if (onRecategorize === null) return
    setApplying(true)
    if (await onRecategorize(pending)) setPending({})
    setApplying(false)
  }

  return (
    <CollapsibleSection
      key={`${picks}:${unfoldedForLow}:${expected.length > 0}`}
      title={title}
      defaultCollapsed={picks === 0 && !unfoldedForLow && expected.length === 0}
    >
      <label>
        <input
          type="checkbox"
          checked={standingOrders}
          onChange={(e) => onStandingOrders(e.target.checked)}
        />{' '}
        Standing orders only
      </label>
      {editable && (
        <p className="muted">
          A category chosen here applies to every charge of that merchant and is remembered.
        </p>
      )}
      <div className="table-scroll">
        <table className="transactions" aria-label="Raw transactions">
          <thead>
            <tr>
              <th>Date</th>
              <th>Agent</th>
              <th>Merchant</th>
              <th>Amount</th>
              <th>Details</th>
              <th>Category</th>
              <th>AI confidence</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((t) => (
              <tr key={`${t.agent}/${t.id}`} className={isExpected.has(t) ? 'expected' : undefined}>
                <td>{t.transactionDate}</td>
                <td>{t.agent}</td>
                <td
                  dir="auto"
                  className="merchant"
                  title={t.rawMerchant !== t.merchant ? t.rawMerchant : undefined}
                >
                  {t.merchant}
                </td>
                <td>{formatAmount(t.amount)}</td>
                <td>
                  {[isExpected.has(t) ? 'expected' : '', transactionDetails(t)]
                    .filter((part) => part !== '')
                    .join(', ')}
                </td>
                <td>
                  {editable && !isExpected.has(t) ? (
                    <select
                      aria-label={`Category for ${t.merchant} on ${t.transactionDate}`}
                      value={pending[t.merchantKey] ?? counted(t)}
                      onChange={(e) => {
                        setPending((current) => ({ ...current, [t.merchantKey]: e.target.value }))
                        setEdits((count) => count + 1)
                      }}
                    >
                      {counted(t) === 'uncategorized' && (
                        <option value="uncategorized" disabled>
                          uncategorized
                        </option>
                      )}
                      {totals.options.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  ) : (
                    counted(t)
                  )}
                </td>
                {chosen(t) ? (
                <td>{t.confidence} (overruled)</td>
              ) : (
                <td className={`confidence-${t.confidence}`}>{t.confidence}</td>
              )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {onRecategorize !== null && (
        <button
          key={edits}
          type="button"
          className={changed > 0 ? 'border-sweep' : undefined}
          autoFocus={edits > 0}
          disabled={changed === 0 || applying}
          onClick={apply}
        >
          Apply categories{changed > 0 && ` (${changed} merchant${changed === 1 ? '' : 's'})`}
        </button>
      )}
    </CollapsibleSection>
  )
}
