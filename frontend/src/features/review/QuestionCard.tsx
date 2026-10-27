import { useState } from 'react'
import { SIGN_IN_REQUIRED } from '../../api/types.ts'
import type { Answers, Question, Transaction, User } from '../../api/types.ts'
import { GoogleSignIn } from '../../auth/GoogleSignIn.tsx'
import { displayName } from '../../auth/SessionHeader.tsx'
import { formatDate, formatShekels } from '../../format.ts'
import { transactionDetails } from './transactionDetails.ts'

interface Props {
  questions: Question[]
  submitting: boolean
  onSubmit: (answers: Answers) => void
}

const CONTINUE = 'continue'

/** Every card agent question offers "continue"; the card's one button answers them all with it. */
function continueAll(questions: Question[]): Answers {
  const remote = questions.filter((q) => q.kind === 'remote-input')
  for (const q of remote) {
    if (!q.actions.includes(CONTINUE)) throw new Error(`question ${q.id} offers no continue`)
  }
  return Object.fromEntries(remote.map((q) => [q.id, CONTINUE]))
}

/** Rows left unanswered keep the category their card agent guessed. */
function notSureLabel(transactions: Transaction[]): string {
  const guesses = new Set(transactions.map((t) => t.category))
  if (guesses.size > 1) return "Not sure: keep the card agents' categories"
  const [guess] = guesses
  return guess === 'uncategorized' ? 'Not sure: leave uncategorized' : `Not sure: keep ${guess}`
}

function MerchantRows({
  merchant,
  transactions,
}: {
  merchant: string
  transactions: Transaction[]
}) {
  return (
    <div className="question-rows">
      <table aria-label={`Charges at ${merchant}`}>
      <thead>
        <tr>
          <th>Date</th>
          <th>Card</th>
          <th>Statement text</th>
          <th>Amount</th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody>
        {transactions.map((t) => (
          <tr key={`${t.agent}/${t.id}`}>
            <td>{formatDate(t.transactionDate)}</td>
            <td>{t.agent}</td>
            <td dir="auto">{t.rawMerchant}</td>
            <td>{formatShekels(t.amount)}</td>
            <td>{transactionDetails(t)}</td>
          </tr>
        ))}
        </tbody>
      </table>
    </div>
  )
}

function MerchantQuestion({
  question,
  value,
  onChange,
}: {
  question: Question & { kind: 'categorize' }
  value: string | undefined
  onChange: (value: string | undefined) => void
}) {
  return (
    <div className="question">
      <p className="question-name">
        <strong dir="auto">{question.merchant}</strong>
      </p>
      <MerchantRows merchant={question.merchant} transactions={question.transactions} />
      <select
        aria-label={`Category for ${question.merchant}`}
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)}
      >
        <option value="">{notSureLabel(question.transactions)}</option>
        {question.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  )
}

/**
 * A card agent's question is answered by the card's one "continue" button. Any other action it
 * offers (a "skip") is its own button, which submits the card at once with that answer.
 */
function AgentQuestion({
  question,
  submitting,
  onAction,
}: {
  question: Question & { kind: 'remote-input' }
  submitting: boolean
  onAction: (action: string) => void
}) {
  return (
    <div className="question">
      <p className="question-name">
        <strong>{question.agent}</strong>
      </p>
      {question.reason === SIGN_IN_REQUIRED && <SignInAgain />}
      {question.link !== null && (
        <p>
          <a
            className="button prerequisite"
            href={question.link}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open the {question.agent} statements page
          </a>
        </p>
      )}
      {question.actions
        .filter((action) => action !== CONTINUE)
        .map((action) => (
          <button
            key={action}
            type="button"
            className="secondary"
            disabled={submitting}
            onClick={() => onAction(action)}
          >
            {action} {question.agent}
          </button>
        ))}
    </div>
  )
}

/**
 * A card agent could not verify the person: signing in again replaces the session cookie, and the
 * continue that follows carries the fresh token.
 */
function SignInAgain() {
  const [refreshed, setRefreshed] = useState<User | null>(null)
  if (refreshed !== null) {
    return <p className="muted">Signed in again as {displayName(refreshed)}; now continue.</p>
  }
  return <GoogleSignIn onSignedIn={setRefreshed} text="continue_with" />
}

/**
 * One "continue" button answers the whole card: the categories chosen, and "continue" to every
 * card agent asking. Merchants left unanswered keep their guess, so the button is always live.
 */
export function QuestionCard({ questions, submitting, onSubmit }: Props) {
  const [categories, setCategories] = useState<Answers>({})
  const choose = (id: string, value: string | undefined) =>
    setCategories((current) =>
      value === undefined
        ? Object.fromEntries(Object.entries(current).filter(([key]) => key !== id))
        : { ...current, [id]: value },
    )
  const submit = (overrides: Answers = {}) =>
    onSubmit({ ...categories, ...continueAll(questions), ...overrides })
  return (
    <section className="question-card">
      <h2>Questions</h2>
      {questions.some((q) => q.kind === 'categorize') && (
        <p className="muted">
          The card agent is unsure of these merchants. Categorize the ones you recognize; the rest
          keep the card agent&apos;s guess.
        </p>
      )}
      {questions.map((q) =>
        q.kind === 'categorize' ? (
          <MerchantQuestion
            key={q.id}
            question={q}
            value={categories[q.id]}
            onChange={(value) => choose(q.id, value)}
          />
        ) : (
          <AgentQuestion
            key={q.id}
            question={q}
            submitting={submitting}
            onAction={(action) => submit({ [q.id]: action })}
          />
        ),
      )}
      <button type="button" disabled={submitting} onClick={() => submit()}>
        {CONTINUE}
      </button>
    </section>
  )
}
