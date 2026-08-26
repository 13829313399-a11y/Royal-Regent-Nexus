import { nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'summary',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

interface DialogFocusOptions {
  onEscape?: () => void
  openAnnouncement?: string | (() => string)
  initialFocus?: () => HTMLElement | null
}

export function useDialogFocus(
  isOpen: () => boolean,
  root: Ref<HTMLElement | null>,
  options: DialogFocusOptions = {},
) {
  const announcement = ref('')
  let previousFocus: HTMLElement | null = null
  let activeRoot: HTMLElement | null = null

  function focusables() {
    return activeRoot
      ? Array.from(activeRoot.querySelectorAll<HTMLElement>(focusableSelector))
      : []
  }

  function handleKeydown(event: KeyboardEvent) {
    if (!activeRoot) return
    if (event.key === 'Escape' && options.onEscape) {
      event.preventDefault()
      event.stopPropagation()
      options.onEscape()
      return
    }
    if (event.key !== 'Tab') return

    const items = focusables()
    if (!items.length) {
      event.preventDefault()
      activeRoot.focus({ preventScroll: true })
      return
    }

    const first = items[0]!
    const last = items[items.length - 1]!
    const current = document.activeElement
    if (event.shiftKey && (current === first || !activeRoot.contains(current))) {
      event.preventDefault()
      last.focus({ preventScroll: true })
    } else if (!event.shiftKey && current === last) {
      event.preventDefault()
      first.focus({ preventScroll: true })
    }
  }

  function detach() {
    activeRoot?.removeEventListener('keydown', handleKeydown)
    activeRoot = null
  }

  function restoreFocus() {
    previousFocus?.focus({ preventScroll: true })
    previousFocus = null
  }

  watch(isOpen, async (open) => {
    if (typeof document === 'undefined') return
    if (open) {
      previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
      announcement.value = typeof options.openAnnouncement === 'function'
        ? options.openAnnouncement()
        : options.openAnnouncement ?? ''
      await nextTick()
      detach()
      activeRoot = root.value
      activeRoot?.addEventListener('keydown', handleKeydown)
      const target = options.initialFocus?.() ?? focusables()[0] ?? activeRoot
      target?.focus({ preventScroll: true })
      return
    }
    announcement.value = ''
    detach()
    restoreFocus()
  }, { flush: 'post', immediate: true })

  onBeforeUnmount(() => {
    detach()
    restoreFocus()
  })

  return { announcement }
}
