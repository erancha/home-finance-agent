import { useState } from 'react'
import type { User } from '../../api/types.ts'
import { SignInButton } from '../../auth/SignInButton.tsx'
import { withBold } from '../../components/withBold.tsx'
import {
  APP_TAGLINE,
  APP_TITLE,
  INVITE_LINK,
  INVITE_MARK,
  LANDING_DETAILS,
  LANDING_LEAD,
  LANDING_STEPS,
  LESS,
  MORE,
  SOURCE_LINK,
} from './copy.ts'
import { whatsAppInviteUrl } from './invite.ts'

const SOURCE_URL = 'https://github.com/erancha/home-finance-agent'

/**
 * The signed-out page: one card in the middle of the page, under the tab's icon, the product name
 * and the tagline, that pitches the agent over the sign-in button, with a toggle that adds the
 * details. Links under the card invite a friend or open the source. Its markup is
 * loan-simulator's, which the shared landing.css styles.
 */
export function Landing({ onSignedIn }: { onSignedIn: (user: User) => void }) {
  const [expanded, setExpanded] = useState(false)
  // Opening the sign-in explanation folds the details back, so one subject is open at a time.
  const foldOnExplain = (event: { target: EventTarget }) => {
    const toggle = (event.target as Element).closest('.sign-in-why')
    if (toggle?.getAttribute('aria-expanded') === 'false') setExpanded(false)
  }
  return (
    <main className="landing">
      <div className="landing-card" onClick={foldOnExplain}>
        <h1 className="app-heading">
          {/* The same file as the tab's icon, so the two cannot drift apart; decorative. */}
          <img className="app-icon" src="/favicon.svg" alt="" /> {APP_TITLE}
        </h1>
        {/* A sibling of the heading, so the heading's accessible name stays the bare title. */}
        <p className="app-tagline landing-flash">{APP_TAGLINE}</p>
        {LANDING_LEAD.map((line) => (
          <p key={line} className="landing-pitch">
            {withBold(line)}
          </p>
        ))}
        <ol className="landing-steps">
          {LANDING_STEPS.map((step) => (
            <li key={step.title}>
              <span>
                <strong>{step.title}</strong>: {step.text}
              </span>
            </li>
          ))}
        </ol>
        {expanded && (
          <ul className="landing-details">
            {LANDING_DETAILS.map((detail) => (
              <li key={detail}>{withBold(detail)}</li>
            ))}
          </ul>
        )}
        <button
          type="button"
          className="landing-more landing-flash"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? LESS : MORE}
        </button>
        <SignInButton onSignedIn={onSignedIn} />
      </div>
      <footer className="landing-links">
        <a href={whatsAppInviteUrl()} target="_blank" rel="noreferrer">
          <span className="link-mark" aria-hidden="true">
            {INVITE_MARK}
          </span>
          {INVITE_LINK}
        </a>
        <a href={SOURCE_URL} target="_blank" rel="noreferrer">
          {SOURCE_LINK}
        </a>
      </footer>
    </main>
  )
}
