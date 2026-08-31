import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DialogPanel } from './a11y'

function TestDialog({ onClose }) {
  return (
    <DialogPanel labelledBy="test-dialog-title" onClose={onClose}>
      <h2 id="test-dialog-title">Test dialog</h2>
      <select aria-label="Account">
        <option>Primary</option>
      </select>
      <input aria-label="Max bid" />
    </DialogPanel>
  )
}

describe('DialogPanel focus management', () => {
  it('does not reset focus when the close callback changes', () => {
    const { rerender } = render(<TestDialog onClose={() => {}} />)
    const account = screen.getByRole('combobox', { name: 'Account' })
    const maxBid = screen.getByRole('textbox', { name: 'Max bid' })

    expect(document.activeElement).toBe(account)
    maxBid.focus()
    rerender(<TestDialog onClose={() => {}} />)

    expect(document.activeElement).toBe(maxBid)
  })

  it('uses the latest close callback without resetting the dialog effect', () => {
    const firstClose = vi.fn()
    const latestClose = vi.fn()
    const { rerender } = render(<TestDialog onClose={firstClose} />)

    rerender(<TestDialog onClose={latestClose} />)
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(firstClose).not.toHaveBeenCalled()
    expect(latestClose).toHaveBeenCalledOnce()
  })
})
