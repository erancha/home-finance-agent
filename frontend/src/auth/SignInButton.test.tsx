import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as auth from '../api/auth.ts'
import { SignInButton } from './SignInButton.tsx'

vi.mock('../api/auth.ts')

beforeEach(() => {
  vi.mocked(auth.getAuthConfig).mockResolvedValue({ clientId: 'hfm-test-client' })
})

const renderButton = () => render(<SignInButton onSignedIn={vi.fn()} />)

const WHY = 'Why sign in with Google?'
const CLOSE = 'Close the explanation'

describe('SignInButton', () => {
  it('stays closed until asked for', () => {
    renderButton()

    expect(screen.getByRole('button', { name: WHY })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: CLOSE })).not.toBeInTheDocument()
  })

  it("opens the four reasons, ending with the link to Google's help page", async () => {
    const user = userEvent.setup()
    renderButton()
    const toggle = screen.getByRole('button', { name: WHY })

    await user.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('safer and easier').tagName).toBe('STRONG')
    const points = screen.getAllByRole('listitem')
    expect(points).toHaveLength(4)
    expect(points[0]).toHaveTextContent(
      'Google approves the sign-in. Google gives the app only a' +
        ' confirmation of who you are, with no access to your data (emails, contacts and more).',
    )
    expect(points[1]).toHaveTextContent(
      "You stay in control: you can disconnect the app at any time in your Google account's settings.",
    )
    expect(points[2]).toHaveTextContent('the app stores no passwords at all.')
    expect(screen.getByText('Google approves the sign-in.').tagName).toBe(
      'STRONG',
    )
    // The link says it opens a new tab, so nobody takes it for the way to close the explanation.
    const link = screen.getByRole('link', {
      name: "Google's full explanation (opens in a new tab)",
    })
    expect(link).toHaveAttribute('href', 'https://support.google.com/accounts/answer/12921417')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noreferrer')

    await user.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('frames the open explanation; its close button closes it and hands focus back', async () => {
    const user = userEvent.setup()
    const { container } = renderButton()
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
    const toggle = screen.getByRole('button', { name: WHY })

    const area = container.querySelector('.sign-in')
    expect(area).not.toHaveClass('sign-in-open')
    await user.click(toggle)
    // Opening scrolls down to the explanation's last line.
    expect(scroll).toHaveBeenLastCalledWith({ behavior: 'smooth', block: 'end' })
    expect(scroll.mock.instances).toContain(container.querySelector('.sign-in-why-text'))
    expect(area).toHaveClass('sign-in-open')

    await user.click(screen.getByRole('button', { name: CLOSE }))

    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
    expect(area).not.toHaveClass('sign-in-open')
    expect(toggle).toHaveFocus()
  })
})
