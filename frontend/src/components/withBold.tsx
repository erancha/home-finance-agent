import { Fragment, type ReactNode } from 'react'

/** A span wrapped in double asterisks, as Markdown marks bold. */
const BOLD = /\*\*(.+?)\*\*/gs

/** A line of fixed page text with its **marked** spans in bold; nothing else is read. */
export function withBold(text: string): ReactNode[] {
  // split puts each captured span at an odd index, between the plain runs around it.
  return text
    .split(BOLD)
    .map((part, index) =>
      index % 2 === 0 ? <Fragment key={index}>{part}</Fragment> : <strong key={index}>{part}</strong>,
    )
}
