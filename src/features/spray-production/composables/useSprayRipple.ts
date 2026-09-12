import { onBeforeUnmount, onMounted, type Ref } from 'vue'

/* 喷油工作区点击波纹：根节点一次性委托监听，不新增按钮包装组件。
   只在真实按压（pointerdown）时写入 data-spray-ripple，由 CSS 伪元素播放扩散，
   因此不会改动任何按钮的事件、禁用状态或可访问名称。
   非指针设备（键盘）不触发；减少动态效果时不播放。 */
export function useSprayRipple(root: Ref<HTMLElement | null>, allowed: Ref<boolean>) {
  const pending = new Set<HTMLElement>()
  let timer = 0

  function paint(event: Event) {
    if (!allowed.value) return
    const target = event.target
    const element = target instanceof Element ? target.closest('button, label.spray-file-trigger, .spray-nav a') : null
    if (!(element instanceof HTMLElement)) return
    /* 清除上一轮残留后再写入，保证连续点击每次都重播一次扩散。 */
    element.removeAttribute('data-spray-ripple')
    void element.offsetWidth
    element.setAttribute('data-spray-ripple', '')
    pending.add(element)
    if (timer) return
    timer = window.setTimeout(() => {
      timer = 0
      pending.forEach(item => item.removeAttribute('data-spray-ripple'))
      pending.clear()
    }, 600)
  }

  onMounted(() => root.value?.addEventListener('pointerdown', paint, { passive: true }))

  onBeforeUnmount(() => {
    root.value?.removeEventListener('pointerdown', paint)
    if (timer) window.clearTimeout(timer)
    pending.forEach(item => item.removeAttribute('data-spray-ripple'))
    pending.clear()
  })
}
