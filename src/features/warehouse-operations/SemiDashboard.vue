<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { PackageCheck, PackageOpen, Truck, TriangleAlert } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import WarehouseDashboard from '@/features/warehouse-foundation/WarehouseDashboard.vue'
import WarehouseTodoPanel from '@/features/warehouse-foundation/WarehouseTodoPanel.vue'
import { warehouseOperationsApi, type WarehouseOperationsWorkspace } from '@/api/warehouseOperations'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { WAREHOUSE_FACTORY, WAREHOUSE_HOME } from './navigation'
import { pendingHandoffQuantity } from './operations'

const route = useRoute()
const auth = useAuthStore()
const workspace = ref<WarehouseOperationsWorkspace>()
const error = ref('')
const loading = ref(false)
const updatedAt = ref('')
let generation = 0

function link(section: string, view: string, query: Record<string, string> = {}) {
  return { path: `${WAREHOUSE_HOME}/semi-finished-warehouse/${section}`, query: { factory: WAREHOUSE_FACTORY, view, ...query } }
}

const orderRows = computed(() => {
  if (!workspace.value?.order_progress) return undefined
  const releases = new Map(workspace.value.documents.filter(row => row.kind === 'SEMI_RELEASE' && !row.reversed).map(row => [row.id, row]))
  return workspace.value.order_progress.flatMap(progress => {
    const release = releases.get(progress.release_id)
    if (!release) return []
    const { item_name, item_code, production_no, part, label_code, due_date, unit } = release.data
    return [{
      id: release.id, title: item_name || item_code, context: [production_no, part, label_code && `布标 ${label_code}`].filter(Boolean).join(' · '),
      unit, dueDate: due_date || '', pending: progress.pending_receipt, extra: progress.extra_received,
    }]
  })
})

const handoffRows = computed(() => {
  if (!workspace.value) return undefined
  const tasks = new Map(workspace.value.documents.filter(row => row.kind === 'TASK').map(row => [row.id, row.data.due_date]))
  return workspace.value.documents.flatMap(row => {
    const pending = pendingHandoffQuantity(row)
    if (!pending) return []
    const processing = row.kind === 'PROCESS_SEND'
    const { item_name, item_code, source_no, production_no, counterparty, unit, task_id } = row.data
    const dueDate = processing ? tasks.get(task_id) : undefined
    return [{
      id: row.id, processing, title: item_name || row.batch_snapshot?.item_name || item_code,
      context: [production_no, counterparty, source_no || row.id].filter(Boolean).join(' · '),
      quantity: `${processing ? '在外' : '待签'} ${pending} ${unit || row.batch_snapshot?.unit || ''}`,
      date: dueDate ? `应回 ${dueDate}` : `发出 ${row.business_date}`, priority: dueDate || row.business_date,
      to: link('inventory', processing ? 'processing' : 'packaging', { followup: 'pending', record: row.id }),
    }]
  }).sort((a, b) => a.priority.localeCompare(b.priority))
})

const releaseError = computed(() => workspace.value && !workspace.value.order_progress ? '放产进度不可用，请核对服务版本。' : '')
const panels = computed(() => [
  {
    title: '待收货', icon: PackageOpen, unit: '项', action: '查看明细', destination: link('receipts', 'pending'),
    empty: '当前没有待收的放产明细。', error: releaseError.value,
    rows: orderRows.value?.filter(row => Number(row.pending) > 0).sort((a, b) => (a.dueDate || '9999').localeCompare(b.dueDate || '9999')).map(row => ({
      ...row, quantity: `待收 ${row.pending} ${row.unit}`, date: row.dueDate ? `应收 ${row.dueDate}` : undefined,
      to: link('receipts', 'pending', { release: row.id }),
    })),
  },
  {
    title: '加工在外', icon: Truck, unit: '笔', action: '查看发出单', destination: link('inventory', 'processing', { followup: 'pending' }),
    empty: '当前没有待回的加工发出单。', rows: handoffRows.value?.filter(row => row.processing),
  },
  {
    title: '包装待签收', icon: PackageCheck, unit: '笔', action: '查看交接单', destination: link('inventory', 'packaging', { followup: 'pending' }),
    empty: '当前没有待签收的包装交接单。', rows: handoffRows.value?.filter(row => !row.processing),
  },
  {
    title: '实收超计划', icon: TriangleAlert, unit: '项', action: '核对实收', attention: true,
    destination: link('orders', 'progress', { receipt_progress: 'extra' }), empty: '当前没有实收超计划的放产明细。', error: releaseError.value,
    rows: orderRows.value?.filter(row => Number(row.extra) > 0).map(row => ({
      ...row, quantity: `超收 ${row.extra} ${row.unit}`, to: link('orders', 'progress', { receipt_progress: 'extra', release: row.id }),
    })),
  },
])

async function load(reset = false) {
  const ticket = ++generation
  if (reset) { workspace.value = undefined; updatedAt.value = '' }
  error.value = ''
  if (route.query.factory !== WAREHOUSE_FACTORY) { loading.value = false; return }
  loading.value = true
  try {
    const result = await warehouseOperationsApi.workspace('semi', false, true)
    if (ticket !== generation) return
    workspace.value = result
    updatedAt.value = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit' }).format(new Date())
  } catch (failure) {
    if (ticket !== generation) return
    workspace.value = undefined; updatedAt.value = ''; error.value = getApiErrorMessage(failure)
  } finally { if (ticket === generation) loading.value = false }
}

function refreshWhenVisible() {
  if (!loading.value && document.visibilityState === 'visible') void load()
}
watch(() => [route.query.factory, auth.currentUser?.id, auth.authorizationVersion], () => load(true), { immediate: true })
let timer: number | undefined
onMounted(() => {
  window.addEventListener('focus', refreshWhenVisible)
  document.addEventListener('visibilitychange', refreshWhenVisible)
  timer = window.setInterval(refreshWhenVisible, 60_000)
})
onBeforeUnmount(() => {
  generation++
  window.clearInterval(timer)
  window.removeEventListener('focus', refreshWhenVisible)
  document.removeEventListener('visibilitychange', refreshWhenVisible)
})
</script>

<template>
  <WarehouseDashboard class="semi-dashboard" subtitle="华康 C · 半成品仓" :loading="loading" :updated-at="updatedAt" :error="error" @refresh="load()">
    <template #primary><Button as-child><RouterLink :to="link('orders', 'progress')">订单进度</RouterLink></Button></template>
    <template #todos><WarehouseTodoPanel v-for="panel in panels" :key="panel.title" v-bind="panel" /></template>
    <slot />
  </WarehouseDashboard>
</template>
