import { GoogleSignIn } from './auth/GoogleSignIn.tsx'
import { SessionHeader } from './auth/SessionHeader.tsx'
import { useSession } from './auth/useSession.ts'
import { ReviewPage } from './features/review/ReviewPage.tsx'

/** The review page is reached only signed in; the month stays in the URL across a sign-in. */
export function App() {
  const { session, signedIn, signOut } = useSession()
  switch (session.state) {
    case 'loading':
      return (
        <main>
          <p className="muted">Checking who is signed in…</p>
        </main>
      )
    case 'failed':
      return (
        <main>
          <p role="alert" className="error">The server could not be reached: {session.message}</p>
        </main>
      )
    case 'signed-out':
      return (
        <main>
          <h1>Monthly card review</h1>
          <p>Sign in with your Google account to review your card months.</p>
          <GoogleSignIn onSignedIn={signedIn} />
        </main>
      )
    case 'signed-in':
      return (
        <>
          <SessionHeader user={session.user} onSignOut={() => void signOut()} />
          <ReviewPage />
        </>
      )
  }
}
