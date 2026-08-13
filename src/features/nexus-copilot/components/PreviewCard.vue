<script setup lang="ts">
import { computed } from 'vue'
import { Clock3, FlaskConical, ShieldCheck, TriangleAlert } from '@lucide/vue'
import type { AIPreviewManifest } from '../renderers/preview'

const props = defineProps<{ manifest: AIPreviewManifest }>()

const status = computed(() => ({
  READY: { label: '可供复核', classes: 'bg-emerald-100 text-emerald-800' },
  STALE: { label: '来源已变化', classes: 'bg-amber-100 text-amber-900' },
  EXPIRED: { label: '已过期', classes: 'bg-amber-100 text-amber-900' },
  ACCESS_REVOKED: { label: '当前权限不可用', classes: 'bg-rose-100 text-rose-800' },
  INVALID: { label: '校验未通过', classes: 'bg-rose-100 text-rose-800' },
}[props.manifest.status]))
</script>

<template>
  <section class="mt-2 space-y-2 rounded-xl border border-violet-200 bg-violet-50/60 p-3 text-[11px] text-slate-700" data-preview-card>
    <header class="flex flex-wrap items-start justify-between gap-2">
      <div>
        <strong class="flex items-center gap-1.5 text-xs text-slate-950"><FlaskConical class="size-3.5 text-violet-700" aria-hidden="true" />Simulation / Preview</strong>
        <p class="mt-1 font-mono text-[10px] text-slate-500">{{ manifest.preview_type }} · {{ manifest.preview_id }}</p>
      </div>
      <span class="rounded-full px-2 py-1 font-bold" :class="status.classes">{{ status.label }}</span>
    </header>

    <div class="grid gap-2 sm:grid-cols-2">
      <div class="rounded-lg border border-violet-100 bg-white p-2">
        <p class="flex items-center gap-1 font-bold text-violet-800"><Clock3 class="size-3.5" aria-hidden="true" />有效期</p>
        <p class="mt-1 break-all">{{ manifest.created_at }} → {{ manifest.expires_at }}</p>
      </div>
      <div class="rounded-lg border border-violet-100 bg-white p-2">
        <p class="font-bold text-violet-800">来源与权限</p>
        <p class="mt-1">厂区 {{ manifest.factory_id }} · {{ manifest.deterministic_service ? '确定性领域 Service' : '模型建议，需人工审核' }}</p>
      </div>
    </div>

    <dl class="grid gap-1 sm:grid-cols-2">
      <div v-for="assumption in manifest.assumptions" :key="assumption.key" class="rounded-lg border border-slate-200 bg-white px-2 py-1.5">
        <dt class="font-semibold text-slate-500">{{ assumption.label }}</dt><dd class="mt-0.5 font-medium text-slate-800">{{ assumption.value }}</dd>
      </div>
    </dl>

    <p v-if="manifest.status !== 'READY'" class="flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 p-2 text-amber-900">
      <TriangleAlert class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />此 Preview 不能继续创建有效 Action Proposal；请重新生成并复核。
    </p>
    <footer class="rounded-lg border border-emerald-200 bg-emerald-50 p-2 text-emerald-900">
      <p class="flex items-center gap-1.5 font-bold"><ShieldCheck class="size-3.5" aria-hidden="true" />没有执行正式业务写入</p>
      <p v-if="manifest.can_propose_action" class="mt-1">仅允许进入“创建 Proposal”流程，不代表已 Apply、Publish 或执行。</p>
      <p v-else class="mt-1">此结果不提供 Action 能力；后续导入、审批或 Apply 由独立领域流程决定。</p>
    </footer>
  </section>
</template>
