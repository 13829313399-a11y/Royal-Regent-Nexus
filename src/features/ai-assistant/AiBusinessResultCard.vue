<script setup lang="ts">
import { ExternalLink, FileSearch, ShieldCheck } from '@lucide/vue'
import { RouterLink } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import type {
  AIBusinessResult,
  AIEntityLink,
  AIInternalQuoteSummary,
  AISourceSummary,
} from './types'

defineProps<{
  results: AIBusinessResult[]
  sources: AISourceSummary[]
}>()

function linkHref(link: AIEntityLink) {
  const query = new URLSearchParams(link.query ?? {}).toString()
  return query ? `${link.route}?${query}` : link.route
}

function numberOrDash(value: number | undefined) {
  return value === undefined ? '—' : String(value)
}

function internalQuoteLink(
  quote: AIInternalQuoteSummary,
  factoryId: string | undefined,
): RouteLocationRaw {
  return {
    name: quote.navigationTarget === 'summary'
      ? 'internal-quote-summary'
      : 'internal-quote-collaboration',
    params: { quoteId: quote.quoteId },
    query: factoryId ? { factory: factoryId } : {},
  }
}
</script>

<template>
  <div
    v-if="results.length || sources.length"
    data-ai-business-results
    class="mx-4 mt-3 space-y-2 sm:mx-5"
  >
    <article
      v-for="result in results"
      :key="result.id"
      class="rounded-xl border border-sky-200 bg-sky-50/80 p-3"
    >
      <div class="flex items-start gap-2">
        <FileSearch class="mt-0.5 size-4 shrink-0 text-sky-700" aria-hidden="true" />
        <div class="min-w-0 flex-1">
          <h3 class="text-xs font-semibold text-slate-900">{{ result.title }}</h3>
          <div v-if="result.kind === 'plan_context' && result.planContext" class="mt-2 grid gap-2 sm:grid-cols-2">
            <section class="rounded-lg border border-emerald-200 bg-white p-2.5" data-plan-kind="published">
              <p class="text-[11px] font-bold text-emerald-700">当前执行 PUBLISHED</p>
              <template v-if="result.planContext.executionPublished">
                <p class="mt-1 text-[11px] text-slate-600">
                  日期 {{ result.planContext.executionPublished.businessDate || '—' }}
                  · 版本 {{ numberOrDash(result.planContext.executionPublished.revision) }}
                </p>
                <p class="mt-1 text-[11px] text-slate-600">
                  任务 {{ numberOrDash(result.planContext.executionPublished.taskCount) }}
                  · 运行中 {{ numberOrDash(result.planContext.executionPublished.runningCount) }}
                </p>
              </template>
              <p v-else class="mt-1 text-[11px] text-slate-500">当前没有已发布执行计划</p>
            </section>
            <section class="rounded-lg border border-amber-200 bg-white p-2.5" data-plan-kind="draft">
              <p class="text-[11px] font-bold text-amber-700">规划草案 DRAFT</p>
              <template v-if="result.planContext.planningDraft">
                <p class="mt-1 text-[11px] text-slate-600">
                  日期 {{ result.planContext.planningDraft.businessDate || '—' }}
                  · 版本 {{ numberOrDash(result.planContext.planningDraft.revision) }}
                </p>
                <p class="mt-1 text-[11px] text-slate-600">
                  任务 {{ numberOrDash(result.planContext.planningDraft.taskCount) }}
                </p>
              </template>
              <p v-else class="mt-1 text-[11px] text-slate-500">当前没有规划草案</p>
            </section>
          </div>
          <dl v-if="result.kind === 'backlog' && result.backlog" class="mt-2 grid grid-cols-2 gap-2 rounded-lg border border-sky-200 bg-white p-2.5 text-[11px] sm:grid-cols-3">
            <div>
              <dt class="text-slate-500">全部待排</dt>
              <dd class="mt-0.5 font-bold text-slate-900">{{ numberOrDash(result.backlog.total) }}</dd>
            </div>
            <div>
              <dt class="text-slate-500">本次返回</dt>
              <dd class="mt-0.5 font-bold text-slate-900">{{ numberOrDash(result.backlog.returned) }}</dd>
            </div>
            <div class="col-span-2 sm:col-span-1">
              <dt class="text-slate-500">数据范围</dt>
              <dd class="mt-0.5 break-words font-semibold text-slate-700">
                {{ result.backlog.sourceBusinessLabel || result.backlog.sourceScope || '当前已验证厂区' }}
              </dd>
            </div>
          </dl>
          <section
            v-if="result.kind === 'internal_quote_list' && result.internalQuote"
            class="mt-2 space-y-2"
            data-ai-internal-quote-list
          >
            <p class="rounded-lg border border-sky-200 bg-white px-2.5 py-2 text-[11px] text-slate-600">
              共 {{ result.internalQuote.total }} 条，本次返回 {{ result.internalQuote.returned }} 条
            </p>
            <ul v-if="result.internalQuote.quotes.length" class="space-y-2">
              <li
                v-for="quote in result.internalQuote.quotes"
                :key="quote.quoteId"
                class="rounded-lg border border-sky-200 bg-white p-2.5"
              >
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <div class="min-w-0">
                    <p class="break-words text-xs font-bold text-slate-900">{{ quote.quoteNo }}</p>
                    <p class="mt-0.5 break-words text-[11px] text-slate-600">
                      客户：{{ quote.customer || '—' }} · 版本：{{ quote.versionLabel || '—' }}
                    </p>
                  </div>
                  <span class="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-800">
                    {{ quote.statusLabel }}
                  </span>
                </div>
                <p class="mt-1 text-[11px] text-slate-600">
                  当前环节：{{ quote.currentStageLabel }}
                </p>
                <p class="mt-1 text-[10px] text-slate-500">
                  更新时间：{{ quote.updatedAt || '—' }}
                </p>
                <RouterLink
                  :to="internalQuoteLink(quote, result.factoryId)"
                  class="mt-2 inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-700 ring-1 ring-inset ring-sky-200 hover:bg-sky-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
                >
                  打开内部报价
                  <ExternalLink class="size-3" aria-hidden="true" />
                </RouterLink>
              </li>
            </ul>
            <p v-else class="rounded-lg border border-dashed border-slate-300 bg-white p-3 text-center text-[11px] text-slate-500">
              当前筛选条件下没有内部报价
            </p>
          </section>
          <p v-if="result.summary" class="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-slate-600">
            {{ result.summary }}
          </p>
          <p v-if="result.factoryId || result.asOf" class="mt-2 text-[11px] text-slate-500">
            <span v-if="result.factoryId">厂区：{{ result.factoryId }}</span>
            <span v-if="result.factoryId && result.asOf"> · </span>
            <span v-if="result.asOf">数据时间：{{ result.asOf }}</span>
          </p>
          <p v-if="result.truncated" class="mt-1 text-[11px] font-medium text-amber-700">
            结果已按安全上限截断
          </p>
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
        </div>
      </div>
    </article>

    <section v-if="sources.length" class="rounded-xl border border-slate-200 bg-white p-3" aria-label="回答来源">
      <div class="flex items-center gap-2 text-xs font-semibold text-slate-800">
        <ShieldCheck class="size-4 text-emerald-600" aria-hidden="true" />
        回答来源
      </div>
      <ul class="mt-2 space-y-2">
        <li v-for="source in sources" :key="source.id" class="text-[11px] leading-5 text-slate-600">
          <span class="font-medium text-slate-700">{{ source.label }}</span>
          <span v-if="source.factoryId"> · {{ source.factoryId }}</span>
          <span v-if="source.updatedAt"> · {{ source.updatedAt }}</span>
          <span v-if="source.links.length" class="ml-2 inline-flex flex-wrap gap-1.5">
            <a
              v-for="link in source.links"
              :key="`${link.route}:${link.label}`"
              :href="linkHref(link)"
              class="font-semibold text-sky-700 underline decoration-sky-300 underline-offset-2"
            >
              {{ link.label }}
            </a>
          </span>
        </li>
      </ul>
    </section>
  </div>
</template>
