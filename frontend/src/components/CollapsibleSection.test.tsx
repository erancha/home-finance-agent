import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CollapsibleSection } from './CollapsibleSection.tsx'

describe('CollapsibleSection', () => {
  it('renders expanded by default and folds the body on toggle', () => {
    render(<CollapsibleSection title="Title"><p>Body</p></CollapsibleSection>)
    const toggle = screen.getByRole('button', { name: 'Title' })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Body')).toBeInTheDocument()

    fireEvent.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Body')).toBeNull()
  })

  it('starts collapsed when asked and unfolds on toggle', () => {
    render(<CollapsibleSection title="Title" defaultCollapsed><p>Body</p></CollapsibleSection>)
    const toggle = screen.getByRole('button', { name: 'Title' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Body')).toBeNull()

    fireEvent.click(toggle)

    expect(screen.getByText('Body')).toBeInTheDocument()
  })
})
