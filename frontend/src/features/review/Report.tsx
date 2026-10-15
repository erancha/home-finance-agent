export function Report({ text }: { text: string }) {
  return (
    <section>
      <h2>Report</h2>
      <pre className="report" dir="auto">
        {text}
      </pre>
    </section>
  )
}
