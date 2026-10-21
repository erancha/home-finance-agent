import { useCallback, useEffect, useState } from 'react'
import { me, signOut as signOutRequest } from '../api/auth.ts'
import { ApiException, SIGNED_OUT_EVENT } from '../api/client.ts'
import type { User } from '../api/types.ts'

export type Session =
  | { state: 'loading' }
  | { state: 'signed-out' }
  | { state: 'signed-in'; user: User }
  | { state: 'failed'; message: string }

/**
 * Who is signed in, asked of the server once on mount and kept current afterwards: a sign-in
 * reports the person, a sign-out or any 401 from the API drops back to signed-out. A server that
 * cannot be asked at all is a failure, shown as such rather than as a sign-in screen.
 */
export function useSession() {
  const [session, setSession] = useState<Session>({ state: 'loading' })

  useEffect(() => {
    let current = true
    me().then(
      (user) => current && setSession({ state: 'signed-in', user }),
      (error: unknown) => {
        if (!current) return
        if (error instanceof ApiException && error.status === 401) {
          setSession({ state: 'signed-out' })
        } else {
          setSession({ state: 'failed', message: String(error) })
        }
      },
    )
    return () => {
      current = false
    }
  }, [])

  useEffect(() => {
    const onSignedOut = () => setSession({ state: 'signed-out' })
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut)
    return () => window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut)
  }, [])

  const signedIn = useCallback((user: User) => setSession({ state: 'signed-in', user }), [])
  const signOut = useCallback(async () => {
    await signOutRequest()
    setSession({ state: 'signed-out' })
  }, [])
  return { session, signedIn, signOut }
}
