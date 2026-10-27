import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as agentsApi from '../../api/agents.ts'
import * as api from '../../api/reviews.ts'
import type { ExpectedData, MonthView, Transaction } from '../../api/types.ts'
import { FakeEventSource } from '../../test/fakeEventSource.ts'
import { ApiException } from '../../api/client.ts'
import { ReviewPage } from './ReviewPage.tsx'

vi.mock('../../api/reviews.ts')
vi.mock('../../api/agents.ts')

const row: Transaction = {
  id: 't1', agent: 'amex', transactionDate: '2026-09-02', chargeDate: '2026-10-02',
  merchant: 'שופרסל', rawMerchant: 'SHUFERSAL', merchantKey: 'shufersal', amount: '120.50',
  originalAmount: null,
  originalCurrency: null, standingOrder: false, abroad: false, installment: null,
  category: 'uncategorized', confidence: 'medium',
}
const question = {
  id: 'cat:שופרסל',
  kind: 'categorize' as const,
  merchant: 'שופרסל',
  options: ['groceries', 'dining'],
  transactions: [row],
}
const remoteQuestion = {
  id: 'remote:amex', kind: 'remote-input' as const, agent: 'amex', text: 'Enter the SMS code',
  reason: 'auth', link: null, actions: ['continue', 'skip'],
}
const totals = {
  currency: 'ILS',
  totals: [{ category: 'dining', spent: '120.50', limit: '100.00', over: true }],
  categories: { amex: { t1: 'dining' } },
  chosen: {},
  options: ['groceries', 'dining'],
  standingOrders: '0.00',
  skipped: [],
}

const gymExpected: Transaction = {
  ...row, id: 'expected-g1', merchant: 'וים קלאבס', merchantKey: 'gym', amount: '250.00',
  standingOrder: true, category: 'health', confidence: 'high',
}
const expected: ExpectedData = {
  basedOn: '2026-08',
  transactions: [gymExpected],
  categories: { amex: { 'expected-g1': 'health' } },
  chosen: { amex: ['expected-g1'] },
  totals: [
    ...totals.totals,
    { category: 'health', spent: '250.00', limit: null, over: false },
  ],
  standingOrders: '250.00',
}

/** Runs a review to completion, with one raw row counted under dining. */
async function completedReview() {
  const user = await startReview()
  emit('transactions.batch', { agent: 'amex', month: '2026-09', count: 1, transactions: [row] }, 1)
  emit('review.totals', totals, 2)
  emit('review.report', { text: 'Budget review for 2026-09' }, 3)
  emit('review.status', { status: 'completed' }, 4)
  return user
}

/** The review the server holds for the month asked about; set by a start or a test. */
let standing: MonthView['review'] = null

function monthView(month: string): MonthView {
  return { month, review: standing, limit: 3, startsLeft: standing === null ? 3 : 2, nextStart: null }
}

/** Sends an event as the server would, stamped with the time it was logged. */
function emit(type: string, data: object, seq: number) {
  const stamped = JSON.stringify({ ...data, at: '2026-10-14T09:00:00+00:00' })
  act(() => FakeEventSource.last().emit(type, stamped, String(seq)))
}

async function startReview() {
  const user = userEvent.setup()
  render(<ReviewPage />)
  const start = screen.getByRole('button', { name: 'Start review' })
  await waitFor(() => expect(start).toBeEnabled())
  await user.click(start)
  await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
  return user
}

beforeEach(() => {
  FakeEventSource.reset()
  vi.stubGlobal('EventSource', FakeEventSource)
  standing = null
  vi.mocked(api.getMonth).mockImplementation((month) => Promise.resolve(monthView(month)))
  vi.mocked(api.startReview).mockImplementation(() => {
    standing = { id: 'r1', status: 'running' }
    return Promise.resolve({ id: 'r1' })
  })
  vi.mocked(api.answerReview).mockResolvedValue(undefined)
  vi.mocked(agentsApi.getAgents).mockResolvedValue({ agents: ['amex'] })
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetAllMocks()
  window.history.replaceState(null, '', '/')
})

describe('ReviewPage', () => {
  it('explains that no card agent is connected and offers no start', async () => {
    vi.mocked(agentsApi.getAgents).mockResolvedValue({ agents: [] })
    render(<ReviewPage />)
    expect(await screen.findByRole('status')).toHaveTextContent('No card agents are connected yet.')
    expect(screen.queryByRole('button', { name: 'Start review' })).toBeNull()
  })

  it('runs a review from start to report on its events alone', async () => {
    const user = await startReview()
    expect(api.startReview).toHaveBeenCalledWith(expect.stringMatching(/^\d{4}-\d{2}$/))

    emit('transactions.batch', {
      agent: 'amex', month: '2026-09', count: 1, transactions: [row],
    }, 1)
    emit('review.question', { questions: [question] }, 2)
    expect(screen.queryByRole('combobox')).toBeNull()
    emit('review.status', { status: 'waiting' }, 3)
    expect(screen.getByText('1 transactions from amex')).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Raw transactions' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Raw transactions (1)' }))
    const raw = screen.getByRole('table', { name: 'Raw transactions' })
    expect(within(raw).getByText('שופרסל')).toHaveAttribute('dir', 'auto')

    await user.selectOptions(screen.getByRole('combobox', { name: 'Category for שופרסל' }), 'dining')
    await user.click(screen.getByRole('button', { name: 'continue' }))
    expect(api.answerReview).toHaveBeenCalledExactlyOnceWith('r1', { 'cat:שופרסל': 'dining' })
    await waitFor(() => expect(screen.queryByRole('combobox')).not.toBeInTheDocument())

    const progress = () => screen.getByRole('button', { name: 'Progress' })
    expect(progress()).toHaveAttribute('aria-expanded', 'true')
    emit('review.status', { status: 'running' }, 4)
    emit('review.totals', totals, 5)
    emit('review.report', { text: 'Budget review for 2026-09' }, 6)
    expect(screen.getByText('₪121 / ₪100')).toBeInTheDocument()
    expect(screen.getByText('Budget review for 2026-09')).toBeInTheDocument()
    expect(progress()).toHaveAttribute('aria-expanded', 'true')
    emit('review.status', { status: 'completed' }, 7)
    expect(progress()).toHaveAttribute('aria-expanded', 'false')
  })

  it('keeps the raw transactions folded when a reload replays a review that already completed', async () => {
    standing = { id: 'r1', status: 'completed' }
    render(<ReviewPage />)
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    const low = { ...row, confidence: 'low' as const }
    emit('review.status', { status: 'running' }, 1)
    emit('transactions.batch', { agent: 'amex', month: '2026-09', count: 1, transactions: [low] }, 2)
    emit('review.question', { questions: [question] }, 3)
    emit('review.status', { status: 'waiting' }, 4)
    emit('review.status', { status: 'running' }, 5)
    emit('review.totals', totals, 6)
    emit('review.report', { text: 'Budget review for 2026-09' }, 7)
    emit('review.status', { status: 'completed' }, 8)

    expect(await screen.findByRole('button', { name: 'Raw transactions (1)' }))
      .toHaveAttribute('aria-expanded', 'false')
  })

  it('lists the raw transactions of the category chosen in the totals, and all from Totals', async () => {
    const user = await startReview()
    emit('transactions.batch', { agent: 'amex', month: '2026-09', count: 1, transactions: [row] }, 1)
    emit('review.totals', totals, 2)

    await user.click(screen.getByRole('button', { name: 'dining' }))
    const filtered = screen.getByRole('button', { name: 'Raw transactions: dining (1 of 1)' })
    expect(filtered).toHaveAttribute('aria-expanded', 'true')

    await user.click(screen.getByRole('button', { name: 'Totals' }))
    expect(screen.getByRole('button', { name: 'Raw transactions (1)' }))
      .toHaveAttribute('aria-expanded', 'true')
  })

  it('lists the standing orders chosen in the totals until the box is cleared', async () => {
    const user = await startReview()
    const gym = { ...row, id: 't2', merchant: 'וים קלאבס', standingOrder: true }
    const rows = [row, gym]
    emit('transactions.batch', { agent: 'amex', month: '2026-09', count: 2, transactions: rows }, 1)
    emit('review.totals', { ...totals, standingOrders: '120.50' }, 2)

    await user.click(screen.getByRole('button', { name: 'Standing orders' }))
    expect(screen.getByRole('button', { name: 'Raw transactions: standing orders (1 of 2)' }))
      .toHaveAttribute('aria-expanded', 'true')

    await user.click(screen.getByRole('checkbox', { name: 'Standing orders only' }))
    expect(screen.getByRole('button', { name: 'Raw transactions (2)' })).toBeInTheDocument()
  })

  it('recategorizes a merchant from the raw transactions once the review completed', async () => {
    const user = await startReview()
    emit('transactions.batch', { agent: 'amex', month: '2026-09', count: 1, transactions: [row] }, 1)
    await user.click(screen.getByRole('button', { name: 'Raw transactions (1)' }))
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()

    emit('review.totals', totals, 2)
    emit('review.report', { text: 'Budget review for 2026-09' }, 3)
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    emit('review.status', { status: 'completed' }, 4)
    const category = screen.getByRole('combobox', { name: 'Category for שופרסל on 2026-09-02' })
    expect(category).toHaveValue('dining')
    await user.selectOptions(category, 'groceries')
    await user.click(screen.getByRole('button', { name: 'Apply categories (1 merchant)' }))

    expect(api.recategorizeReview).toHaveBeenCalledExactlyOnceWith('r1', { shufersal: 'groceries' })
    await waitFor(() => expect(screen.queryByRole('combobox')).not.toBeInTheDocument())
    emit('review.status', { status: 'running' }, 5)
    emit('review.totals', { ...totals, categories: { amex: { t1: 'groceries' } } }, 6)
    emit('review.report', { text: 'Rewritten' }, 7)
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    emit('review.status', { status: 'completed' }, 8)
    expect(screen.getByRole('combobox', { name: /Category for/ })).toHaveValue('groceries')
    expect(screen.getByText('Rewritten')).toBeInTheDocument()
  })

  it('puts the month of the started review in the URL', async () => {
    await startReview()
    expect(new URLSearchParams(window.location.search).get('month')).toBe(
      vi.mocked(api.startReview).mock.calls[0][0],
    )
  })

  it("opens the review of the month in the URL and offers Clear, not Start", async () => {
    window.history.replaceState(null, '', '/?month=2026-09')
    standing = { id: 'r1', status: 'waiting' }
    render(<ReviewPage />)

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    expect(api.getMonth).toHaveBeenCalledExactlyOnceWith('2026-09')
    expect(FakeEventSource.last().url).toBe('/api/reviews/r1/events')
    emit('review.question', { questions: [question] }, 1)

    expect(screen.getByRole('combobox', { name: 'Category for שופרסל' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start review' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Clear review' })).toBeEnabled()
  })

  it('hides the review once another month without one is picked', async () => {
    const user = await startReview()
    standing = null
    const input = screen.getByLabelText('Billing month')
    await user.clear(input)
    await user.type(input, '2020-01')

    await waitFor(() => expect(screen.getByRole('button', { name: 'Start review' })).toBeEnabled())
    expect(screen.queryByRole('button', { name: 'Clear review' })).toBeNull()
    expect(new URLSearchParams(window.location.search).get('month')).toBe('2020-01')
  })

  it('shows why the month cannot be read', async () => {
    vi.mocked(api.getMonth).mockRejectedValue(new ApiException(500, 'Internal Server Error'))
    render(<ReviewPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Internal Server Error')
    expect(screen.getByRole('button', { name: 'Start review' })).toBeDisabled()
  })

  it('shows a question posed again before the answer was acknowledged', async () => {
    let acknowledge: () => void = () => undefined
    vi.mocked(api.answerReview).mockReturnValue(
      new Promise((resolve) => {
        acknowledge = () => resolve(undefined)
      }),
    )
    const user = await startReview()
    emit('review.question', { questions: [remoteQuestion] }, 1)
    emit('review.status', { status: 'waiting' }, 2)
    await user.click(screen.getByRole('button', { name: 'continue' }))
    expect(screen.getByRole('button', { name: 'continue' })).toBeDisabled()

    emit('review.status', { status: 'running' }, 3)
    emit('review.question', { questions: [remoteQuestion] }, 4)
    emit('review.status', { status: 'waiting' }, 5)
    await act(async () => acknowledge())

    expect(screen.getByRole('button', { name: 'continue' })).toBeEnabled()
  })

  it('shows a failure once, prominently', async () => {
    await startReview()
    emit('review.failed', { message: 'agent unreachable' }, 1)
    expect(screen.getByRole('alert')).toHaveTextContent('Review failed: agent unreachable')
    expect(screen.getAllByText(/agent unreachable/)).toHaveLength(1)
  })

  it('shows a malformed frame as a stream error', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    await startReview()
    act(() => FakeEventSource.last().emit('review.report', '{oops', '1'))
    expect(screen.getByRole('alert')).toHaveTextContent('Stream error: malformed review.report frame')
    error.mockRestore()
  })

  it('shows a refused start', async () => {
    vi.mocked(api.startReview).mockRejectedValue(new ApiException(429, '3 reviews were started'))
    const user = userEvent.setup()
    render(<ReviewPage />)
    const start = screen.getByRole('button', { name: 'Start review' })
    await waitFor(() => expect(start).toBeEnabled())
    await user.click(start)
    expect(await screen.findByRole('alert')).toHaveTextContent('3 reviews were started')
  })

  it('clears a review once it ended, offering Start again', async () => {
    vi.mocked(api.clearReview).mockImplementation(() => {
      standing = null
      return Promise.resolve()
    })
    const user = await startReview()
    expect(screen.getByRole('button', { name: 'Clear review' })).toBeDisabled()

    emit('review.failed', { message: 'agent unreachable' }, 1)
    await user.click(screen.getByRole('button', { name: 'Clear review' }))

    expect(api.clearReview).toHaveBeenCalledExactlyOnceWith('r1')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start review' })).toBeEnabled())
    expect(screen.queryByText(/agent unreachable/)).toBeNull()
  })

  it('shows the error text when answers are refused', async () => {
    vi.mocked(api.answerReview).mockRejectedValue(new Error('review is running'))
    const user = await startReview()
    emit('review.question', { questions: [question] }, 1)
    emit('review.status', { status: 'waiting' }, 2)
    await user.selectOptions(screen.getByRole('combobox'), 'dining')
    await user.click(screen.getByRole('button', { name: 'continue' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('review is running')
  })

  it('adds the charges still expected to the rows and totals, and dims the report', async () => {
    vi.mocked(api.getExpected).mockResolvedValue(expected)
    const user = await completedReview()
    const box = screen.getByRole('checkbox', { name: 'Include expected charges' })
    const report = () => screen.getByText('Budget review for 2026-09').closest('section')

    await user.click(box)

    expect(api.getExpected).toHaveBeenCalledExactlyOnceWith('r1')
    expect(await screen.findByText('Expected charges are projected from 2026-08.'))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Raw transactions (2)' }))
      .toHaveAttribute('aria-expanded', 'true')
    const raw = screen.getByRole('table', { name: 'Raw transactions' })
    const [first] = within(raw).getAllByRole('row').slice(1)
    expect(first).toHaveClass('expected')
    expect(within(first).getByText('וים קלאבס')).toBeInTheDocument()
    expect(within(first).getByText('high (overruled)')).toBeInTheDocument()
    expect(within(raw).getByText('expected, standing order')).toBeInTheDocument()
    expect(screen.getAllByRole('combobox')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'health' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Standing orders' }).closest('p'))
      .toHaveTextContent('Standing orders ₪250 across categories')
    expect(report()).toHaveClass('out-of-sync')

    await user.click(box)
    expect(screen.getByRole('button', { name: 'Raw transactions (1)' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'health' })).toBeNull()
    expect(report()).not.toHaveClass('out-of-sync')

    await user.click(box)
    expect(screen.getByRole('button', { name: 'Raw transactions (2)' })).toBeInTheDocument()
    expect(api.getExpected).toHaveBeenCalledOnce()
  })

  it('asks again for the expected charges once the totals changed', async () => {
    vi.mocked(api.getExpected).mockResolvedValue(expected)
    const user = await completedReview()
    await user.click(screen.getByRole('checkbox', { name: 'Include expected charges' }))
    await waitFor(() => expect(api.getExpected).toHaveBeenCalledOnce())

    emit('review.status', { status: 'running' }, 5)
    emit('review.totals', { ...totals, categories: { amex: { t1: 'groceries' } } }, 6)
    emit('review.status', { status: 'completed' }, 7)

    await waitFor(() => expect(api.getExpected).toHaveBeenCalledTimes(2))
  })

  it('says when no earlier month has a completed review to project from', async () => {
    vi.mocked(api.getExpected).mockResolvedValue({
      basedOn: null, transactions: [], categories: {}, chosen: {}, totals: totals.totals,
      standingOrders: '0.00',
    })
    const user = await completedReview()
    await user.click(screen.getByRole('checkbox', { name: 'Include expected charges' }))
    expect(await screen.findByText('No earlier month has a completed review to project from.'))
      .toBeInTheDocument()
  })

  it('shows the expected charges once a review that skipped a card agent completed', async () => {
    vi.mocked(api.getExpected).mockResolvedValue(expected)
    const user = await startReview()
    emit('transactions.batch', { agent: 'amex', month: '2026-09', count: 1, transactions: [row] }, 1)
    emit('review.totals', { ...totals, skipped: ['visa'] }, 2)
    emit('review.report', { text: 'Budget review for 2026-09' }, 3)
    // The server refuses the expected charges until the review's status is completed.
    expect(api.getExpected).not.toHaveBeenCalled()
    emit('review.status', { status: 'completed' }, 4)

    const box = screen.getByRole('checkbox', { name: 'Include expected charges' })
    expect(box).toBeChecked()
    expect(await screen.findByRole('button', { name: 'Raw transactions (2)' }))
      .toHaveAttribute('aria-expanded', 'true')

    await user.click(box)
    expect(box).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Raw transactions (1)' })).toBeInTheDocument()
  })
})
