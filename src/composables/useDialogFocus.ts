import { nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'

const modalInertOwners = new WeakMap<HTMLElement, { count: number; previous: boolean }>()

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
  returnFocus?: () => HTMLElement | null
  shouldRestoreFocus?: () => boolean
  inertBackground?: boolean
}

export function useDialogFocus(
  isOpen: () => boolean,
  root: Ref<HTMLElement | null>,
  options: DialogFocusOptions = {},
) {
  const announcement = ref('')
  let previousFocus: HTMLElement | null = null
  let activeRoot: HTMLElement | null = null
  let lastRoot: HTMLElement | null = null
  let generation = 0
  let inerted: HTMLElement[] = []

  function focusables() {
    return activeRoot
      ? Array.from(activeRoot.querySelectorAll<HTMLElement>(focusableSelector)).filter(el => {
        if (el.closest('[hidden], [inert]')) return false
        for (let parent: HTMLElement | null = el; parent; parent = parent.parentElement) { const style = getComputedStyle(parent); if (style.display === 'none' || style.visibility === 'hidden') return false }
        return true
      })
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
    for (const element of inerted) { const entry = modalInertOwners.get(element); if (entry && --entry.count === 0) { element.inert = entry.previous; modalInertOwners.delete(element) } }
    inerted = []
  }

  function restoreFocus() {
    const target = previousFocus ? options.returnFocus?.() ?? previousFocus : null
    const newerDialog = [...document.querySelectorAll<HTMLElement>('[aria-modal="true"]')].some(el => el !== lastRoot && el.getClientRects().length && !el.contains(target))
    if (!newerDialog && target?.isConnected && !target.closest('[inert]') && (options.shouldRestoreFocus?.() ?? true)) target.focus({ preventScroll: true })
    previousFocus = null
  }

  watch(isOpen, async (open) => {
    const version = ++generation
    if (typeof document === 'undefined') return
    if (open) {
      previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
      announcement.value = typeof options.openAnnouncement === 'function'
        ? options.openAnnouncement()
        : options.openAnnouncement ?? ''
      await nextTick()
      if (version !== generation || !isOpen()) return
      detach()
      activeRoot = root.value
      lastRoot = activeRoot
      if (options.inertBackground && activeRoot) {
        for (const element of Array.from(document.body.children)) {
          if (element instanceof HTMLElement && !element.contains(activeRoot) && !['SCRIPT', 'STYLE'].includes(element.tagName)) { const entry = modalInertOwners.get(element) ?? { count: 0, previous: element.inert }; entry.count++; modalInertOwners.set(element, entry); inerted.push(element); element.inert = true }
        }
      }
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
    generation++
    detach()
    restoreFocus()
  })

  return { announcement }
}
