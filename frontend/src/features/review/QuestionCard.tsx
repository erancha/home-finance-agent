import { useState } from 'react'
import type { Answers, Question, Transaction } from '../../api/types.ts'
import { formatAmount } from '../../format.ts'
import { transactionDetails } from './transactionDetails.ts'

interface Props {
  questions: Question[]
  submitting: boolean
  onSubmit: (answers: Answers) => void
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
            <td>{t.transactionDate}</td>
            <td>{t.agent}</td>
            <td dir="auto">{t.rawMerchant}</td>
            <td>{formatAmount(t.amount)}</td>
            <td>{transactionDetails(t)}</td>
          </tr>
        ))}
        </tbody>
      </table>
    </div>
  )
}

function QuestionInput({
  question,
  value,
  onChange,
}: {
  question: Question
  value: string | undefined
  onChange: (value: string | undefined) => void
}) {
  if (question.kind === 'categorize') {
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
  return (
    <div className="question">
      <p className="question-name">
        <strong>{question.agent}</strong>
      </p>
      <p dir="auto">{question.text}</p>
      {question.link !== null && (
        <p>
          <a href={question.link} target="_blank" rel="noopener noreferrer">
            Open the {question.agent} statements page
          </a>
        </p>
      )}
      {question.actions.map((action) => (
        <button
          key={action}
          type="button"
          aria-pressed={value === action}
          className={value === action ? 'chosen' : undefined}
          onClick={() => onChange(action)}
        >
          {action}
        </button>
      ))}
    </div>
  )
}

/** Categorize questions are optional: a merchant left unanswered keeps its card agent's guess. */
export function QuestionCard({ questions, submitting, onSubmit }: Props) {
  const [answers, setAnswers] = useState<Answers>({})
  const ready = questions.every((q) => q.kind === 'categorize' || answers[q.id] !== undefined)
  const answer = (id: string, value: string | undefined) =>
    setAnswers((current) =>
      value === undefined
        ? Object.fromEntries(Object.entries(current).filter(([key]) => key !== id))
        : { ...current, [id]: value },
    )
  return (
    <section className="question-card">
      <h2>Questions</h2>
      {questions.some((q) => q.kind === 'categorize') && (
        <p className="muted">
          The card agent is unsure of these merchants. Categorize the ones you recognize; the rest
          keep the card agent&apos;s guess.
        </p>
      )}
      {questions.map((q) => (
        <QuestionInput
          key={q.id}
          question={q}
          value={answers[q.id]}
          onChange={(value) => answer(q.id, value)}
        />
      ))}
      <button type="button" disabled={!ready || submitting} onClick={() => onSubmit(answers)}>
        Send answers
      </button>
    </section>
  )
}
