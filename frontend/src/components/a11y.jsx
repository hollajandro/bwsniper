import { useEffect, useEffectEvent, useRef } from 'react'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export function useDialogFocus(active, onClose) {
  const dialogRef = useRef(null)
  const previousFocusRef = useRef(null)
  const closeDialog = useEffectEvent(() => onClose?.())

  useEffect(() => {
    if (!active) return undefined

    previousFocusRef.current = document.activeElement
    const dialog = dialogRef.current
    const focusable = dialog
      ? Array.from(dialog.querySelectorAll(FOCUSABLE_SELECTOR))
        .filter(node => !node.hasAttribute('disabled') && node.getAttribute('aria-hidden') !== 'true')
      : []
    const initialFocus = focusable[0] || dialog
    initialFocus?.focus?.()

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        event.stopPropagation()
        closeDialog()
        return
      }

      if (event.key !== 'Tab' || focusable.length === 0) return

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = ''
      previousFocusRef.current?.focus?.()
    }
  }, [active])

  return dialogRef
}

export function DialogPanel({ active = true, labelledBy, onClose, className, children, ...props }) {
  const dialogRef = useDialogFocus(active, onClose)

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
      tabIndex={-1}
      className={className}
      {...props}
    >
      {children}
    </div>
  )
}

export function activateOnEnterOrSpace(handler) {
  return event => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    handler(event)
  }
}
