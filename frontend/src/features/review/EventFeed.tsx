import type { ReviewEvent } from '../../api/types.ts'
import { formatTimestamp } from '../../format.ts'

function describe(event: ReviewEvent): string {
  switch (event.type) {
    case 'agent.discovered':
      return `Agent ${event.data.agent} discovered`
    case 'agent.status':
      return event.data.text === null
        ? `${event.data.agent}: ${event.data.state}`
        : `${event.data.agent}: ${event.data.state} — ${event.data.text}`
    case 'transactions.batch':
      return `${event.data.count} transactions from ${event.data.agent}`
    case 'review.question':
      return `Question posed (${event.data.questions.length})`
    case 'review.totals':
      return 'Totals updated'
    case 'review.writing':
      return 'Writing the summary'
    case 'review.report':
      return 'Report ready'
    case 'review.failed':
      return 'Review failed'
  }
}

/** working: the review is busy on the server, so the last event's line ends with a spinner. */
export function EventFeed({ events, working }: { events: ReviewEvent[]; working: boolean }) {
  const spinner = <span className="spinner" role="status" aria-label="Working" />
  return (
    <section>
      <h2>Progress</h2>
      <ul className="feed">
        {events.map((event, index) => (
          <li key={index}>
            <time className="feed-time" dateTime={event.data.at}>
              {formatTimestamp(event.data.at)}
            </time>{' '}
            {describe(event)}
            {working && index === events.length - 1 && <> {spinner}</>}
          </li>
        ))}
        {working && events.length === 0 && <li className="feed-bare">{spinner}</li>}
      </ul>
    </section>
  )
}
