import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as auth from './api/auth.ts'
import { ApiException, SIGNED_OUT_EVENT } from './api/client.ts'
import type { User } from './api/types.ts'
import { App } from './App.tsx'
import { FakeGoogleIdentity } from './test/fakeGoogle.ts'

vi.mock('./api/auth.ts')
vi.mock('./features/review/ReviewPage.tsx', () => ({
  ReviewPage: () => <p>the review page</p>,
}))

const dana: User = { id: '1001', email: 'dana@example.com', name: 'Dana' }
const notSignedIn = new ApiException(401, 'sign in to continue')

beforeEach(() => {
  vi.mocked(auth.getAuthConfig).mockResolvedValue({ clientId: 'hfm-test-client' })
  vi.mocked(auth.signIn).mockResolvedValue(dana)
  vi.mocked(auth.signOut).mockResolvedValue(undefined)
  window.history.replaceState(null, '', '/?month=2026-09')
})
afterEach(() => {
  vi.resetAllMocks()
  window.history.replaceState(null, '', '/')
})

describe('App', () => {
  it('shows the review page to a person the server knows', async () => {
    vi.mocked(auth.me).mockResolvedValue(dana)
    render(<App />)
    expect(await screen.findByText('the review page')).toBeInTheDocument()
    expect(screen.getByText('Signed in as dana@example.com')).toBeInTheDocument()
  })

  it("offers Google's button to a stranger and signs them in with its credential", async () => {
    vi.mocked(auth.me).mockRejectedValue(notSignedIn)
    const user = userEvent.setup()
    render(<App />)

    const button = await screen.findByRole('button', { name: 'Sign in with Google' })
    expect(screen.queryByText('the review page')).not.toBeInTheDocument()
    expect((window.google?.accounts.id as FakeGoogleIdentity).clientIds).toEqual(['hfm-test-client'])

    await user.click(button)
    expect(auth.signIn).toHaveBeenCalledExactlyOnceWith(FakeGoogleIdentity.credential)
    expect(await screen.findByText('the review page')).toBeInTheDocument()
    expect(window.location.search).toBe('?month=2026-09')
  })

  it('shows why a sign-in was refused', async () => {
    vi.mocked(auth.me).mockRejectedValue(notSignedIn)
    vi.mocked(auth.signIn).mockRejectedValue(new ApiException(401, 'the sign-in has expired'))
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: 'Sign in with Google' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('the sign-in has expired')
  })

  it('signs out on request and drops to the button', async () => {
    vi.mocked(auth.me).mockResolvedValue(dana)
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: 'Sign out' }))
    expect(auth.signOut).toHaveBeenCalledOnce()
    expect(await screen.findByRole('button', { name: 'Sign in with Google' })).toBeInTheDocument()
  })

  it('drops to the button when any request answers 401, keeping the month in the URL', async () => {
    vi.mocked(auth.me).mockResolvedValue(dana)
    render(<App />)
    await screen.findByText('the review page')

    act(() => window.dispatchEvent(new Event(SIGNED_OUT_EVENT)))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Sign in with Google' })).toBeInTheDocument(),
    )
    expect(window.location.search).toBe('?month=2026-09')
  })

  it('reports a server that cannot say who is signed in', async () => {
    vi.mocked(auth.me).mockRejectedValue(new TypeError('Failed to fetch'))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to fetch')
    expect(screen.queryByRole('button', { name: 'Sign in with Google' })).not.toBeInTheDocument()
  })
})
