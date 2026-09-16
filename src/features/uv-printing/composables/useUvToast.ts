import { computed, ref, type ComputedRef } from 'vue'
import type { Tone } from '@/data/enterpriseMock'

/**
 * 工作区局部 Toast：位于工作台标题区下方右侧，最大宽约 420px。
 * 普通通知使用 role="status"，阻断错误由页面内 role="alert" 承担，
 * 不能只依赖会自动消失的 Toast。
 */

export interface UvToast {
  id: number
  message: string
  tone: Tone
  /** 成功提示说明已完成的对象，不只写「成功」。 */
  detail: string
  /** 失败提示是否提供重试入口。 */
  retryable: boolean
}

let sequence = 0

export function useUvToast(timeoutMs = 6000): {
  toasts: ComputedRef<UvToast[]>
  push: (toast: Omit<UvToast, 'id'>) => number
  dismiss: (id: number) => void
  clear: () => void
} {
  const toasts = ref<UvToast[]>([])

  function dismiss(id: number) {
    toasts.value = toasts.value.filter((toast) => toast.id !== id)
  }

  function push(toast: Omit<UvToast, 'id'>) {
    sequence += 1
    const id = sequence
    toasts.value = [...toasts.value.slice(-3), { ...toast, id }]
    if (toast.tone !== 'red') {
      window.setTimeout(() => dismiss(id), timeoutMs)
    }
    return id
  }

  return {
    toasts: computed(() => toasts.value),
    push,
    dismiss,
    clear: () => { toasts.value = [] },
  }
}
