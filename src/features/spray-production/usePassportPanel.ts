import { ref, watch, nextTick, onBeforeUnmount, type Ref } from 'vue'

/** Native passport focus follows dialog close, before returning to its source. */
export function usePassportPanel(selected: Ref<string|null>) {
  const panel = ref<HTMLDialogElement|null>(null), wide = window.matchMedia('(min-width:1680px)')
  let trigger: HTMLElement|null = null, generation = 0, disposed = false
  async function syncPanel() {
    const current = ++generation
    await nextTick()
    if (disposed || current !== generation || !panel.value) return
    const element = panel.value
    element.close()
    if (selected.value) {
      if (wide.matches) element.show(); else element.showModal()
      element.focus()
    } else if (!document.querySelector('dialog[open]')) {
      const target = trigger?.isConnected && trigger !== document.body ? trigger : document.querySelector<HTMLElement>('[data-spray-focus-fallback]')
      target?.focus(); trigger=null
    }
  }
  watch(selected, (id, old) => { if (id && !old) trigger=document.activeElement as HTMLElement; void syncPanel() }, {immediate:true})
  wide.addEventListener('change', syncPanel)
  onBeforeUnmount(() => { disposed=true; generation++; wide.removeEventListener('change',syncPanel); panel.value?.close() })
  return { panel, focus: async () => { await nextTick(); if (!disposed && selected.value) panel.value?.focus() } }
}
