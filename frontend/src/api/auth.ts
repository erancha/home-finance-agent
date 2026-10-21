import { apiDelete, apiGet, apiPost } from './client.ts'
import type { User } from './types.ts'

export function getAuthConfig(): Promise<{ clientId: string }> {
  return apiGet('/api/auth/config')
}

/** Who is signed in; a 401 means nobody. */
export function me(): Promise<User> {
  return apiGet('/api/auth/me')
}

/** Hands the server the ID token Google's button produced; the server answers with a cookie. */
export function signIn(credential: string): Promise<User> {
  return apiPost('/api/auth/session', { credential })
}

export function signOut(): Promise<void> {
  return apiDelete('/api/auth/session')
}
