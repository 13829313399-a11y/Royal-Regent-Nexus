<script setup lang="ts">
import { computed } from 'vue'
import { ExternalLink } from '@lucide/vue'
import { RouterLink } from 'vue-router'
import type { AIBusinessResult, AISourceSummary } from '@/features/ai-assistant/types'
import { commercialResultView } from '../commercialResultAdapter'
import PagedResultList from '../PagedResultList.vue'
import ResultFrame from '../ResultFrame.vue'

const props = defineProps<{ result: AIBusinessResult; sources: AISourceSummary[] }>()
const view = computed(() => commercialResultView(props.result))
</script>

<template>
  <ResultFrame :result="result">
    <template v-if="view">
      <p v-if="view.notice" class="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-[11px] font-medium text-amber-900">
        {{ view.notice }}
      </p>
      <p class="mt-2 rounded-lg border border-sky-200 bg-white px-2.5 py-2 text-[11px] text-slate-600">
        {{ view.summary }}
      </p>
      <PagedResultList :items="view.items" :total="view.total" :offset="view.offset" :page-size="5" class="mt-2">
        <template #default="{ item }">
          <article class="rounded-lg border border-sky-200 bg-white p-2.5">
            <div class="flex flex-wrap items-start justify-between gap-2">
              <div class="min-w-0">
                <p class="break-words text-xs font-bold text-slate-900">{{ item.title }}</p>
                <p class="mt-0.5 break-words text-[11px] text-slate-600">{{ item.description }}</p>
              </div>
              <span v-if="item.status" class="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-800">{{ item.status }}</span>
            </div>
            <p class="mt-1 break-words text-[10px] text-slate-500">{{ item.meta }}</p>
            <RouterLink
              v-if="item.to"
              :to="item.to"
              class="mt-2 inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-700 ring-1 ring-inset ring-sky-200 hover:bg-sky-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
            >
              {{ item.actionLabel }}
              <ExternalLink class="size-3" aria-hidden="true" />
            </RouterLink>
          </article>
        </template>
        <template #empty>
          <p class="rounded-lg border border-dashed border-slate-300 bg-white p-3 text-center text-[11px] text-slate-500">{{ view.emptyLabel }}</p>
        </template>
      </PagedResultList>
    </template>
    <template #technical>
      <p v-if="view" class="mt-1">limit {{ view.limit }} · offset {{ view.offset }} · returned {{ view.returned }} · total {{ view.total }}</p>
    </template>
  </ResultFrame>
</template>
