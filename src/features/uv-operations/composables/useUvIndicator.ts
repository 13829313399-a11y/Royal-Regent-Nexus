import { nextTick, onBeforeUnmount, onMounted, reactive, watch, type Ref } from 'vue'

export function useUvIndicator(root: Ref<HTMLElement | null>, selected: () => string) {
  const style = reactive({ opacity: '0', transform: 'translate(0px,0px)', width: '0px', height: '0px' })
  let frame = 0, disposed = false, observer: ResizeObserver | undefined
  function measure() {
    frame = 0
    const host = root.value, active = host?.querySelector<HTMLElement>('[aria-current="page"], [aria-selected="true"]')
    if (!host || !active || !active.getClientRects().length) { style.opacity = '0'; return }
    const box = host.getBoundingClientRect(), target = active.getBoundingClientRect()
    Object.assign(style, { opacity: '1', transform: `translate(${target.left-box.left+host.scrollLeft}px,${target.top-box.top+host.scrollTop}px)`, width: `${target.width}px`, height: `${target.height}px` })
  }
  function schedule() { if (!disposed && !document.hidden && !frame) frame = requestAnimationFrame(measure) }
  function visibility() { if (document.hidden) { cancelAnimationFrame(frame); frame=0 } else schedule() }
  watch(selected, async () => { await nextTick(); schedule() })
  onMounted(() => {
    observer = new ResizeObserver(schedule)
    if (root.value) { observer.observe(root.value); root.value.querySelectorAll('a,button').forEach(el => observer!.observe(el)); root.value.addEventListener('scroll', schedule, { passive: true }) }
    window.addEventListener('resize', schedule)
    document.addEventListener('visibilitychange', visibility)
    document.fonts?.ready.then(schedule)
    schedule()
  })
  onBeforeUnmount(() => { disposed = true; cancelAnimationFrame(frame); observer?.disconnect(); root.value?.removeEventListener('scroll', schedule); window.removeEventListener('resize', schedule); document.removeEventListener('visibilitychange', visibility) })
  return { style, schedule }
}
