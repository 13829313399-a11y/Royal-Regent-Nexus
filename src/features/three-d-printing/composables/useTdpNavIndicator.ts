import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

export function useTdpNavIndicator(selected: () => string) {
  const nav = ref<HTMLElement | null>(null)
  const indicator = reactive({ top: 0, left: 0, width: 0, height: 0, visible: false })
  let observer: ResizeObserver | undefined
  let frame = 0
  let revealSelected = false

  function measure() {
    frame = 0
    const root = nav.value
    const button = root?.querySelector<HTMLElement>('button[aria-current="page"]')
    if (!root || !button) {
      indicator.visible = false
      return
    }
    const outer = root.getBoundingClientRect()
    const inner = button.getBoundingClientRect()
    const top = inner.top - outer.top + root.scrollTop
    const left = inner.left - outer.left + root.scrollLeft
    if (revealSelected && root.scrollWidth > root.clientWidth) {
      const margin = 8
      if (left < root.scrollLeft + margin) root.scrollLeft = Math.max(0, left - margin)
      else if (left + inner.width > root.scrollLeft + root.clientWidth - margin)
        root.scrollLeft = left + inner.width - root.clientWidth + margin
    }
    revealSelected = false
    indicator.top = top
    indicator.left = left
    indicator.width = inner.width
    indicator.height = inner.height
    indicator.visible = true
  }

  function schedule(ensureVisible = false) {
    if (ensureVisible) revealSelected = true
    if (frame) cancelAnimationFrame(frame)
    frame = requestAnimationFrame(measure)
  }

  const onScroll = () => schedule()
  const onResize = () => schedule(true)
  watch(selected, async () => { await nextTick(); schedule(true) }, { flush: 'post' })
  onMounted(async () => {
    await nextTick()
    schedule(true)
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(onResize)
      if (nav.value) {
        observer.observe(nav.value)
        nav.value.querySelectorAll('button').forEach(button => observer?.observe(button))
      }
    }
    nav.value?.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onResize, { passive: true })
  })
  onBeforeUnmount(() => {
    if (frame) cancelAnimationFrame(frame)
    observer?.disconnect()
    nav.value?.removeEventListener('scroll', onScroll)
    window.removeEventListener('resize', onResize)
  })

  return { nav, indicator }
}
