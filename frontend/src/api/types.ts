export type ReviewStatus = 'running' | 'waiting' | 'completed' | 'failed'

/** The signed-in person as their Google account describes them; id is the stable account id. */
export interface User {
  id: string
  email: string | null
  name: string | null
}

export const SIGN_IN_REQUIRED = 'sign-in-required'

export interface Installment {
  number: number
  total: number
}

export interface Transaction {
  id: string
  agent: string
  transactionDate: string
  chargeDate: string
  merchant: string
  rawMerchant: string
  /** Groups a merchant's rows; the home finance agent derives it from the statement text. */
  merchantKey: string
  amount: string
  originalAmount: string | null
  originalCurrency: string | null
  standingOrder: boolean
  abroad: boolean
  installment: Installment | null
  category: string
  /** How sure the card agent is of its own category. */
  confidence: 'high' | 'medium' | 'low'
}

export interface CategorizeQuestion {
  id: string
  kind: 'categorize'
  merchant: string
  /** Every row of the merchant in the review, so the person can recall what each was. */
  transactions: Transaction[]
  options: string[]
}

export interface RemoteInputQuestion {
  id: string
  kind: 'remote-input'
  agent: string
  text: string
  /** Why the agent stopped: 'statement-missing', 'sign-in-required' or a reason of its own. */
  reason: string
  /** The agent's own page where the person resolves the request; null when it has none. */
  link: string | null
  actions: string[]
}

export type Question = CategorizeQuestion | RemoteInputQuestion

export interface CategoryTotal {
  category: string
  spent: string
  limit: string | null
  over: boolean
}

/** A completed review's charges still expected, projected from an earlier completed review. */
export interface ExpectedData {
  /** The month projected from; null when no earlier month has a completed review. */
  basedOn: string | null
  /** Ids are prefixed "expected-", apart from the review's own rows. */
  transactions: Transaction[]
  /** As in TotalsData, for the expected rows. */
  categories: Record<string, Record<string, string>>
  chosen: Record<string, string[]>
  /** The review's totals with the expected spend added. */
  totals: CategoryTotal[]
  standingOrders: string
}

/** Whether a month has its review, and whether a review may start now. */
export interface MonthView {
  month: string
  review: { id: string; status: ReviewStatus } | null
  limit: number
  startsLeft: number
  /** When a start is next allowed; null while starts are left. */
  nextStart: string | null
}

export type Answers = Record<string, string>

/** Merchant key to the category chosen for it. */
export type MerchantCategories = Record<string, string>

export interface TotalsData {
  currency: string
  totals: CategoryTotal[]
  /** The spend charged by standing order, across categories. */
  standingOrders: string
  skipped: string[]
  /** Agent to row id to the category the totals counted the row under. */
  categories: Record<string, Record<string, string>>
  /** Agent to the ids of rows whose category the person chose, overruling the card agent. */
  chosen: Record<string, string[]>
  /** The categories a person may assign. */
  options: string[]
}

/** Every event's data carries `at`, the ISO time the server logged it. */
type Stamped<T> = T & { at: string }

export type ReviewEvent =
  | { type: 'agent.discovered'; data: Stamped<{ agent: string; url: string; streaming: boolean }> }
  | { type: 'agent.status'; data: Stamped<{ agent: string; state: string; text: string | null }> }
  | {
      type: 'transactions.batch'
      data: Stamped<{ agent: string; month: string; count: number; transactions: Transaction[] }>
    }
  | { type: 'review.question'; data: Stamped<{ questions: Question[] }> }
  | { type: 'review.totals'; data: Stamped<TotalsData> }
  | { type: 'review.writing'; data: Stamped<Record<never, never>> }
  | { type: 'review.report'; data: Stamped<{ text: string }> }
  | { type: 'review.failed'; data: Stamped<{ message: string }> }
  /** The review's status changed; a failure is announced by review.failed instead. */
  | { type: 'review.status'; data: Stamped<{ status: Exclude<ReviewStatus, 'failed'> }> }

export type ReviewEventType = ReviewEvent['type']

/** An event with its per-review sequence number, which the stream sends as the frame id. */
export type SequencedEvent = ReviewEvent & { seq: number }

export const REVIEW_EVENT_TYPES: readonly ReviewEventType[] = [
  'agent.discovered',
  'agent.status',
  'transactions.batch',
  'review.question',
  'review.totals',
  'review.writing',
  'review.report',
  'review.failed',
  'review.status',
]
