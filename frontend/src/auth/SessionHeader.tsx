import type { User } from '../api/types.ts'

interface Props {
  user: User
  onSignOut: () => void
}

/** Google sends email and name only for the scopes the button asks; the id is always there. */
export function displayName(user: User): string {
  return user.email ?? user.name ?? user.id
}

export function SessionHeader({ user, onSignOut }: Props) {
  return (
    <header className="session-bar">
      <span>Signed in as {displayName(user)}</span>
      <button type="button" onClick={onSignOut}>
        Sign out
      </button>
    </header>
  )
}
