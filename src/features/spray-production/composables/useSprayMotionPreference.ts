import { onBeforeUnmount, onMounted, ref } from 'vue'

/* 喷油工作区动效偏好：与注塑排产工作台保持同一口径。
   只有系统未要求减少动态效果、且页面当前可见时才播放装饰性动效；
   页面隐藏时停止，避免后台标签页继续跑动画与观察者。 */
export function useSprayMotionPreference() {
  const motionAllowed = ref(true)
  let media: MediaQueryList | undefined

  function sync() {
    motionAllowed.value = !(media?.matches ?? false) && !document.hidden
  }

  onMounted(() => {
    if (typeof window.matchMedia !== 'function') return
    media = window.matchMedia('(prefers-reduced-motion: reduce)')
    media.addEventListener?.('change', sync)
    document.addEventListener('visibilitychange', sync)
    sync()
  })

  onBeforeUnmount(() => {
    media?.removeEventListener?.('change', sync)
    document.removeEventListener('visibilitychange', sync)
  })

  return { motionAllowed }
}
