import type { Transaction } from '../../api/types.ts'
import { formatAmount } from '../../format.ts'

/** What the statement says beyond date, text and amount, e.g. "10 USD, 2 of 3, abroad". */
export function transactionDetails(t: Transaction): string {
  const details: string[] = []
  if (t.originalAmount !== null) {
    details.push(`${formatAmount(t.originalAmount)} ${t.originalCurrency}`)
  }
  if (t.installment !== null) {
    details.push(`${t.installment.number} of ${t.installment.total}`)
  }
  if (t.abroad) details.push('abroad')
  if (t.standingOrder) details.push('standing order')
  return details.join(', ')
}
