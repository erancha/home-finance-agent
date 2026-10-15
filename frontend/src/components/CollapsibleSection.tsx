import { useState, type ReactNode } from 'react'

interface Props {
  title: ReactNode
  /** The section opens folded when true; the reader unfolds it from the heading. */
  defaultCollapsed?: boolean
  children: ReactNode
}

/** A section whose heading is a toggle that shows or hides its body. */
export function CollapsibleSection({ title, defaultCollapsed = false, children }: Props) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)
  return (
    <section>
      <h2>
        <button
          type="button"
          className="disclosure"
          aria-expanded={!collapsed}
          onClick={() => setCollapsed((c) => !c)}
        >
          {title}
        </button>
      </h2>
      {!collapsed && children}
    </section>
  )
}
