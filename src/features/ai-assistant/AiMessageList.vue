<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowDown } from '@lucide/vue'
import AiMessage from './AiMessage.vue'
import type { AIConversationMessage, AITurnPresentation } from './types'
import { useConversationAutoScroll } from '@/features/nexus-copilot/conversation/useConversationAutoScroll'
import TurnPresentationDetails from '@/features/nexus-copilot/presentation/TurnPresentationDetails.vue'

const props = defineProps<{
  messages: AIConversationMessage[]
  feedbackEnabled?: boolean
  factoryId?: string
  turns?: readonly AITurnPresentation[]
  richTextEnabled?: boolean
  presentationEnabled?: boolean
}>()

const listRoot = ref<HTMLElement | null>(null)
const messageRef = computed(() => props.messages)
const turnByAssistant = computed(() => new Map(
  (props.turns ?? []).flatMap((turn) => turn.assistantMessageId ? [[turn.assistantMessageId, turn] as const] : []),
))
const { hasUnseenContent, onScroll, scrollToLatest } = useConversationAutoScroll(
  listRoot,
  messageRef,
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
    @scroll.passive="onScroll"
  >
    <div v-if="messages.length" class="space-y-4 px-4 sm:px-5">
      <template v-for="message in messages" :key="message.id">
        <AiMessage
          :message="message"
          :feedback-enabled="feedbackEnabled"
          :factory-id="factoryId"
          :rich-text-enabled="richTextEnabled"
        />
        <TurnPresentationDetails
          v-if="presentationEnabled !== false && message.role === 'assistant' && turnByAssistant.get(message.id)"
          :turn="turnByAssistant.get(message.id)!"
        />
      </template>
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
    <button
      v-if="hasUnseenContent"
      type="button"
      class="sticky bottom-3 ml-auto mr-3 flex items-center gap-1 rounded-full border border-border bg-card px-3 py-2 text-xs font-semibold text-primary shadow-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      @click="scrollToLatest(true)"
    >
      <ArrowDown class="size-3.5" aria-hidden="true" />
      有新内容
    </button>
  </div>
</template>
