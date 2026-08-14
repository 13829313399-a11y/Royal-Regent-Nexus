import { nextTick, ref, watch, type Ref } from 'vue'
import type { AIConversationMessage } from '@/features/ai-assistant/types'

const BOTTOM_THRESHOLD = 80

export function useConversationAutoScroll(
  root: Ref<HTMLElement | null>,
  messages: Ref<readonly AIConversationMessage[]>,
) {
  const isNearBottom = ref(true)
  const hasUnseenContent = ref(false)
  const followStreaming = ref(true)

  function reducedMotion() {
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  }

  function measure() {
    const element = root.value
    if (!element) return true
    return element.scrollHeight - element.scrollTop - element.clientHeight <= BOTTOM_THRESHOLD
  }

  function onScroll() {
    isNearBottom.value = measure()
    followStreaming.value = isNearBottom.value
    if (isNearBottom.value) hasUnseenContent.value = false
  }

  function scrollToLatest(force = true) {
    const element = root.value
    if (!element || (!force && !followStreaming.value)) return
    element.scrollTo({
      top: element.scrollHeight,
      behavior: reducedMotion() ? 'auto' : 'smooth',
    })
    isNearBottom.value = true
    followStreaming.value = true
    hasUnseenContent.value = false
  }

  watch(
    () => ({
      signature: messages.value.map((message) => `${message.id}:${message.text.length}:${message.status}`).join('|'),
      firstId: messages.value[0]?.id ?? '',
      lastId: messages.value.at(-1)?.id ?? '',
      lastUserId: [...messages.value].reverse().find((message) => message.role === 'user')?.id ?? '',
    }),
    async (next, previous) => {
      const element = root.value
      const previousHeight = element?.scrollHeight ?? 0
      const prepended = Boolean(previous?.firstId && next.firstId !== previous.firstId && next.lastId === previous.lastId)
      const userSent = next.lastUserId !== (previous?.lastUserId ?? '')
      await nextTick()
      if (!root.value) return
      if (prepended) {
        root.value.scrollTop += root.value.scrollHeight - previousHeight
        return
      }
      if (userSent || followStreaming.value || isNearBottom.value) {
        scrollToLatest(true)
      } else {
        hasUnseenContent.value = true
      }
    },
  )

  return { isNearBottom, hasUnseenContent, followStreaming, onScroll, scrollToLatest }
}
