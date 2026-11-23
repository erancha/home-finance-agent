import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

  it("lays Google's button over the landing card's shared sign-in button", async () => {
    vi.mocked(auth.me).mockRejectedValue(notSignedIn)
    const { container } = render(<App />)

    const google = await screen.findByRole('button', { name: 'Sign in with Google' })
    const area = container.querySelector('main.landing > .landing-card > .sign-in') as HTMLElement
    const shared = area.querySelector(':scope > button.sign-in-button') as HTMLElement
    expect(shared).toHaveTextContent('GSign in with Google')
    // The shared button only shows; Google's own button, laid over it, takes the click.
    expect(shared).toHaveAttribute('aria-hidden', 'true')
    expect(shared).toHaveAttribute('tabindex', '-1')
    expect(google.closest('.sign-in-google')?.previousElementSibling).toBe(shared)
  })

  it('heads the signed-out card with the icon, the product name and the tagline', async () => {
    vi.mocked(auth.me).mockRejectedValue(notSignedIn)
    const { container } = render(<App />)

    const heading = await screen.findByRole('heading', { level: 1, name: 'Home Finance Agent' })
    expect(heading.querySelector('img.app-icon')).toHaveAttribute('src', '/favicon.svg')
    expect(screen.getByText('An AI agent that reviews your monthly card spending')).toHaveClass(
      'app-tagline',
    )
    // The build makes no stamp, so no line names the build.
    expect(container.querySelector('.app-version')).toBeNull()
    expect(container.querySelectorAll('.landing-pitch')).toHaveLength(2)
    expect(container.querySelectorAll('.landing-steps > li')).toHaveLength(3)
    expect(container.querySelectorAll('.landing-steps > li')[2]).toHaveTextContent(
      /^Read the summary: a pie of spending by category/,
    )
  })

  it('adds the details under the pitch from the More toggle', async () => {
    vi.mocked(auth.me).mockRejectedValue(notSignedIn)
    const user = userEvent.setup()
    const { container } = render(<App />)

    const more = await screen.findByRole('button', { name: 'More' })
    expect(more).toHaveAttribute('aria-expanded', 'false')
    expect(container.querySelector('.landing-card > .landing-details')).toBeNull()
    await user.click(more)

    const less = screen.getByRole('button', { name: 'Less' })
    expect(less).toHaveAttribute('aria-expanded', 'true')
    const details = container.querySelector('.landing-card > .landing-details') as HTMLElement
    expect(details.nextElementSibling).toBe(less)
    expect(within(details).getByText(/never guessed/)).toBeInTheDocument()
  })

  it('opening the sign-in explanation folds the details back', async () => {
    vi.mocked(auth.me).mockRejectedValue(notSignedIn)
    render(<App />)
    const more = await screen.findByRole('button', { name: 'More' })
    fireEvent.click(more)
    fireEvent.click(document.querySelector('.sign-in-why') as HTMLElement)
    expect(document.querySelector('.landing-card > .landing-details')).toBeNull()
    expect(more).toHaveAttribute('aria-expanded', 'false')
  })

  it('links under the card to the WhatsApp invite and the source, with no demo', async () => {
    vi.mocked(auth.me).mockRejectedValue(notSignedIn)
    const { container } = render(<App />)
    await screen.findByRole('heading', { level: 1 })

    const footer = container.querySelector('main.landing > footer.landing-links') as HTMLElement
    const [invite, source, ...rest] = within(footer).getAllByRole('link')
    expect(rest).toHaveLength(0)
    expect(invite).toHaveAccessibleName('Invite friends on WhatsApp')
    expect(invite.querySelector('.link-mark')).toHaveTextContent('💬')
    expect(invite).toHaveAttribute('target', '_blank')
    expect(invite).toHaveAttribute('rel', 'noreferrer')
    const url = new URL(invite.getAttribute('href') as string)
    expect(`${url.origin}${url.pathname}`).toBe('https://wa.me/')
    const paragraphs = (url.searchParams.get('text') as string).split('\n\n')
    expect(paragraphs[0]).toMatch(/^Hi! 👋 I got a recommendation for Home Finance Agent/)
    expect(paragraphs[paragraphs.length - 1]).toMatch(new RegExp(`\n${window.location.origin}$`))
    expect(source).toHaveAccessibleName('Source code on GitHub')
    expect(source).toHaveAttribute('href', 'https://github.com/erancha/home-finance-agent')
    expect(source).toHaveAttribute('target', '_blank')
    expect(source).toHaveAttribute('rel', 'noreferrer')
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
