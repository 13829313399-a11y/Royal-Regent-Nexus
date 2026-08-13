<script setup lang="ts">
import { AlertTriangle, FileSpreadsheet, Search, Upload } from '@lucide/vue'
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import type { Tone } from '@/data/enterpriseMock'
import { qcInspectionApi, type QcScheduleImport } from '@/api/qcInspection'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { useQcInspectionWorkspace } from './context'
import { getApiErrorMessage } from '@/lib/http'

const context = useQcInspectionWorkspace()
const searchQuery = ref('')
const selectedFile = ref<File | null>(null)
const previewBatch = ref<QcScheduleImport | null>(null)
const decisions = ref<Record<string, string>>({})
const targetOrderIds = ref<Record<string, string>>({})
const actionError = ref('')
const actionMessage = ref('')
const previewing = ref(false)
const confirming = ref(false)

const summary = computed(() => context.workspace.value?.summary ?? {
  total_orders: 0,
  pending_orders: 0,
  completed_orders: 0,
  problem_orders: 0,
})
const orders = computed(() => context.workspace.value?.orders ?? [])
const filteredOrders = computed(() => {
  const query = searchQuery.value.trim().toLocaleLowerCase()
  if (!query) return orders.value
  return orders.value.filter((order) => [
    order.inspection_no,
    order.customer_name,
    order.sales_contract_no,
    order.customer_po_no,
    order.customer_item_no,
  ].some((value) => String(value ?? '').toLocaleLowerCase().includes(query)))
})
const changes = computed(() => (previewBatch.value?.rows ?? []).filter((row) => row.decision_status !== 'UNCHANGED'))
const decisionsComplete = computed(() => changes.value.length > 0 && changes.value.every((change) => {
  const decision = decisions.value[change.id]
  return Boolean(decision) && !(
    change.match_status === 'MULTIPLE_MATCHES'
    && ['UPDATE', 'KEEP'].includes(decision)
    && !targetOrderIds.value[change.id]
  )
}))

const resultLabels: Record<string, string> = {
  PENDING: '待验货',
  PASS: 'PASS',
  FAIL: '不通过',
  REJECTED: '退货',
  CONDITIONAL_PASS: '有条件通过',
  CANCELLED: '已取消',
}
const resultTones: Record<string, Tone> = {
  PENDING: 'amber',
  PASS: 'green',
  FAIL: 'red',
  REJECTED: 'red',
  CONDITIONAL_PASS: 'blue',
  CANCELLED: 'slate',
}

function candidateLabel(change: QcScheduleImport['rows'][number], candidateId: string) {
  const candidate = change.candidate_orders?.find((item) => item.id === candidateId)
  if (!candidate) return candidateId
  return [
    candidate.inspection_no || candidate.id,
    `PO ${candidate.customer_po_no || '—'}`,
    candidate.planned_inspection_date || candidate.week_key || '日期待补',
    `数量 ${candidate.quantity}`,
  ].join(' · ')
}

function onFileChange(event: Event) {
  const files = (event.target as HTMLInputElement).files
  selectedFile.value = files?.[0] ?? null
  previewBatch.value = null
  decisions.value = {}
  targetOrderIds.value = {}
  actionError.value = ''
  actionMessage.value = ''
}

async function previewImport() {
  if (!selectedFile.value || !context.canScheduleWrite.value) return
  previewing.value = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    previewBatch.value = await qcInspectionApi.previewScheduleImport(
      selectedFile.value,
      context.factoryId.value,
      context.weekKey.value,
    )
    decisions.value = {}
    targetOrderIds.value = {}
    actionMessage.value = changes.value.length
      ? '预览已生成。请逐项确认更新或保留，系统不会静默覆盖。'
      : '预览完成，未发现需要确认的排期变化。'
  } catch (error) {
    actionError.value = getApiErrorMessage(error)
  } finally {
    previewing.value = false
  }
}

async function confirmImport() {
  if (!previewBatch.value || !decisionsComplete.value || !context.canScheduleWrite.value) return
  confirming.value = true
  actionError.value = ''
  try {
    await qcInspectionApi.confirmScheduleImport(
      previewBatch.value.id,
      context.factoryId.value,
      previewBatch.value.revision,
      changes.value.map((change) => ({
        row_id: change.id,
        action: decisions.value[change.id]! as 'UPDATE' | 'KEEP' | 'CREATE' | 'SKIP',
        target_order_id: targetOrderIds.value[change.id] || undefined,
      })),
    )
    previewBatch.value = null
    selectedFile.value = null
    decisions.value = {}
    targetOrderIds.value = {}
    actionMessage.value = '排期变化已按本次确认结果处理。'
    await context.refresh()
  } catch (error) {
    actionError.value = getApiErrorMessage(error)
  } finally {
    confirming.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <article v-for="metric in [
        { label: '本周验货主单', value: summary.total_orders, tone: 'text-slate-950' },
        { label: '待验货', value: summary.pending_orders, tone: 'text-amber-700' },
        { label: '已完成', value: summary.completed_orders, tone: 'text-emerald-700' },
        { label: '涉及问题', value: summary.problem_orders, tone: 'text-red-700' },
      ]" :key="metric.label" class="enterprise-panel rounded-xl p-5">
        <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">{{ metric.label }}</p>
        <p class="mt-2 text-3xl font-semibold" :class="metric.tone">{{ metric.value }}</p>
        <p class="mt-2 text-xs text-slate-500">{{ context.factoryName.value }} · {{ context.weekKey.value }}</p>
      </article>
    </div>

    <SectionPanel title="生产排期导入" subtitle="先生成差异预览，再由 QC 逐项选择更新或保留；合同号与货号只用于候选匹配。">
      <div v-if="!context.canScheduleWrite.value" class="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
        当前为只读访问，不能导入或确认排期。
      </div>
      <div v-else class="space-y-5">
        <div class="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
          <label class="block space-y-2">
            <span class="text-sm font-semibold text-slate-800">选择本周生产排期表</span>
            <input
              type="file"
              accept=".xls,.xlsx"
              class="block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-teal-50 file:px-3 file:py-1.5 file:font-semibold file:text-teal-800"
              @change="onFileChange"
            >
          </label>
          <Button type="button" :disabled="!selectedFile || previewing" @click="previewImport">
            <Upload class="size-4" aria-hidden="true" />
            {{ previewing ? '正在生成预览…' : '生成差异预览' }}
          </Button>
        </div>

        <p v-if="actionError" role="alert" class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{{ actionError }}</p>
        <p v-if="actionMessage" class="rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800">{{ actionMessage }}</p>

        <div v-if="previewBatch && changes.length" class="overflow-hidden rounded-xl border border-slate-200">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3">
            <div>
              <p class="font-semibold text-slate-900">排期变更确认 · {{ previewBatch.source_file_name }}</p>
              <p class="mt-1 text-xs text-slate-500">共 {{ changes.length }} 项；全部完成选择后才能确认。</p>
            </div>
            <Button type="button" :disabled="!decisionsComplete || confirming" @click="confirmImport">
              {{ confirming ? '确认中…' : '确认本批次' }}
            </Button>
          </div>
          <div class="divide-y divide-slate-100">
            <article v-for="(change, index) in changes" :key="change.id" class="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_220px] lg:items-center">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="text-xs font-bold text-teal-700">第 {{ index + 1 }} 项 / 共 {{ changes.length }} 项</span>
                  <StatusPill :label="change.match_status" :tone="change.validation_errors.length ? 'red' : 'blue'" compact />
                </div>
                <p class="mt-2 font-semibold text-slate-950">{{ change.sales_contract_no }} · {{ change.customer_item_no }}</p>
                <p v-if="change.customer_name" class="mt-1 text-sm text-slate-500">{{ change.customer_name }}</p>
                <div v-if="change.changes.length" class="mt-3 grid gap-2 sm:grid-cols-2">
                  <div v-for="field in change.changes" :key="field.field" class="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-700">
                    <b>{{ field.field }}</b>：{{ field.old_value || '空' }} → {{ field.new_value || '空' }}
                  </div>
                </div>
                <p v-for="issue in change.validation_errors" :key="issue" class="mt-3 flex items-start gap-2 text-sm text-red-700">
                  <AlertTriangle class="mt-0.5 size-4 shrink-0" aria-hidden="true" />{{ issue }}
                </p>
              </div>
              <fieldset>
                <legend class="mb-2 text-xs font-semibold text-slate-600">QC 决策</legend>
                <select
                  v-if="change.match_status === 'MULTIPLE_MATCHES' && ['UPDATE', 'KEEP'].includes(decisions[change.id] || '')"
                  v-model="targetOrderIds[change.id]"
                  class="mb-2 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-500"
                  aria-label="选择要更新的验货主单"
                >
                  <option value="">请选择验货主单</option>
                  <option v-for="candidateId in change.candidate_order_ids" :key="candidateId" :value="candidateId">{{ candidateLabel(change, candidateId) }}</option>
                </select>
                <div class="grid grid-cols-2 gap-2">
                  <label
                    v-for="choice in change.match_status === 'NEW'
                      ? [{ value: 'CREATE', label: '创建主单' }, { value: 'SKIP', label: '跳过' }]
                      : change.match_status === 'INVALID'
                        ? [{ value: 'SKIP', label: '确认跳过' }]
                        : change.match_status === 'MULTIPLE_MATCHES'
                           ? [{ value: 'UPDATE', label: '选择更新' }, { value: 'KEEP', label: '选择保留' }, { value: 'SKIP', label: '跳过' }]
                          : [{ value: 'UPDATE', label: '确认更新' }, { value: 'KEEP', label: '跳过保留' }]"
                    :key="choice.value"
                    class="cursor-pointer"
                  >
                    <input v-model="decisions[change.id]" type="radio" :name="`decision-${change.id}`" :value="choice.value" class="peer sr-only">
                    <span class="flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-sm font-semibold text-slate-700 peer-checked:border-teal-600 peer-checked:bg-teal-50 peer-checked:text-teal-800">{{ choice.label }}</span>
                  </label>
                </div>
              </fieldset>
            </article>
          </div>
        </div>
      </div>
    </SectionPanel>

    <SectionPanel title="本周验货排期" subtitle="正式验货主单按系统验货单号区分；同一合同和货号可存在多次验货。">
      <template #action>
        <label class="relative block">
          <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input v-model="searchQuery" type="search" placeholder="合同号、PO、货号或客户" class="h-10 w-72 max-w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15">
        </label>
      </template>

      <div v-if="!filteredOrders.length" class="grid min-h-44 place-items-center rounded-xl border border-dashed border-slate-300 bg-slate-50/70 p-8 text-center">
        <div>
          <FileSpreadsheet class="mx-auto size-8 text-slate-400" aria-hidden="true" />
          <p class="mt-3 font-semibold text-slate-800">{{ orders.length ? '没有匹配的验货主单' : '当前周暂无验货主单' }}</p>
          <p class="mt-1 text-sm text-slate-500">可以导入生产排期，或由有权限的 QC 人员新增临时订单。</p>
        </div>
      </div>

      <div v-else class="overflow-x-auto rounded-xl border border-slate-200">
        <table class="min-w-full text-left text-sm">
          <thead class="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th class="px-4 py-3 font-semibold">验货单号</th>
              <th class="px-4 py-3 font-semibold">客户 / 合同</th>
              <th class="px-4 py-3 font-semibold">PO / 客户货号</th>
              <th class="px-4 py-3 font-semibold">验货期</th>
              <th class="px-4 py-3 font-semibold">结果</th>
              <th class="px-4 py-3 text-right font-semibold">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 bg-white">
            <tr v-for="order in filteredOrders" :key="order.id" class="hover:bg-slate-50/70">
              <td class="whitespace-nowrap px-4 py-3 font-semibold text-slate-950">{{ order.inspection_no || order.id }}</td>
              <td class="px-4 py-3"><b class="text-slate-900">{{ order.customer_name }}</b><span class="mt-1 block text-xs text-slate-500">{{ order.sales_contract_no }}</span></td>
              <td class="px-4 py-3"><span>{{ order.customer_po_no }}</span><span class="mt-1 block text-xs text-slate-500">{{ order.customer_item_no }}</span></td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ order.planned_inspection_date }}</td>
              <td class="px-4 py-3"><StatusPill :label="resultLabels[order.inspection_result || 'PENDING'] || order.inspection_result || '待验货'" :tone="resultTones[order.inspection_result || 'PENDING'] || 'slate'" compact /></td>
              <td class="px-4 py-3 text-right">
                <RouterLink :to="{ name: 'qc-inspection-order-detail', params: { orderId: order.id }, query: { factory: context.factoryId.value, week: context.weekKey.value } }" class="font-semibold text-teal-700 hover:text-teal-900">查看主单</RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </SectionPanel>
  </div>
</template>
