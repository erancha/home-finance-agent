import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ReviewEvent, TotalsData, Transaction } from '../../api/types.ts'
import { TransactionsSection } from './TransactionsSection.tsx'

const row: Transaction = {
  id: 't1', agent: 'amex', transactionDate: '2026-09-02', chargeDate: '2026-10-02',
  merchant: 'שופרסל', rawMerchant: 'SHUFERSAL 12', merchantKey: 'shufersal', amount: '1120.50',
  originalAmount: null, originalCurrency: null, standingOrder: false, abroad: false,
  installment: null, category: 'uncategorized', confidence: 'medium',
}
const sameMerchant: Transaction = { ...row, id: 't2', rawMerchant: 'SHUFERSAL 7' }
const batch = (...transactions: Transaction[]): ReviewEvent => ({
  type: 'transactions.batch',
  data: {
    agent: 'amex', month: '2026-09', count: transactions.length, transactions,
    at: '2026-10-14T09:00:00+00:00',
  },
})
const totals: TotalsData = {
  currency: 'ILS', totals: [], skipped: [],
  categories: { amex: { t1: 'dining', t2: 'dining' } },
  chosen: {},
  options: ['groceries', 'dining'],
  standingOrders: '0.00',
}

describe('TransactionsSection', () => {
  it('starts folded, counting each row once even when a batch repeats it', () => {
    render(
      <TransactionsSection
        events={[batch(row), batch(row, sameMerchant)]}
        expected={[]}
        totals={null}
        onRecategorize={null}
        category={null}
        standingOrders={false}
        onStandingOrders={vi.fn()}
        inProgress
        picks={0}
      />,
    )
    const toggle = screen.getByRole('button', { name: 'Raw transactions (2)' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('table')).toBeNull()

    fireEvent.click(toggle)

    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(3)
    expect(screen.getAllByText('uncategorized')).toHaveLength(2)
    expect(screen.getAllByText('1,121')).toHaveLength(2)
  })

  it("shows each row's details and confidence, with the statement text as a tooltip", () => {
    const installment: Transaction = {
      ...row, installment: { number: 3, total: 10 }, confidence: 'low',
    }
    render(
      <TransactionsSection
        events={[batch(installment)]}
        expected={[]}
        totals={null}
        onRecategorize={null}
        category={null}
        standingOrders={false}
        onStandingOrders={vi.fn()}
        inProgress
        picks={0}
      />,
    )
    const cells = within(screen.getAllByRole('row')[1]).getAllByRole('cell')
    expect(cells.map((c) => c.textContent)).toEqual([
      '2026-09-02', 'amex', 'שופרסל', '1,121', '3 of 10', 'uncategorized', 'low',
    ])
    expect(cells[2]).toHaveAttribute('title', 'SHUFERSAL 12')
    expect(cells[6]).toHaveClass('confidence-low')
  })

  it('shows the category the totals counted, read-only while the review is not completed', () => {
    render(<TransactionsSection
        events={[batch(row)]}
        expected={[]}
        totals={totals}
        onRecategorize={null}
        category={null}
        standingOrders={false}
        onStandingOrders={vi.fn()}
        inProgress
        picks={0}
      />)
    fireEvent.click(screen.getByRole('button', { name: 'Raw transactions (1)' }))
    expect(screen.getByText('dining')).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('applies a category to every row of the merchant and sends it once', async () => {
    const user = userEvent.setup()
    const onRecategorize = vi.fn().mockResolvedValue(true)
    render(
      <TransactionsSection
        events={[batch(row, sameMerchant)]}
        expected={[]}
        totals={totals}
        onRecategorize={onRecategorize}
        category={null}
        standingOrders={false}
        onStandingOrders={vi.fn()}
        inProgress
        picks={0}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Raw transactions (2)' }))
    const apply = screen.getByRole('button', { name: 'Apply categories' })
    expect(apply).toBeDisabled()

    const [first, second] = screen.getAllByRole('combobox')
    await user.selectOptions(first, 'groceries')
    expect(second).toHaveValue('groceries')
    await user.click(screen.getByRole('button', { name: 'Apply categories (1 merchant)' }))

    expect(onRecategorize).toHaveBeenCalledExactlyOnceWith({ shufersal: 'groceries' })
    expect(screen.getByRole('button', { name: 'Apply categories' })).toBeDisabled()
  })

  it('moves focus to the apply button and sweeps its edge on every category change', async () => {
    const user = userEvent.setup()
    render(
      <TransactionsSection
        events={[batch(row, { ...row, id: 't2', merchantKey: 'gett', merchant: 'Gett' })]}
        expected={[]}
        totals={totals}
        onRecategorize={vi.fn().mockResolvedValue(true)}
        category={null}
        standingOrders={false}
        onStandingOrders={vi.fn()}
        inProgress
        picks={0}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Raw transactions (2)' }))
    const idle = screen.getByRole('button', { name: 'Apply categories' })
    expect(idle).not.toHaveClass('border-sweep')
    expect(idle).not.toHaveFocus()

    const [first, second] = screen.getAllByRole('combobox')
    await user.selectOptions(first, 'groceries')
    const once = screen.getByRole('button', { name: 'Apply categories (1 merchant)' })
    expect(once).toHaveClass('border-sweep')
    expect(once).toHaveFocus()

    await user.selectOptions(second, 'groceries')
    const twice = screen.getByRole('button', { name: 'Apply categories (2 merchants)' })
    expect(twice).not.toBe(once)
    expect(twice).toHaveClass('border-sweep')
    expect(twice).toHaveFocus()
  })

  it('keeps the choices when the server refuses them', async () => {
    const user = userEvent.setup()
    const onRecategorize = vi.fn().mockResolvedValue(false)
    render(
      <TransactionsSection
        events={[batch(row)]}
        expected={[]}
        totals={totals}
        onRecategorize={onRecategorize}
        category={null}
        standingOrders={false}
        onStandingOrders={vi.fn()}
        inProgress
        picks={0}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Raw transactions (1)' }))
    await user.selectOptions(screen.getByRole('combobox'), 'groceries')
    await user.click(screen.getByRole('button', { name: 'Apply categories (1 merchant)' }))

    expect(screen.getByRole('combobox')).toHaveValue('groceries')
    expect(screen.getByRole('button', { name: 'Apply categories (1 merchant)' })).toBeEnabled()
  })

  it('opens on a chosen category and lists only the rows the totals counted under it', () => {
    const other: Transaction = { ...row, id: 't3', merchantKey: 'gett', merchant: 'Gett' }
    const counted: TotalsData = {
      ...totals, categories: { amex: { t1: 'dining', t2: 'dining', t3: 'transport' } },
    }
    render(
      <TransactionsSection
        events={[batch(row, sameMerchant, other)]}
        expected={[]}
        totals={counted}
        onRecategorize={null}
        category="transport"
        standingOrders={false}
        onStandingOrders={vi.fn()}
        inProgress
        picks={1}
      />,
    )
    const toggle = screen.getByRole('button', { name: 'Raw transactions: transport (1 of 3)' })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(2)
    expect(screen.getByText('Gett')).toBeInTheDocument()
  })

  it('lists only the standing orders when asked, and reports the box being toggled', () => {
    const gym: Transaction = { ...row, id: 't3', merchant: 'וים קלאבס', standingOrder: true }
    const onStandingOrders = vi.fn()
    render(
      <TransactionsSection
        events={[batch(row, gym)]}
        expected={[]}
        totals={null}
        onRecategorize={null}
        category={null}
        standingOrders
        onStandingOrders={onStandingOrders}
        inProgress
        picks={1}
      />,
    )
    expect(screen.getByRole('button', { name: 'Raw transactions: standing orders (1 of 2)' }))
      .toBeInTheDocument()
    expect(screen.getByText('וים קלאבס')).toBeInTheDocument()
    expect(screen.queryByText('שופרסל')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: 'Standing orders only' }))
    expect(onStandingOrders).toHaveBeenCalledExactlyOnceWith(false)
  })

  it('unfolds once when a low-confidence row arrives while the review is in progress', () => {
    const props = {
      expected: [], totals: null, onRecategorize: null, category: null, standingOrders: false,
      onStandingOrders: vi.fn(), inProgress: true, picks: 0,
    }
    const { rerender } = render(<TransactionsSection events={[batch(row)]} {...props} />)
    expect(screen.getByRole('button', { name: 'Raw transactions (1)' }))
      .toHaveAttribute('aria-expanded', 'false')

    const unsure: Transaction = { ...sameMerchant, confidence: 'low' }
    rerender(<TransactionsSection events={[batch(row), batch(unsure)]} {...props} />)
    const toggle = screen.getByRole('button', { name: 'Raw transactions (2)' })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    fireEvent.click(toggle)
    rerender(
      <TransactionsSection
        events={[batch(row), batch(unsure)]}
        {...props}
        inProgress={false}
      />,
    )
    expect(screen.getByRole('button', { name: 'Raw transactions (2)' }))
      .toHaveAttribute('aria-expanded', 'false')
  })

  it('stays folded for low-confidence rows of a review that already ended', () => {
    render(
      <TransactionsSection
        events={[batch({ ...row, confidence: 'low' })]}
        expected={[]}
        totals={null}
        onRecategorize={null}
        category={null}
        standingOrders={false}
        onStandingOrders={vi.fn()}
        inProgress={false}
        picks={0}
      />,
    )
    expect(screen.getByRole('button', { name: 'Raw transactions (1)' }))
      .toHaveAttribute('aria-expanded', 'false')
  })

  it('marks the confidence of a row the person overruled, without the low highlight', () => {
    const unsure: Transaction = { ...row, confidence: 'low' }
    render(
      <TransactionsSection
        events={[batch(unsure)]}
        expected={[]}
        totals={{ ...totals, chosen: { amex: ['t1'] } }}
        onRecategorize={null}
        category={null}
        standingOrders={false}
        onStandingOrders={vi.fn()}
        inProgress={false}
        picks={1}
      />,
    )
    const cell = screen.getByRole('cell', { name: 'low (overruled)' })
    expect(cell).not.toHaveClass('confidence-low')
  })

  it('lists the expected rows of a review whose only card agent was skipped', () => {
    const gym: Transaction = { ...row, id: 'expected-g1', merchant: 'וים קלאבס', standingOrder: true }
    render(
      <TransactionsSection
        events={[]}
        expected={[gym]}
        totals={totals}
        onRecategorize={vi.fn()}
        category={null}
        standingOrders={false}
        onStandingOrders={vi.fn()}
        inProgress={false}
        picks={0}
      />,
    )
    expect(screen.getByRole('button', { name: 'Raw transactions (1)' }))
      .toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('וים קלאבס').closest('tr')).toHaveClass('expected')
  })

  it('renders nothing before any row arrives', () => {
    const { container } = render(
      <TransactionsSection
        events={[]}
        expected={[]}
        totals={null}
        onRecategorize={null}
        category={null}
        standingOrders={false}
        onStandingOrders={vi.fn()}
        inProgress
        picks={0}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
