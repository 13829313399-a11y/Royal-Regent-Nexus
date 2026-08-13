<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import AiMessage from './AiMessage.vue'
import type { AIConversationMessage } from './types'

const props = defineProps<{
  messages: AIConversationMessage[]
  feedbackEnabled?: boolean
  factoryId?: string
}>()

const listRoot = ref<HTMLElement | null>(null)

watch(
  () => props.messages.map((message) => `${message.id}:${message.text.length}:${message.status}`).join('|'),
  async () => {
    await nextTick()
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    listRoot.value?.scrollTo({
      top: listRoot.value.scrollHeight,
      behavior: reducedMotion ? 'auto' : 'smooth',
    })
  },
)
</script>

<template>
  <div
    ref="listRoot"
    class="min-h-0 flex-1 overflow-y-auto overscroll-contain py-4"
    role="log"
    aria-live="polite"
    aria-relevant="additions text"
    aria-label="AI 对话记录"
  >
    <div v-if="messages.length" class="space-y-4 px-4 sm:px-5">
      <AiMessage
        v-for="message in messages"
        :key="message.id"
        :message="message"
        :feedback-enabled="feedbackEnabled"
        :factory-id="factoryId"
      />
    </div>
    <div v-else class="flex items-center justify-center px-4 py-8 text-center sm:px-5">
      <div class="max-w-xs">
        <p class="text-sm font-semibold text-slate-800">需要页面帮助吗？</p>
        <p class="mt-2 text-xs leading-5 text-slate-500">
          我只会读取当前账号已获授权的信息。持久会话最多保留 30 天正文；临时会话不保存正文。
        </p>
      </div>
    </div>
    <slot />
  </div>
</template>
