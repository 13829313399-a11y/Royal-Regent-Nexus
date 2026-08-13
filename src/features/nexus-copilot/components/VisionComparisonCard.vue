<script setup lang="ts">
import { computed } from 'vue'
import { CheckCircle2, Eye, GitCompareArrows, ShieldCheck, TriangleAlert } from '@lucide/vue'
import type { VisionTaskResult } from '../renderers/visionComparison'

const props = defineProps<{
  result: VisionTaskResult
  comparing?: boolean
}>()

const emit = defineEmits<{
  compare: []
}>()

const isObservation = computed(() => props.result.result_type === 'vision.injection_backlog_observation.v1')
const observation = computed(() => props.result.observation)
const comparison = computed(() => props.result.result_type === 'vision.injection_backlog_comparison.v1' ? props.result : null)

function percent(value: number) {
  return `${Math.round(value * 100)}%`
}

const statusLabels = {
  MATCHED: '一致',
  DIFFERENT: '有差异',
  IMAGE_ONLY: '仅图片可见',
  FORMAL_ONLY: '仅正式数据可见',
  UNCONFIRMED: '无法确认',
} as const
</script>

<template>
  <section class="mt-3 space-y-3 rounded-xl border border-indigo-200 bg-indigo-50/60 p-3 text-xs text-slate-800" data-vision-comparison>
    <header class="flex items-start justify-between gap-3">
      <div>
        <strong class="flex items-center gap-2 text-sm text-slate-950">
          <Eye class="size-4 text-indigo-700" aria-hidden="true" />
          {{ isObservation ? '图片 Observation' : '图片与正式 Backlog 核对' }}
        </strong>
        <p class="mt-1 text-slate-600">厂区 {{ result.factory_id }} · 图片内容始终标记为用户提供</p>
      </div>
      <span class="rounded-full bg-white px-2 py-1 font-bold text-indigo-700 ring-1 ring-indigo-200">无写入</span>
    </header>

    <div class="grid gap-2 sm:grid-cols-3">
      <div class="rounded-lg border border-indigo-100 bg-white p-2">
        <p class="font-bold text-indigo-800">USER_PROVIDED</p>
        <p class="mt-1">{{ observation.rows.length }} 行 · 总体置信度 {{ percent(observation.overall_confidence) }}</p>
      </div>
      <div v-if="comparison" class="rounded-lg border border-emerald-100 bg-white p-2">
        <p class="font-bold text-emerald-800">FORMAL_DOMAIN_SERVICE</p>
        <p class="mt-1">查询时点 {{ comparison.formal_backlog.as_of }}</p>
      </div>
      <div class="rounded-lg border border-slate-200 bg-white p-2">
        <p class="font-bold text-slate-700">安全边界</p>
        <p class="mt-1">图片阶段 Tool=0；图片文字不构成查询参数</p>
      </div>
    </div>

    <div v-if="observation.instructions_detected" class="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-amber-900">
      <TriangleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      图片中检测到疑似指令文本，已按不可信数据忽略。
    </div>

    <div class="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table class="min-w-full text-left text-[11px]">
        <thead class="bg-slate-50 text-slate-600">
          <tr><th class="px-2 py-1.5">行</th><th class="px-2 py-1.5">订单号</th><th class="px-2 py-1.5">料号</th><th class="px-2 py-1.5">模号</th><th class="px-2 py-1.5">交期</th><th class="px-2 py-1.5">置信度</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in observation.rows" :key="row.row_index" class="border-t border-slate-100">
            <td class="px-2 py-1.5">{{ row.row_index }}</td><td class="px-2 py-1.5 font-mono">{{ row.order_no ?? '无法确认' }}</td><td class="px-2 py-1.5 font-mono">{{ row.item_no ?? '无法确认' }}</td><td class="px-2 py-1.5">{{ row.mold_no ?? '—' }}</td><td class="px-2 py-1.5">{{ row.delivery_due_date ?? '—' }}</td><td class="px-2 py-1.5">{{ percent(row.row_confidence) }}</td>
          </tr>
          <tr v-if="!observation.rows.length"><td colspan="6" class="px-2 py-3 text-center text-slate-500">没有形成可核对的结构化行</td></tr>
        </tbody>
      </table>
    </div>

    <template v-if="comparison">
      <div class="flex flex-wrap gap-2">
        <span class="rounded-full bg-emerald-100 px-2 py-1 text-emerald-800">一致 {{ comparison.matched_count }}</span>
        <span class="rounded-full bg-rose-100 px-2 py-1 text-rose-800">差异 {{ comparison.different_count }}</span>
        <span class="rounded-full bg-amber-100 px-2 py-1 text-amber-800">无法确认 {{ comparison.unconfirmed_count }}</span>
        <span class="rounded-full bg-slate-100 px-2 py-1 text-slate-700">图片独有 {{ comparison.image_only_count }}</span>
        <span class="rounded-full bg-sky-100 px-2 py-1 text-sky-800">正式独有 {{ comparison.formal_only_count }}</span>
      </div>
      <p v-if="comparison.formal_backlog.truncated" class="rounded-lg border border-amber-200 bg-amber-50 p-2 text-amber-900">
        正式 Backlog 已截断：本次返回 {{ comparison.formal_backlog.returned }}/{{ comparison.formal_backlog.total }}，未返回部分不能判定为不存在。
      </p>
      <ol class="space-y-1.5">
        <li v-for="(row, index) in comparison.comparison_rows" :key="`${row.formal?.order_id ?? row.observation?.row_index ?? index}-${row.status}`" class="rounded-lg border border-slate-200 bg-white p-2">
          <div class="flex items-center justify-between gap-2">
            <span class="font-mono">{{ row.observation?.order_no ?? row.formal?.order_no ?? '未知订单' }} / {{ row.observation?.item_no ?? row.formal?.item_no ?? '未知料号' }}</span>
            <strong :class="row.status === 'MATCHED' ? 'text-emerald-700' : row.status === 'DIFFERENT' ? 'text-rose-700' : 'text-amber-700'">{{ statusLabels[row.status] }}</strong>
          </div>
          <p v-if="row.field_comparisons.length" class="mt-1 text-slate-500">
            {{ row.field_comparisons.map(item => `${item.field}:${item.status}`).join(' · ') }}
          </p>
        </li>
      </ol>
    </template>

    <footer class="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-2 text-emerald-900">
      <p class="flex items-center gap-1.5 font-semibold"><CheckCircle2 class="size-4" aria-hidden="true" />没有修改任何业务数据</p>
      <button v-if="isObservation" type="button" class="inline-flex items-center gap-1.5 rounded-lg bg-indigo-700 px-3 py-2 font-bold text-white disabled:bg-slate-400" :disabled="comparing" @click="emit('compare')">
        <GitCompareArrows class="size-4" aria-hidden="true" />{{ comparing ? '正在创建核对任务…' : '同意读取并比较正式 Backlog' }}
      </button>
      <p v-else class="flex items-center gap-1.5"><ShieldCheck class="size-4" aria-hidden="true" />正式数据已在 Stage B 重新鉴权并即时读取</p>
    </footer>
  </section>
</template>
