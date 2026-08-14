<script setup lang="ts">
import { ExternalLink, FileSearch } from '@lucide/vue'
import type { AIBusinessResult, AIEntityLink } from '@/features/ai-assistant/types'

defineProps<{ result: AIBusinessResult }>()

const factoryLabels: Record<string, string> = {
  'huakang-a': '华康 A',
  'huakang-b': '华康 B',
  'huakang-c': '华康 C',
  'huakang-d': '华康 D',
  huadeng: '华登',
  huaxing: '华兴',
}

const evidenceLabels: Record<string, string> = {
  FORMAL_DOMAIN_SERVICE: '正式业务数据',
  VERSIONED_MODULE_KNOWLEDGE: '已审核流程知识',
  AUTHENTICATED_SERVER_CONTEXT: '当前登录上下文',
  USER_PROVIDED: '用户提供内容',
  MODEL_INFERENCE: 'AI 推断',
}

function linkHref(link: AIEntityLink) {
  const query = new URLSearchParams(link.query ?? {}).toString()
  return query ? `${link.route}?${query}` : link.route
}
</script>

<template>
  <article class="mx-4 mt-3 rounded-xl border border-sky-200 bg-sky-50/80 p-3 sm:mx-5" data-domain-result>
    <div class="flex items-start gap-2">
      <FileSearch class="mt-0.5 size-4 shrink-0 text-sky-700" aria-hidden="true" />
      <div class="min-w-0 flex-1">
        <h3 class="text-xs font-semibold text-slate-900">{{ result.title }}</h3>
        <slot />
        <p v-if="result.summary" class="mt-2 whitespace-pre-wrap break-words text-xs leading-5 text-slate-600">
          {{ result.summary }}
        </p>
        <p v-if="result.factoryId || result.asOf" class="mt-2 text-[11px] text-slate-500">
          <span v-if="result.factoryId">厂区：{{ factoryLabels[result.factoryId] ?? result.factoryId }}</span>
          <span v-if="result.factoryId && result.asOf"> · </span>
          <span v-if="result.asOf">数据时间：{{ result.asOf }}</span>
        </p>
        <p v-if="result.truncated" class="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-[11px] font-medium text-amber-800">
          结果已按安全上限截断。可继续查看下一页，或缩小查询范围。
        </p>
        <section
          v-if="result.evidence?.length"
          class="mt-2 rounded-lg border border-emerald-200 bg-white px-2.5 py-2 text-[10px] text-slate-600"
          data-ai-evidence
          aria-label="结果证据"
        >
          <div class="flex flex-wrap gap-x-2 gap-y-1">
            <strong class="text-emerald-800">{{ evidenceLabels[result.evidence[0]!.sourceLevel] ?? '受控来源' }}</strong>
            <span v-if="result.evidence[0]!.factoryId">厂区 {{ result.evidence[0]!.factoryId }}</span>
            <span>时点 {{ result.evidence[0]!.asOf }}</span>
            <span>{{ result.evidence.some((item) => item.truncated) ? '不完整/已截断' : '完整性：未截断' }}</span>
          </div>
          <details class="mt-1 border-t border-emerald-100 pt-1">
            <summary class="cursor-pointer font-medium text-slate-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-600">技术详情</summary>
            <p class="mt-1 break-all text-slate-500">
              {{ result.evidence[0]!.sourceLevel }} · {{ result.evidence[0]!.evidenceId }}
            </p>
          </details>
        </section>
        <div v-if="result.links.length" class="mt-2 flex flex-wrap gap-2">
          <a
            v-for="link in result.links"
            :key="`${link.route}:${link.label}`"
            :href="linkHref(link)"
            class="inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 text-[11px] font-semibold text-sky-700 ring-1 ring-inset ring-sky-200 hover:bg-sky-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
          >
            {{ link.label }}
            <ExternalLink class="size-3" aria-hidden="true" />
          </a>
        </div>
        <details class="mt-2 text-[10px] text-slate-500">
          <summary class="cursor-pointer font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600">结果技术信息</summary>
          <p class="mt-1 break-all">类型 {{ result.kind }} · 来源 {{ result.sourceType }}</p>
          <slot name="technical" />
        </details>
      </div>
    </div>
  </article>
</template>
