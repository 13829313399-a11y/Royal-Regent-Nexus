<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ClipboardCheck, Plus, Upload } from '@lucide/vue'
import { qcInspectionApi, type QcInspectionOrder } from '@/api/qcInspection'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { useQcInspectionWorkspace } from './context'
import { effectiveInspectionDate, isImportedPendingInspection, scheduleStatus } from './schedule'
import QcImportPanel from './QcImportPanel.vue'
import QcManualOrderDialog from './QcManualOrderDialog.vue'

const context = useQcInspectionWorkspace()
const route = useRoute()
const router = useRouter()
const orders = ref<QcInspectionOrder[]>([])
const loading = ref(false)
const error = ref('')
const saved = ref<QcInspectionOrder | null>(null)
const showImport = ref(false)
const showManual = ref(false)
const customers = computed(() => [...new Set(orders.value.map(order => order.customer_name))].sort())
const pending = computed(() => orders.value.filter(isImportedPendingInspection))
const metrics = computed(() => [
  { label: '已导入待验', value: pending.value.length },
  { label: '其中待安排日期', value: pending.value.filter(order => !effectiveInspectionDate(order)).length },
  { label: '临时单待验', value: orders.value.filter(order => order.source_type === 'MANUAL' && ['pending', 'unplanned'].includes(scheduleStatus(order))).length },
  { label: '已验货记录', value: orders.value.filter(order => scheduleStatus(order) === 'completed').length },
])
function target(name: string) { return { name, query: { factory: context.factoryId.value, week: context.weekKey.value } } }
function orderLink(order: QcInspectionOrder) { return { name: 'qc-inspection-order-detail', params: { orderId: order.id }, query: { factory: context.factoryId.value, week: order.week_key || context.weekKey.value } } }
let loadSequence = 0
async function load() {
  const sequence = ++loadSequence
  loading.value = true; error.value = ''
  try {
    const result = await qcInspectionApi.listOrders(context.factoryId.value)
    if (sequence === loadSequence) orders.value = result
  } catch (cause) { if (sequence === loadSequence) error.value = getApiErrorMessage(cause) }
  finally { if (sequence === loadSequence) loading.value = false }
}
async function manualSaved(order: QcInspectionOrder) {
  showManual.value = false; saved.value = order
  orders.value = [order, ...orders.value.filter(item => item.id !== order.id)]
  await context.refresh()
}
watch(() => context.workspace.value, () => { void load() })
onMounted(() => {
  void load()
  if (route.query.add === '1') {
    showManual.value = context.canOrderWrite.value
    const query = { ...route.query }; delete query.add
    void router.replace({ query })
  }
})
</script>

<template>
  <div class="space-y-5">
    <section class="qc-card">
      <div class="qc-section-heading"><div><p class="qc-eyebrow">INSPECTION SCHEDULE</p><h2>验货总排期</h2><p class="qc-muted">导入生产排期或临时加单，进入独立排期明细表安排验货。</p></div><div class="flex flex-wrap gap-2"><Button v-if="context.canScheduleWrite.value" variant="outline" :aria-expanded="showImport" @click="showImport = !showImport"><Upload class="size-4" />{{ showImport ? '收起导入' : '导入生产排期' }}</Button><Button v-if="context.canOrderWrite.value" @click="showManual = true"><Plus class="size-4" />临时加单</Button></div></div>
      <p v-if="error" class="qc-error" role="alert">{{ error }} <button class="underline" @click="load">重新加载</button></p>
      <p v-if="loading" class="qc-muted" role="status">正在读取排期概况…</p>
      <div v-else-if="!error" class="qc-metrics"><div v-for="metric in metrics" :key="metric.label"><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong></div></div>
    </section>
    <section class="qc-card">
      <div class="qc-section-heading mb-0"><div><h2>排期明细</h2><p class="qc-muted">独立表格记录已导入且未完成验货的订单，支持按客户、日期和机构筛选。</p><p class="qc-muted">完成或取消验货后自动移出待验表，原记录保留。</p></div><Button as-child><RouterLink :to="target('qc-inspection-schedule-details')"><ClipboardCheck class="size-4" />打开排期明细</RouterLink></Button></div>
      <div class="mt-5 border-t border-slate-100 pt-4 text-sm text-slate-500">查看临时加单、已完成或已取消记录：<RouterLink :to="target('qc-inspection-order-records')" class="font-semibold text-teal-700">全部验货记录</RouterLink></div>
    </section>
    <QcImportPanel v-if="showImport" />
    <p v-if="saved" class="qc-notice" role="status">临时单 {{ saved.inspection_no }} 已保存，可在全部验货记录中查看。<RouterLink :to="orderLink(saved)" class="font-semibold underline">查看订单</RouterLink></p>
    <QcManualOrderDialog v-if="showManual && context.canOrderWrite.value" :customers="customers" :orders="orders" @close="showManual = false" @saved="manualSaved" />
  </div>
</template>
