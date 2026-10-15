const WHOLE = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })

/** An amount as whole units with thousands separators; the server keeps the exact value. */
export function formatAmount(text: string): string {
  const value = Number(text)
  if (Number.isNaN(value)) throw new Error(`not an amount: ${text}`)
  return WHOLE.format(value)
}

const pad = (n: number) => String(n).padStart(2, '0')

/** An ISO time as local `YYYY/MM/DD HH:MM:SS`. */
export function formatTimestamp(iso: string): string {
  const t = new Date(iso)
  if (Number.isNaN(t.getTime())) throw new Error(`not a time: ${iso}`)
  const date = `${t.getFullYear()}/${pad(t.getMonth() + 1)}/${pad(t.getDate())}`
  return `${date} ${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`
}
