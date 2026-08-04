import { nextTick, onBeforeUnmount, watch, type Ref } from 'vue'

export function useDialogFocus(isOpen: () => boolean, root: Ref<HTMLElement | null>) {
  let previousFocus: HTMLElement | null = null

  watch(isOpen, async (open) => {
    if (typeof document === 'undefined') return
    if (open) {
      previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
      await nextTick()
      root.value?.focus()
      return
    }
    previousFocus?.focus()
    previousFocus = null
  }, { flush: 'post', immediate: true })

  onBeforeUnmount(() => previousFocus?.focus())
}
