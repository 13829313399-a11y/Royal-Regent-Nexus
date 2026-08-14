<script setup lang="ts">
import { FileQuestion } from '@lucide/vue'
import type { AIBusinessResult, AISourceSummary } from '@/features/ai-assistant/types'

defineProps<{ result: AIBusinessResult; sources: AISourceSummary[] }>()
</script>

<template>
  <article class="mx-4 mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 sm:mx-5" data-safe-result-fallback>
    <div class="flex items-start gap-2">
      <FileQuestion class="mt-0.5 size-4 shrink-0 text-slate-500" aria-hidden="true" />
      <div class="min-w-0">
        <h3 class="text-xs font-semibold text-slate-900">{{ result.title || 'AI 结果' }}</h3>
        <p class="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-slate-600">{{ result.summary }}</p>
        <p class="mt-2 text-[10px] text-slate-500">该结果使用安全文本回退显示，不会执行动态 HTML。</p>
      </div>
    </div>
  </article>
</template>
