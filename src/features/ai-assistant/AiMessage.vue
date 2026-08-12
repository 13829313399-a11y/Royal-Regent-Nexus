<script setup lang="ts">
import { Bot, UserRound } from '@lucide/vue'
import type { AIConversationMessage } from './types'

defineProps<{
  message: AIConversationMessage
}>()
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
      class="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white"
      aria-hidden="true"
    >
      <Bot class="size-4" />
    </span>
    <div
      class="max-w-[84%] rounded-2xl px-3.5 py-3 text-sm leading-6 shadow-sm"
      :class="message.role === 'user'
        ? 'rounded-br-md bg-slate-900 text-white'
        : 'rounded-bl-md border border-slate-200 bg-white text-slate-700'"
    >
      <p class="whitespace-pre-wrap break-words">{{ message.text }}</p>
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
    </div>
    <span
      v-if="message.role === 'user'"
      class="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-xl bg-sky-100 text-sky-700"
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
