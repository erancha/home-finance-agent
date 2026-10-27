const WHOLE = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const WHOLE_SHEKELS = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'ILS',
  maximumFractionDigits: 0,
})

function amountOf(text: string): number {
  const value = Number(text)
  if (Number.isNaN(value)) throw new Error(`not an amount: ${text}`)
  return value
}

/** An amount as whole units with thousands separators; the server keeps the exact value. */
export function formatAmount(text: string): string {
  return WHOLE.format(amountOf(text))
}

/** An amount in the card currency, shekels, as whole units with the shekel sign. */
export function formatShekels(text: string): string {
  return WHOLE_SHEKELS.format(amountOf(text))
}

/** The sum of amounts as whole shekels; the float error of adding two-decimal amounts is far
 * below the rounding to whole units. */
export function formatShekelsSum(texts: string[]): string {
  return WHOLE_SHEKELS.format(texts.reduce((sum, text) => sum + amountOf(text), 0))
}

const pad = (n: number) => String(n).padStart(2, '0')

const dayMonthYear = (day: string, month: string, year: string) => `${day}/${month}/${year}`

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/

/** An ISO date as `DD/MM/YYYY`. The text is split, not parsed as a time, so the day never shifts
 * with the browser's time zone. */
export function formatDate(iso: string): string {
  const match = ISO_DATE.exec(iso)
  if (match === null) throw new Error(`not a date: ${iso}`)
  const [, year, month, day] = match
  return dayMonthYear(day, month, year)
}

/** An ISO time as local `DD/MM/YYYY HH:MM:SS`. */
export function formatTimestamp(iso: string): string {
  const t = new Date(iso)
  if (Number.isNaN(t.getTime())) throw new Error(`not a time: ${iso}`)
  const date = dayMonthYear(pad(t.getDate()), pad(t.getMonth() + 1), String(t.getFullYear()))
  return `${date} ${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`
}
