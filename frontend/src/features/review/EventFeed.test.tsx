import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EventFeed } from './EventFeed.tsx'

describe('EventFeed', () => {
  it('prefixes each message with its local time; a bare status shows its state', () => {
    const at = new Date(2026, 9, 14, 9, 5, 7).toISOString()
    const status = { agent: 'amex', state: 'TASK_STATE_WORKING', text: null, at }
    render(<EventFeed events={[{ type: 'agent.status', data: status }]} />)
    expect(screen.getByRole('listitem'))
      .toHaveTextContent(/^2026\/10\/14 09:05:07 amex: TASK_STATE_WORKING$/)
    expect(screen.getByText('2026/10/14 09:05:07')).toHaveClass('feed-time')
  })
})
