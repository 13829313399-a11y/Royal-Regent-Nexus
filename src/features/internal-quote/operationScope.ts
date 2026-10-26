import { onBeforeUnmount, watch } from 'vue'

// Stop a multi-step native operation before another request after its page disappears.
export function useQuoteOperationScope(identity: () => unknown) {
  let generation = 0
  watch(identity, () => { ++generation }, { flush: 'sync' })
  onBeforeUnmount(() => { ++generation })
  return () => {
    const started = generation
    return () => {
      if (started !== generation) throw new Error('报价上下文已变化，请在当前页面重新操作。')
    }
  }
}
