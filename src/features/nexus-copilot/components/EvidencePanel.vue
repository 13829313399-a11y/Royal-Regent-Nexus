<script setup lang="ts">
import { computed } from 'vue'
import { FileSearch, RefreshCcw, ShieldAlert, ShieldCheck } from '@lucide/vue'

const props = defineProps<{
  evidence: readonly Readonly<Record<string, unknown>>[]
  inaccessible?: boolean
  loading?: boolean
  headingId?: string
}>()

const emit = defineEmits<{
  refresh: []
}>()

interface SafeEvidence {
  id: string
  sourceName: string
  sourceLevel: string
  factoryId: string
  asOf: string
  entityLabel: string
  truncated: boolean
}

function safeText(value: unknown, max = 160) {
  return typeof value === 'string' ? value.trim().slice(0, max) : ''
}

const safeEvidence = computed<SafeEvidence[]>(() => {
  if (props.inaccessible) return []
  return props.evidence.flatMap((source) => {
    const id = safeText(source.evidence_id ?? source.evidenceId)
    const sourceName = safeText(source.source_name ?? source.sourceName)
    const sourceLevel = safeText(source.source_level ?? source.sourceLevel)
    const asOf = safeText(source.as_of ?? source.asOf)
    const accessPolicy = safeText(source.access_policy ?? source.accessPolicy)
    if (!id.startsWith('ev:') || !sourceName || !sourceLevel || !asOf || accessPolicy !== 'REAUTHORIZE_ON_OPEN') {
      return []
    }
    const entityType = safeText(source.entity_type ?? source.entityType)
    const entityId = safeText(source.entity_id ?? source.entityId)
    return [{
      id,
      sourceName,
      sourceLevel,
      factoryId: safeText(source.factory_id ?? source.factoryId, 64),
      asOf,
      entityLabel: [entityType, entityId].filter(Boolean).join(' · '),
      truncated: source.truncated === true,
    }]
  })
})
</script>

<template>
  <aside class="flex min-h-0 flex-col border-l border-slate-200 bg-white" :aria-labelledby="headingId ?? 'evidence-panel-title'">
    <header class="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
      <div>
        <h2 :id="headingId ?? 'evidence-panel-title'" class="text-sm font-bold text-slate-900">证据</h2>
        <p class="mt-0.5 text-[11px] text-slate-500">每次打开都按当前权限重新验证</p>
      </div>
      <button
        type="button"
        class="flex size-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:opacity-50"
        aria-label="重新验证证据访问权限"
        :disabled="loading"
        @click="emit('refresh')"
      >
        <RefreshCcw class="size-3.5" :class="loading ? 'animate-spin' : ''" aria-hidden="true" />
      </button>
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto p-3">
      <div
        v-if="inaccessible"
        data-evidence-inaccessible
        class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900"
        role="status"
      >
        <ShieldAlert class="mb-2 size-5" aria-hidden="true" />
        证据当前不可访问。权限可能已变化，页面不会显示先前缓存的详情。
      </div>
      <div v-else-if="loading" class="py-8 text-center text-xs text-slate-500" role="status">正在重新验证…</div>
      <div v-else-if="!safeEvidence.length" class="py-8 text-center">
        <FileSearch class="mx-auto size-6 text-slate-300" aria-hidden="true" />
        <p class="mt-2 text-xs leading-5 text-slate-500">当前会话没有可访问的证据引用。权限变化后不会沿用缓存详情。</p>
      </div>
      <ul v-else class="space-y-2">
        <li v-for="item in safeEvidence" :key="item.id" class="rounded-xl border border-slate-200 p-3">
          <div class="flex items-start gap-2">
            <ShieldCheck class="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />
            <div class="min-w-0">
              <p class="truncate text-xs font-bold text-slate-900">{{ item.sourceName }}</p>
              <p class="mt-1 break-words text-[11px] leading-4 text-slate-500">{{ item.sourceLevel }}</p>
            </div>
          </div>
          <dl class="mt-2 space-y-1 text-[11px] leading-4 text-slate-600">
            <div v-if="item.factoryId" class="flex gap-2"><dt>厂区</dt><dd>{{ item.factoryId }}</dd></div>
            <div class="flex gap-2"><dt>时点</dt><dd>{{ item.asOf }}</dd></div>
            <div v-if="item.entityLabel" class="flex gap-2"><dt>对象</dt><dd class="break-all">{{ item.entityLabel }}</dd></div>
            <div class="flex gap-2"><dt>完整性</dt><dd>{{ item.truncated ? '已截断' : '未截断' }}</dd></div>
          </dl>
        </li>
      </ul>
    </div>
  </aside>
</template>
