<script setup lang="ts">
import { ref } from 'vue'
import { Bot, Check, Copy, UserRound } from '@lucide/vue'
import type { AIConversationMessage } from './types'
import FeedbackControls from '@/features/nexus-copilot/components/FeedbackControls.vue'
import AiRichText from '@/features/nexus-copilot/presentation/AiRichText.vue'

withDefaults(defineProps<{
  message: AIConversationMessage
  feedbackEnabled?: boolean
  factoryId?: string
  richTextEnabled?: boolean
}>(), {
  feedbackEnabled: false,
  factoryId: '',
  richTextEnabled: true,
})

const copied = ref(false)

async function copyMessage(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    window.setTimeout(() => { copied.value = false }, 1_500)
  } catch {
    copied.value = false
  }
}
</script>

<template>
  <article
    class="flex gap-3"
    :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
    :aria-label="message.role === 'user' ? '你的消息' : 'AI 回复'"
    :data-message-role="message.role"
  >
    <span
      v-if="message.role === 'assistant'"
      class="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground"
      aria-hidden="true"
    >
      <Bot class="size-4" />
    </span>
    <div
      class="min-w-0 text-sm leading-6"
      :class="message.role === 'user'
        ? 'max-w-[84%] rounded-2xl rounded-br-md bg-primary px-3.5 py-3 text-primary-foreground shadow-sm'
        : 'max-w-[min(100%,960px)] flex-1 py-1 text-slate-700'"
    >
      <p v-if="message.role === 'user'" class="whitespace-pre-wrap break-words">{{ message.text }}</p>
      <AiRichText
        v-else-if="message.text && richTextEnabled"
        :source="message.text"
        :streaming="message.status === 'streaming'"
      />
      <p v-else-if="message.text" class="whitespace-pre-wrap break-words">{{ message.text }}</p>
      <span
        v-if="message.status === 'streaming' && !message.text"
        class="inline-flex items-center gap-1.5 text-xs text-slate-500"
        aria-label="AI 正在回复"
      >
        <span class="ai-thinking-dot" />
        <span class="ai-thinking-dot [animation-delay:120ms]" />
        <span class="ai-thinking-dot [animation-delay:240ms]" />
      </span>
      <span v-if="message.status === 'error'" class="mt-2 block text-xs font-medium text-rose-600">
        本次响应未正常完成
      </span>
      <span v-if="message.status === 'truncated'" class="mt-2 block text-xs font-medium text-amber-700">
        回答过长，后续内容未显示
      </span>
      <span v-if="message.status === 'cancelled'" class="mt-2 block text-xs font-medium text-amber-700">
        已停止生成
      </span>
      <div
        v-if="message.role === 'assistant' && message.text"
        class="mt-2 flex items-center gap-2 border-t border-slate-100 pt-2"
      >
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] font-semibold text-slate-500 hover:bg-slate-100 hover:text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          :aria-label="copied ? '回复已复制' : '复制 AI 回复'"
          @click="copyMessage(message.text)"
        >
          <Check v-if="copied" class="size-3.5 text-emerald-600" aria-hidden="true" />
          <Copy v-else class="size-3.5" aria-hidden="true" />
          {{ copied ? '已复制' : '复制' }}
        </button>
      </div>
      <FeedbackControls
        v-if="feedbackEnabled && factoryId && message.role === 'assistant' && message.status === 'complete' && message.feedbackTarget"
        :factory-id="factoryId"
        :target-type="message.feedbackTarget.type"
        :target-id="message.feedbackTarget.id"
      />
    </div>
    <span
      v-if="message.role === 'user'"
      class="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-foreground"
      aria-hidden="true"
    >
      <UserRound class="size-4" />
    </span>
  </article>
</template>

<style scoped>
.ai-thinking-dot {
  width: 0.34rem;
  height: 0.34rem;
  border-radius: 9999px;
  background: currentColor;
  animation: ai-thinking 900ms ease-in-out infinite alternate;
}

@keyframes ai-thinking {
  from { opacity: 0.25; transform: translateY(1px); }
  to { opacity: 0.9; transform: translateY(-1px); }
}

@media (prefers-reduced-motion: reduce) {
  .ai-thinking-dot { animation: none; }
}
</style>
