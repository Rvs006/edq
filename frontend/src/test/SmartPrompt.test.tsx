import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SmartPrompt from '@/components/common/SmartPrompt'

describe('SmartPrompt', () => {
  it('renders the message content', () => {
    render(
      <SmartPrompt>
        <strong>3 manual tests remaining.</strong> Click on them to see instructions.
      </SmartPrompt>
    )

    expect(screen.getByText(/3 manual tests remaining/)).toBeInTheDocument()
    expect(screen.getByText(/Click on them to see instructions/)).toBeInTheDocument()
  })

  it('renders with warning variant by default (shows AlertTriangle icon)', () => {
    const { container } = render(
      <SmartPrompt>Warning message</SmartPrompt>
    )

    // Should have amber/warning background classes
    expect(container.firstChild).toHaveClass('bg-amber-50')
  })

  it('renders with info variant', () => {
    const { container } = render(
      <SmartPrompt variant="info">Info message</SmartPrompt>
    )

    expect(container.firstChild).toHaveClass('bg-blue-50')
    expect(screen.getByText('Info message')).toBeInTheDocument()
  })

  it('renders with success variant', () => {
    const { container } = render(
      <SmartPrompt variant="success">Success message</SmartPrompt>
    )

    expect(container.firstChild).toHaveClass('bg-emerald-50')
  })

  it('renders with error variant', () => {
    const { container } = render(
      <SmartPrompt variant="error">Error message</SmartPrompt>
    )

    expect(container.firstChild).toHaveClass('bg-red-50')
  })

  it('renders an action button when action prop is provided', () => {
    const handleAction = vi.fn()
    render(
      <SmartPrompt action={{ label: 'Go to first', onClick: handleAction }}>
        Test message
      </SmartPrompt>
    )

    const actionButton = screen.getByText('Go to first')
    expect(actionButton).toBeInTheDocument()
    expect(actionButton.tagName).toBe('BUTTON')
  })

  it('calls action onClick when the action button is clicked', async () => {
    const user = userEvent.setup()
    const handleAction = vi.fn()
    render(
      <SmartPrompt action={{ label: 'Go to first', onClick: handleAction }}>
        Test message
      </SmartPrompt>
    )

    await user.click(screen.getByText('Go to first'))
    expect(handleAction).toHaveBeenCalledTimes(1)
  })

  it('renders a dismiss button when onDismiss is provided', () => {
    const handleDismiss = vi.fn()
    render(
      <SmartPrompt onDismiss={handleDismiss}>
        Dismissible message
      </SmartPrompt>
    )

    const dismissButton = screen.getByLabelText('Dismiss')
    expect(dismissButton).toBeInTheDocument()
  })

  it('calls onDismiss when dismiss button is clicked', async () => {
    const user = userEvent.setup()
    const handleDismiss = vi.fn()
    render(
      <SmartPrompt onDismiss={handleDismiss}>
        Dismissible message
      </SmartPrompt>
    )

    await user.click(screen.getByLabelText('Dismiss'))
    expect(handleDismiss).toHaveBeenCalledTimes(1)
  })

  it('does not render action button when action prop is not provided', () => {
    render(<SmartPrompt>No action</SmartPrompt>)

    // Should only have the icon area and message, no buttons
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('does not render dismiss button when onDismiss is not provided', () => {
    render(<SmartPrompt>No dismiss</SmartPrompt>)

    expect(screen.queryByLabelText('Dismiss')).not.toBeInTheDocument()
  })

  it('renders both action and dismiss buttons together', () => {
    render(
      <SmartPrompt
        action={{ label: 'Fix now', onClick: vi.fn() }}
        onDismiss={vi.fn()}
      >
        Both buttons
      </SmartPrompt>
    )

    expect(screen.getByText('Fix now')).toBeInTheDocument()
    expect(screen.getByLabelText('Dismiss')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(
      <SmartPrompt className="mt-4 mb-2">Styled</SmartPrompt>
    )

    expect(container.firstChild).toHaveClass('mt-4')
    expect(container.firstChild).toHaveClass('mb-2')
  })
})
