import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import type { CategoryTotal } from '../../api/types.ts'
import { formatShekels, formatShekelsSum } from '../../format.ts'
import { CATEGORY_MEANINGS } from './categoryMeanings.ts'

interface Props {
  totals: CategoryTotal[]
  standingOrders: string
  /** The totals count the charges a mid-month review still expects. */
  withExpected: boolean
  skipped: string[]
  /** The category whose transactions are shown; null shows all. */
  selected: string | null
  onSelect: (category: string | null) => void
  onSelectStandingOrders: () => void
}

// Slots of the categorical palette in global.css (--series-1 ...). Slices past the last slot share
// the --series-rest gray rather than reusing a hue, so no two colored slices look alike.
const PALETTE_SLOTS = 7

interface Slice {
  total: CategoryTotal
  spent: number
  share: number
  color: string
}

// A pie can only show positive spend: a category with nothing spent, or with refunds outweighing
// its charges, stays in the legend without a slice. Largest slices take the palette's first slots.
function slicesOf(totals: CategoryTotal[]): Slice[] {
  const positive = totals.filter((total) => Number(total.spent) > 0)
  const sum = positive.reduce((acc, total) => acc + Number(total.spent), 0)
  return positive
    .map((total) => ({ total, spent: Number(total.spent) }))
    .sort((a, b) => b.spent - a.spent)
    .map((slice, index) => ({
      ...slice,
      share: slice.spent / sum,
      color: index < PALETTE_SLOTS ? `var(--series-${index + 1})` : 'var(--series-rest)',
    }))
}

function amountLabel(total: CategoryTotal): string {
  const spent = formatShekels(total.spent)
  return total.limit === null ? spent : `${spent} / ${formatShekels(total.limit)}`
}

function shareLabel(share: number): string {
  return `${(share * 100).toFixed(1)}%`
}

function sliceSummary(slice: Slice): string {
  return `${slice.total.category} ${amountLabel(slice.total)} (${shareLabel(slice.share)})`
}

function SliceTooltip({ active, payload }: { active?: boolean; payload?: { payload: Slice }[] }) {
  if (!active || !payload?.length) return null
  return <div className="chart-tooltip">{sliceSummary(payload[0].payload)}</div>
}

export function TotalsChart({
  totals,
  standingOrders,
  withExpected,
  skipped,
  selected,
  onSelect,
  onSelectStandingOrders,
}: Props) {
  const slices = slicesOf(totals)
  const sliceByCategory = new Map(slices.map((slice) => [slice.total.category, slice]))
  // The legend follows the slices from largest down, then lists the categories without one.
  const legend = [
    ...slices.map((slice) => slice.total),
    ...totals.filter((total) => !sliceByCategory.has(total.category)),
  ]
  return (
    <section>
      <h2>
        <button
          type="button"
          className="heading-button"
          aria-pressed={selected === null}
          onClick={() => onSelect(null)}
        >
          Totals
        </button>
      </h2>
      <p className="muted">
        {selected === null
          ? 'Choose a category to see only its transactions.'
          : `Showing the transactions of ${selected}; choose Totals to show all.`}
      </p>
      {skipped.length > 0 && (
        <p className="notice">Skipped: {skipped.join(', ')}. Their spend is missing from the totals.</p>
      )}
      <div className="totals">
        {slices.length === 0 ? (
          <p className="muted">Nothing spent.</p>
        ) : (
          <div
            className="totals-pie"
            role="img"
            aria-label={`Spending by category: ${slices.map(sliceSummary).join(', ')}`}
          >
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={slices}
                  dataKey="spent"
                  nameKey={(slice: Slice) => slice.total.category}
                  innerRadius={0}
                  outerRadius="90%"
                  stroke="var(--bg)"
                  strokeWidth={2}
                  isAnimationActive={false}
                  cursor="pointer"
                  onClick={(_, index) => onSelect(slices[index].total.category)}
                >
                  {slices.map((slice) => (
                    <Cell
                      key={slice.total.category}
                      fill={slice.color}
                      fillOpacity={selected === null || selected === slice.total.category ? 1 : 0.35}
                    />
                  ))}
                </Pie>
                <Tooltip content={<SliceTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
        <table className="totals-legend">
          <thead>
            <tr>
              <th>Category</th>
              <th className="num">Spent / limit</th>
              <th className="num">Share</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {legend.map((total) => {
              const slice = sliceByCategory.get(total.category)
              return (
                <tr key={total.category} className={total.over ? 'over' : undefined}>
                  <td>
                    <span className="chip" style={slice && { background: slice.color }} />{' '}
                    <button
                      type="button"
                      className="legend-button"
                      aria-pressed={selected === total.category}
                      title={CATEGORY_MEANINGS[total.category]}
                      onClick={() => onSelect(total.category)}
                    >
                      {total.category}
                    </button>
                  </td>
                  <td className="num">{amountLabel(total)}</td>
                  <td className="num muted">{slice && shareLabel(slice.share)}</td>
                  <td>
                    {total.over && 'over budget'}
                    {total.limit === null && <span className="muted">no limit</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr className="summary">
              <th scope="row">{withExpected ? 'Total, with expected charges' : 'Total'}</th>
              <td className="num">{formatShekelsSum(totals.map((t) => t.spent))}</td>
              <td></td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p>
        <button type="button" className="legend-button" onClick={onSelectStandingOrders}>
          Standing orders
        </button>{' '}
        <strong className="summary">{formatShekels(standingOrders)}</strong>{' '}
        <span className="muted">across categories</span>
      </p>
    </section>
  )
}
