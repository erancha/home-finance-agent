import { useLayoutEffect, useRef, useState } from 'react'
import type { User } from '../api/types.ts'
import { useGoogleButton } from './GoogleSignIn.tsx'
import { SignInReasons } from './SignInReasons.tsx'

/**
 * The landing page's sign-in area: the shared sign-in button, as every landing page draws it,
 * with Google's own button laid over it, transparent and stretched to the shared button's box,
 * so the click reaches Google's button and the sign-in stays Google's. Under the button it shows
 * why a sign-in failed, then the toggle that explains signing in with Google; while the
 * explanation is open, the whole area is framed as one panel.
 */
export function SignInButton({ onSignedIn }: { onSignedIn: (user: User) => void }) {
  const [explained, setExplained] = useState(false)
  const shared = useRef<HTMLButtonElement>(null)
  const overlay = useRef<HTMLDivElement>(null)
  const slot = useRef<HTMLDivElement>(null)
  const error = useGoogleButton(slot, onSignedIn)

  useLayoutEffect(() => {
    const button = shared.current!
    const cover = overlay.current!
    const google = slot.current!
    // Google draws its button at its own size, so the overlay takes the shared button's box and
    // scales Google's button to fill it; a transform leaves layout alone, so the fit cannot loop.
    const fit = () => {
      cover.style.top = `${button.offsetTop}px`
      cover.style.left = `${button.offsetLeft}px`
      cover.style.width = `${button.offsetWidth}px`
      cover.style.height = `${button.offsetHeight}px`
      // The slot stays empty, with no size to scale, until Google's script has drawn into it.
      if (google.offsetWidth > 0 && google.offsetHeight > 0) {
        const x = button.offsetWidth / google.offsetWidth
        const y = button.offsetHeight / google.offsetHeight
        google.style.transform = `scale(${x}, ${y})`
      }
    }
    const observer = new ResizeObserver(fit)
    observer.observe(button)
    observer.observe(google)
    return () => observer.disconnect()
  }, [])

  return (
    <div className={explained ? 'sign-in sign-in-open' : 'sign-in'}>
      {/* Only drawn: Google's button over it is the control that screen readers and the keyboard
          reach, under the same name. */}
      <button
        ref={shared}
        type="button"
        className="sign-in-button"
        aria-hidden="true"
        tabIndex={-1}
      >
        <span className="sign-in-mark" aria-hidden="true">G</span>
        Sign in with Google
      </button>
      <div ref={overlay} className="sign-in-google">
        <div ref={slot} />
      </div>
      {error !== null && <p role="alert" className="error">{error}</p>}
      <SignInReasons open={explained} onOpenChange={setExplained} />
    </div>
  )
}
