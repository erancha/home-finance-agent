import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import { TotalsChart } from './TotalsChart.tsx'

const totals = [
  { category: 'dining', spent: '100.00', limit: '500.00', over: false },
  { category: 'groceries', spent: '1200.00', limit: '1000.00', over: true },
  { category: 'misc', spent: '30.00', limit: null, over: false },
  { category: 'travel', spent: '0.00', limit: '800.00', over: false },
]

function chart(overrides: Partial<ComponentProps<typeof TotalsChart>> = {}) {
  return render(
    <TotalsChart
      totals={totals}
      standingOrders="0.00"
      skipped={[]}
      selected={null}
      onSelect={vi.fn()}
      onSelectStandingOrders={vi.fn()}
      {...overrides}
    />,
  )
}

function legendRow(category: string): HTMLElement {
  return screen.getByText(category, { selector: '.totals-legend button' }).closest('li')!
}

describe('TotalsChart', () => {
  it('draws one slice per category with spend and summarizes them for assistive technology', () => {
    const { container } = chart()
    expect(container.querySelectorAll('.recharts-pie-sector')).toHaveLength(3)
    expect(screen.getByRole('img')).toHaveAccessibleName(
      'Spending by category: groceries 1,200 / 1,000 (90.2%), '
        + 'dining 100 / 500 (7.5%), misc 30 (2.3%)',
    )
  })

  it('lists every category largest first, marking overruns, missing limits and slice-less rows', () => {
    const { container } = chart()
    const rows = [...container.querySelectorAll('.totals-legend li')]
    expect(rows.map((row) => row.children[1].textContent))
      .toEqual(['groceries', 'dining', 'misc', 'travel'])
    expect(legendRow('groceries')).toHaveClass('over')
    expect(legendRow('groceries')).toHaveTextContent('1,200 / 1,000')
    expect(legendRow('groceries')).toHaveTextContent('over budget')
    expect(legendRow('dining')).not.toHaveClass('over')
    expect(legendRow('misc')).toHaveTextContent('no limit')
    expect(legendRow('travel')).not.toHaveTextContent('%')
    expect(screen.queryByText(/skipped/i)).not.toBeInTheDocument()
  })

  it('shows the hovered slice with its amount and share', async () => {
    const { container } = chart()
    await userEvent.hover(container.querySelector('.recharts-pie-sector')!)
    expect(await screen.findByText('groceries 1,200 / 1,000 (90.2%)', { selector: '.chart-tooltip' }))
      .toBeInTheDocument()
  })

  it('draws no pie when nothing was spent', () => {
    chart({ totals: [totals[3]], skipped: ['amex'] })
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByText('Nothing spent.')).toBeInTheDocument()
    expect(legendRow('travel')).toHaveTextContent('0 / 800')
  })

  it('lists skipped agents', () => {
    chart({ skipped: ['amex', 'isracard'] })
    expect(screen.getByText(/skipped: amex, isracard/i)).toBeInTheDocument()
  })

  it('selects a category from its slice or legend entry, and all from the Totals heading', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    const { container } = chart({ selected: 'dining', onSelect })
    expect(screen.getByRole('button', { name: 'dining' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/showing the transactions of dining/i)).toBeInTheDocument()

    await user.click(container.querySelector('.recharts-pie-sector path')!)
    await user.click(screen.getByRole('button', { name: 'misc' }))
    await user.click(screen.getByRole('button', { name: 'Totals' }))
    expect(onSelect.mock.calls).toEqual([['groceries'], ['misc'], [null]])
  })

  it('shows the standing-order spend and selects its transactions', async () => {
    const onSelectStandingOrders = vi.fn()
    chart({ standingOrders: '1308.00', onSelectStandingOrders })
    expect(screen.getByText('Standing orders').closest('p')).toHaveTextContent(
      'Standing orders 1,308 across categories',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Standing orders' }))
    expect(onSelectStandingOrders).toHaveBeenCalledOnce()
  })
})
