import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as auth from '../../api/auth.ts'
import type { Question, Transaction } from '../../api/types.ts'
import { FakeGoogleIdentity } from '../../test/fakeGoogle.ts'
import { QuestionCard } from './QuestionCard.tsx'

vi.mock('../../api/auth.ts')

beforeEach(() => {
  vi.mocked(auth.getAuthConfig).mockResolvedValue({ clientId: 'hfm-test-client' })
  vi.mocked(auth.signIn).mockResolvedValue({ id: '1001', email: 'dana@example.com', name: 'Dana' })
})

const row: Transaction = {
  id: 't1', agent: 'amex', transactionDate: '2026-09-02', chargeDate: '2026-10-02',
  merchant: 'שופרסל', rawMerchant: 'SHUFERSAL', merchantKey: 'shufersal', amount: '120.50',
  originalAmount: null,
  originalCurrency: null, standingOrder: false, abroad: false, installment: null,
  category: 'uncategorized', confidence: 'low',
}
const foreign: Transaction = {
  ...row, id: 't2', transactionDate: '2026-09-17', rawMerchant: 'SHUFERSAL ONLINE',
  amount: '37.20', originalAmount: '9.99', originalCurrency: 'USD', abroad: true,
  installment: { number: 2, total: 3 },
}
const categorize: Question = {
  id: 'cat:שופרסל', kind: 'categorize', merchant: 'שופרסל', transactions: [row, foreign],
  options: ['groceries', 'dining'],
}
const otherMerchant: Question = {
  ...categorize, id: 'cat:gett', merchant: 'Gett', transactions: [{ ...row, id: 't3' }],
}
const remote: Question = {
  id: 'remote:amex', kind: 'remote-input', agent: 'amex', text: 'Enter the SMS code',
  reason: 'auth', link: null, actions: ['continue', 'skip'],
}

describe('QuestionCard', () => {
  it("lists each of a merchant's rows with its date, statement text and details", () => {
    render(<QuestionCard questions={[categorize]} submitting={false} onSubmit={vi.fn()} />)
    const table = screen.getByRole('table', { name: 'Charges at שופרסל' })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.map((r) => within(r).getAllByRole('cell').map((c) => c.textContent))).toEqual([
      ['2026-09-02', 'amex', 'SHUFERSAL', '121', ''],
      ['2026-09-17', 'amex', 'SHUFERSAL ONLINE', '37', '10 USD, 2 of 3, abroad'],
    ])
  })

  it('continues with the merchants answered and "continue" to every card agent asking', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(
      <QuestionCard
        questions={[categorize, otherMerchant, remote]}
        submitting={false}
        onSubmit={onSubmit}
      />,
    )
    await user.selectOptions(screen.getByLabelText('Category for שופרסל'), 'dining')
    await user.click(screen.getByRole('button', { name: 'continue' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({
      'cat:שופרסל': 'dining',
      'remote:amex': 'continue',
    })
  })

  it('skips a card agent at once, keeping the categories chosen so far', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<QuestionCard questions={[categorize, remote]} submitting={false} onSubmit={onSubmit} />)
    await user.selectOptions(screen.getByLabelText('Category for שופרסל'), 'dining')
    await user.click(screen.getByRole('button', { name: 'skip amex' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({
      'cat:שופרסל': 'dining',
      'remote:amex': 'skip',
    })
  })

  it('drops an answer set back to "not sure"', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<QuestionCard questions={[categorize]} submitting={false} onSubmit={onSubmit} />)
    const select = screen.getByLabelText('Category for שופרסל')

    await user.selectOptions(select, 'dining')
    await user.selectOptions(select, 'Not sure: leave uncategorized')
    await user.click(screen.getByRole('button', { name: 'continue' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({})
  })

  it("offers to keep the card agent's guess when not sure", () => {
    const guessed: Question = {
      ...categorize, transactions: [{ ...row, category: 'groceries' }],
    }
    render(<QuestionCard questions={[guessed]} submitting={false} onSubmit={vi.fn()} />)
    expect(screen.getByRole('option', { name: 'Not sure: keep groceries' })).toBeInTheDocument()
  })

  it('offers a statement request only its page, as a button in a new tab, and continue', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const linked: Question = {
      ...remote, text: 'No statement covers 2026-10.', reason: 'statement-missing',
      link: 'http://localhost:8020/statements.html', actions: ['continue'],
    }
    render(<QuestionCard questions={[linked]} submitting={false} onSubmit={onSubmit} />)

    expect(screen.queryByText('No statement covers 2026-10.')).not.toBeInTheDocument()
    const link = screen.getByRole('link', { name: 'Open the amex statements page' })
    expect(link).toHaveAttribute('href', 'http://localhost:8020/statements.html')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(link).toHaveClass('button', 'prerequisite')
    expect(screen.queryByRole('button', { name: 'skip amex' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'continue' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ 'remote:amex': 'continue' })
  })

  it('offers to sign in again, then only continue, when the agent could not verify the person', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const signIn: Question = {
      ...remote, reason: 'sign-in-required', actions: ['continue'],
      text: 'amex-agent could not verify who you are (expired). Sign in again and continue.',
    }
    render(<QuestionCard questions={[signIn]} submitting={false} onSubmit={onSubmit} />)

    expect(screen.queryByText(signIn.text)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'skip amex' })).not.toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Continue with Google' }))
    expect(auth.signIn).toHaveBeenCalledExactlyOnceWith(FakeGoogleIdentity.credential)
    expect(await screen.findByText(/Signed in again as dana@example.com/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'continue' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ 'remote:amex': 'continue' })
  })

  it('disables continue and skip while an answer is in flight', () => {
    render(<QuestionCard questions={[categorize, remote]} submitting onSubmit={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'continue' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'skip amex' })).toBeDisabled()
  })
})
