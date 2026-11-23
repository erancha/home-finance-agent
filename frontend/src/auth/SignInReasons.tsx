import { useEffect, useRef } from 'react'
import { withBold } from '../components/withBold.tsx'

// Google's help page "How Sign in with Google helps you share data safely". It carries no
// language parameter, so Google answers in the visitor's own language.
const GOOGLE_HELP_URL = 'https://support.google.com/accounts/answer/12921417'
const LINK = "Google's full explanation"
const LEAD =
  'Signing in with Google is **safer and easier** than opening an account with a new password.'

/**
 * The reasons; **marked** words show in bold. The first two answer the fear of handing the agent
 * access to a Google account, since a worried reader discounts advantages until then; the last
 * two argue the advantages.
 */
const POINTS = [
  `**Google approves the sign-in.** Google gives the app only a` +
    ' confirmation of who you are, with no access to your data (emails, contacts and more).',
  `**You stay in control:** you can disconnect the app at any time in your Google account's` +
    ' settings.',
  '**No new password to remember,** and none that could leak from here: the app stores no' +
    ' passwords at all.',
  "**Google's protections work for you:** two-step verification and alerts on a suspicious" +
    ' sign-in guard your sign-in here too.',
]

/**
 * The toggle under the landing page's sign-in button and the text it opens in place: why signing
 * in with Google is safe for a visitor who does not know this site, ending with a link to
 * Google's own account of it. The sign-in button owns whether it is open, since it frames itself
 * while it is. A close button at the end of the toggle's line closes it too, and the link marks
 * that it opens a new tab, so it is not taken for the way out.
 */
export function SignInReasons({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const toggle = useRef<HTMLButtonElement>(null)
  const text = useRef<HTMLDivElement>(null)
  // Opening scrolls down to the explanation's last line, which on a phone opens below the fold.
  useEffect(() => {
    if (open) text.current!.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [open])
  return (
    <>
      <div className="sign-in-why-row">
        <button
          ref={toggle}
          type="button"
          className="sign-in-why"
          aria-expanded={open}
          onClick={() => onOpenChange(!open)}
        >
          Why sign in with Google?
        </button>
        {open && (
          <button
            type="button"
            className="sign-in-why-close"
            aria-label="Close the explanation"
            onClick={() => {
              onOpenChange(false)
              // The close button leaves with the text, so focus returns to what reopens it.
              toggle.current?.focus()
            }}
          >
            ✕
          </button>
        )}
      </div>
      {open && (
        <div ref={text} className="sign-in-why-text">
          <p>{withBold(LEAD)}</p>
          <ul className="landing-details">
            {POINTS.map((point) => (
              <li key={point}>{withBold(point)}</li>
            ))}
          </ul>
          <a
            href={GOOGLE_HELP_URL}
            target="_blank"
            rel="noreferrer"
            aria-label={`${LINK} (opens in a new tab)`}
          >
            {LINK} <span aria-hidden="true">↗</span>
          </a>
        </div>
      )}
    </>
  )
}
