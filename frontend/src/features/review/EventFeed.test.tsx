import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EventFeed } from './EventFeed.tsx'

describe('EventFeed', () => {
  it('prefixes each message with its local time; a bare status shows its state', () => {
    const at = new Date(2026, 9, 14, 9, 5, 7).toISOString()
    const status = { agent: 'amex', state: 'TASK_STATE_WORKING', text: null, at }
    render(<EventFeed events={[{ type: 'agent.status', data: status }]} working={false} />)
    expect(screen.getByRole('listitem'))
      .toHaveTextContent(/^2026\/10\/14 09:05:07 amex: TASK_STATE_WORKING$/)
    expect(screen.getByText('2026/10/14 09:05:07')).toHaveClass('feed-time')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it("shows an input request's whole text in red, since the question repeats none of it", () => {
    const at = new Date(2026, 9, 14, 9, 5, 7).toISOString()
    const text = 'No statement covers 2026-08. Load it on the statements page and continue.'
    const status = { agent: 'amex', state: 'TASK_STATE_INPUT_REQUIRED', text, at }
    render(<EventFeed events={[{ type: 'agent.status', data: status }]} working={false} />)
    expect(screen.getByRole('listitem'))
      .toHaveTextContent(`2026/10/14 09:05:07 amex: TASK_STATE_INPUT_REQUIRED — ${text}`)
    expect(screen.getByText(text)).toHaveClass('error')
    const working = { agent: 'amex', state: 'TASK_STATE_WORKING', text: 'Parsing', at }
    render(<EventFeed events={[{ type: 'agent.status', data: working }]} working={false} />)
    expect(screen.getByText('Parsing', { exact: false })).not.toHaveClass('error')
  })

  it('ends the last line with a spinner while the review is working', () => {
    const at = new Date(2026, 9, 14, 9, 5, 7).toISOString()
    const status = { agent: 'amex', state: 'TASK_STATE_WORKING', text: 'Parsing', at }
    render(<EventFeed events={[{ type: 'agent.status', data: status }]} working />)
    const [line] = screen.getAllByRole('listitem')
    expect(line).toHaveTextContent(/^2026\/10\/14 09:05:07 amex: TASK_STATE_WORKING — Parsing$/)
    expect(line).toContainElement(screen.getByRole('status', { name: 'Working' }))
  })
})
