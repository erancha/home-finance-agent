/** Dimmed when the page shows charges the report does not narrate. */
export function Report({ text, outOfSync }: { text: string; outOfSync: boolean }) {
  return (
    <section className={outOfSync ? 'out-of-sync' : undefined}>
      <h2>Report</h2>
      <pre className="report" dir="auto">
        {text}
      </pre>
    </section>
  )
}
