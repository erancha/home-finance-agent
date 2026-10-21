import { useEffect, useRef, useState } from 'react'
import { getAuthConfig, signIn } from '../api/auth.ts'
import type { User } from '../api/types.ts'
import { loadGoogleIdentity } from './google.ts'

interface Props {
  onSignedIn: (user: User) => void
  /** The button's wording, as Google's options name it. */
  text?: 'signin_with' | 'continue_with'
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

/**
 * Google's own button, rendered into a slot once the client id and the Google script are in; the
 * credential it produces is posted to the server, which answers with the session cookie.
 */
export function GoogleSignIn({ onSignedIn, text = 'signin_with' }: Props) {
  const slot = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let current = true
    Promise.all([getAuthConfig(), loadGoogleIdentity()]).then(
      ([config, google]) => {
        if (!current || slot.current === null) return
        google.initialize({
          client_id: config.clientId,
          callback: ({ credential }) =>
            signIn(credential).then(
              (user) => current && onSignedIn(user),
              (e: unknown) => current && setError(errorText(e)),
            ),
        })
        google.renderButton(slot.current, { theme: 'outline', size: 'large', text })
      },
      (e: unknown) => current && setError(errorText(e)),
    )
    return () => {
      current = false
    }
  }, [onSignedIn, text])

  return (
    <div className="sign-in">
      <div ref={slot} />
      {error !== null && <p role="alert" className="error">{error}</p>}
    </div>
  )
}
