import type { ReactNode } from 'react'
import type { ReviewEvent } from '../../api/types.ts'
import { CollapsibleSection } from '../../components/CollapsibleSection.tsx'
import { formatTimestamp } from '../../format.ts'

const INPUT_REQUIRED = 'TASK_STATE_INPUT_REQUIRED'

/** An agent's request for input is shown here alone; the question below offers only the action. */
function statusText(state: string, text: string): ReactNode {
  return state === INPUT_REQUIRED ? <span className="error">{text}</span> : text
}

function describe(event: ReviewEvent): ReactNode {
  switch (event.type) {
    case 'agent.discovered':
      return `Agent ${event.data.agent} discovered`
    case 'agent.status':
      return event.data.text === null ? (
        `${event.data.agent}: ${event.data.state}`
      ) : (
        <>
          {event.data.agent}: {event.data.state} — {statusText(event.data.state, event.data.text)}
        </>
      )
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

interface Props {
  events: ReviewEvent[]
  /** The review is busy on the server, so the last event's line ends with a spinner. */
  working: boolean
  /** The review has not ended, so the feed stays unfolded; it folds once the review ended. */
  inProgress: boolean
}

export function EventFeed({ events, working, inProgress }: Props) {
  const spinner = <span className="spinner" role="status" aria-label="Working" />
  return (
    <CollapsibleSection key={String(inProgress)} title="Progress" defaultCollapsed={!inProgress}>
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
    </CollapsibleSection>
  )
}
