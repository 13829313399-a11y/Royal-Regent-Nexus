<script setup lang="ts">
import type { AIBusinessResult, AISourceSummary } from '@/features/ai-assistant/types'
import ResultFrame from '../ResultFrame.vue'

defineProps<{ result: AIBusinessResult; sources: AISourceSummary[] }>()

function linkHref(route: string, query?: Record<string, string>) {
  const encoded = new URLSearchParams(query ?? {}).toString()
  return encoded ? `${route}?${encoded}` : route
}
</script>

<template>
  <ResultFrame :result="result">
    <section v-if="result.kind === 'knowledge_search' && result.knowledgeSearch" class="mt-2 space-y-2" data-ai-knowledge-search>
      <p v-if="result.knowledgeSearch.evidenceMissing" class="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-[11px] font-medium text-amber-900">
        当前没有可引用的有效知识，AI 不会补写缺失规则。
      </p>
      <ul v-else class="space-y-2">
        <li v-for="hit in result.knowledgeSearch.hits" :key="`${hit.citation.knowledgeId}:${hit.citation.version}:${hit.citation.sectionId}`" class="rounded-lg border border-sky-200 bg-white p-2.5">
          <p class="text-[11px] font-bold text-slate-900">{{ hit.citation.heading }}</p>
          <p class="mt-1 whitespace-pre-wrap break-words text-[11px] leading-5 text-slate-600">{{ hit.textMarkdown }}</p>
          <p class="mt-2 text-[10px] text-slate-500">知识版本 {{ hit.citation.version }} · 审核 {{ hit.citation.reviewedAt }}</p>
          <div v-if="hit.links.length" class="mt-2 flex flex-wrap gap-2">
            <a v-for="link in hit.links" :key="`${link.route}:${link.label}`" :href="linkHref(link.route, link.query)" class="font-semibold text-sky-700 underline decoration-sky-300 underline-offset-2">{{ link.label }}</a>
          </div>
          <details class="mt-2 text-[10px] text-slate-500">
            <summary class="cursor-pointer font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600">引用技术详情</summary>
            <p class="mt-1 break-all">Citation：{{ hit.citation.knowledgeId }}@{{ hit.citation.version }} · 段落 {{ hit.citation.sectionId }} · {{ hit.citation.sourcePath }}</p>
          </details>
        </li>
      </ul>
      <p class="text-[10px] text-slate-500">流程知识仅作指导；实时业务事实冲突时，以正式业务工具为准。</p>
    </section>
  </ResultFrame>
</template>
