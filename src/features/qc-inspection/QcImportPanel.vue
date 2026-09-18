<script setup lang="ts">
import { computed, ref } from 'vue'
import { qcInspectionApi, validateQcScheduleImportFile, type QcScheduleImport } from '@/api/qcInspection'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { useQcInspectionWorkspace } from './context'
import { effectiveInspectionDate, importAction, selectedImportDecisions, type ImportDecisionAction } from './schedule'

const emit = defineEmits<{ imported: [] }>()
const context = useQcInspectionWorkspace()
const file = ref<File | null>(null)
const batch = ref<QcScheduleImport | null>(null)
const selected = ref<string[]>([])
const targets = ref<Record<string, string>>({})
const actions = ref<Record<string, ImportDecisionAction>>({})
const customer = ref('')
const status = ref('')
const busy = ref(false)
const error = ref('')
const message = ref('')
const page = ref(1)
const rows = computed(() => batch.value?.rows ?? [])
const customers = computed(() => [...new Set(rows.value.map(row => row.customer_name))].sort())
const visible = computed(() => rows.value.filter(row => (!customer.value || row.customer_name === customer.value)
  && (!status.value || (status.value === 'PENDING' ? row.decision_status === 'PENDING' : row.match_status === status.value))))
const pageRows = computed(() => visible.value.slice((page.value - 1) * 30, page.value * 30))
const selectable = computed(() => visible.value.filter(row => importAction(row, targets.value[row.id], actions.value[row.id])))
const decisions = computed(() => selectedImportDecisions(rows.value, selected.value, targets.value, actions.value))
const pending = computed(() => rows.value.filter(row => row.decision_status === 'PENDING').length)
const newCount = computed(() => decisions.value.filter(row => row.action === 'CREATE').length)
const updateCount = computed(() => decisions.value.filter(row => row.action === 'UPDATE').length)
const keepCount = computed(() => decisions.value.filter(row => row.action === 'KEEP').length)
const skipCount = computed(() => decisions.value.filter(row => row.action === 'SKIP').length)
const allSelected = computed(() => selectable.value.length > 0 && selectable.value.every(row => selected.value.includes(row.id)))
const recent = computed(() => context.workspace.value?.imports ?? [])
const labels: Record<string, string> = { NEW: '新增', EXACT: '更新候选', MULTIPLE_MATCHES: '需指定订单', INVALID: '待修正', UNCHANGED: '无变化', CREATE: '已新增', UPDATE: '已更新', KEEP: '已保留', SKIP: '已跳过' }
function toggleAll() {
  const ids = new Set(selectable.value.map(row => row.id))
  selected.value = allSelected.value ? selected.value.filter(id => !ids.has(id)) : [...new Set([...selected.value, ...ids])]
}
function chooseFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  error.value = file.value ? validateQcScheduleImportFile(file.value) : ''
  if (error.value) file.value = null
}
function resetSelection() { selected.value = []; targets.value = {}; actions.value = {}; page.value = 1; customer.value = ''; status.value = '' }
async function preview() {
  if (!file.value || busy.value || !context.canScheduleWrite.value) return
  busy.value = true; error.value = ''; message.value = ''
  try {
    batch.value = await qcInspectionApi.previewScheduleImport(file.value, context.factoryId.value, context.weekKey.value)
    resetSelection()
    await context.refresh()
  } catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
async function resume(id: string) {
  if (busy.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { batch.value = await qcInspectionApi.getScheduleImport(id, context.factoryId.value); resetSelection() }
  catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
async function confirm() {
  if (!batch.value || !decisions.value.length || busy.value || !context.canScheduleWrite.value) return
  busy.value = true; error.value = ''; message.value = ''
  const submission = decisions.value
  const count = submission.length
  let processed = 0
  try {
    // The API accepts at most 1000 decisions per request. Each response supplies the next revision.
    for (let offset = 0; offset < submission.length; offset += 1000) {
      const part = submission.slice(offset, offset + 1000)
      batch.value = await qcInspectionApi.confirmScheduleImport(batch.value.id, context.factoryId.value, batch.value.revision, part)
      processed += part.length
      message.value = `已处理 ${processed} / ${count} 条，请稍候…`
    }
    selected.value = []
    message.value = `已处理 ${count} 条，剩余 ${pending.value} 条待确认。未勾选的订单继续保留。`
    emit('imported')
    await context.refresh()
  } catch (cause) {
    error.value = `本次已确认处理 ${processed} 条。${getApiErrorMessage(cause)}。请重新读取批次，核对已处理记录后再继续。`
    // Reload after uncertain responses or revision conflicts; never blindly submit a stale selection.
    try { batch.value = await qcInspectionApi.getScheduleImport(batch.value.id, context.factoryId.value); selected.value = [] } catch { /* Keep the explicit reload action available. */ }
    message.value = ''
    await context.refresh()
  } finally { busy.value = false }
}
</script>

<template>
  <section class="qc-card" aria-labelledby="qc-import-title">
    <div class="qc-section-heading"><div><h2 id="qc-import-title">导入未走货订单</h2><p class="qc-muted">仅识别「正单评审表」中「取消单」以上的正单，不按验货日期裁掉跨周订单。</p></div><span class="qc-badge">预览 → 勾选 → 确认</span></div>
    <div class="qc-toolbar"><label class="qc-field flex-1"><span>选择生产排期表（最大 35 MB）</span><input type="file" accept=".xls,.xlsx,.xlsm" :disabled="busy || !context.canScheduleWrite.value" @change="chooseFile"></label><Button :disabled="!file || busy || !context.canScheduleWrite.value" @click="preview">{{ busy ? '处理中…' : '生成差异预览' }}</Button></div>
    <div v-if="recent.length" class="qc-toolbar"><label class="qc-field flex-1"><span>继续处理本业务周的导入批次</span><select :value="batch?.id || ''" :disabled="busy" @change="resume(($event.target as HTMLSelectElement).value)"><option value="" disabled>选择已有批次</option><option v-for="item in recent" :key="item.id" :value="item.id">{{ item.source_file_name }} · {{ item.created_at }} · {{ item.row_count }} 条</option></select></label></div>
    <p v-if="error" class="qc-error" role="alert">{{ error }}</p><p v-if="message" class="qc-notice" role="status">{{ message }}</p>
    <template v-if="batch">
      <div class="qc-section-heading"><div><h3>{{ batch.source_file_name }}</h3><p class="qc-muted">识别 {{ rows.length }} 条 · 待确认 {{ pending }} 条 · 导入归属 {{ batch.week_key }}</p></div><Button variant="outline" :disabled="busy" @click="resume(batch.id)">重新读取批次</Button></div>
      <div class="qc-toolbar"><label class="qc-field"><span>预览客户</span><select v-model="customer" :disabled="busy" @change="page = 1"><option value="">全部客户</option><option v-for="name in customers" :key="name">{{ name }}</option></select></label><label class="qc-field"><span>预览状态</span><select v-model="status" :disabled="busy" @change="page = 1"><option value="">全部状态</option><option value="PENDING">待确认</option><option value="NEW">新增</option><option value="EXACT">更新候选</option><option value="MULTIPLE_MATCHES">需指定订单</option><option value="INVALID">待修正</option></select></label><Button variant="outline" :disabled="busy || !selected.length" @click="selected = []">清空勾选</Button><span class="qc-muted">勾选跨页保留；筛选不会清除勾选。</span></div>
      <div class="qc-table-scroll"><table class="qc-table"><thead><tr><th><input type="checkbox" aria-label="全选当前筛选下可导入的订单" :checked="allSelected" :disabled="busy || !selectable.length || !context.canScheduleWrite.value" @change="toggleAll"></th><th>来源 / 客户</th><th>合同 / PO / 货号</th><th>数量 / 日期</th><th>差异与处理</th></tr></thead><tbody>
        <tr v-for="row in pageRows" :key="row.id"><td><input v-model="selected" type="checkbox" :value="row.id" :aria-label="`选择第 ${row.source_row_no} 行`" :disabled="busy || !context.canScheduleWrite.value || !importAction(row, targets[row.id], actions[row.id])"></td><td><b>{{ row.customer_name || '客户待补' }}</b><small>{{ row.source_sheet_name }} · 第 {{ row.source_row_no }} 行</small></td><td><b>{{ row.sales_contract_no || '—' }}</b><small>PO {{ row.customer_po_no || '缺失' }}</small><small>货号 {{ row.customer_item_no || '—' }}</small></td><td>{{ row.quantity ?? '—' }}<small>验货 {{ effectiveInspectionDate(row) || '待安排' }}<span v-if="!row.planned_inspection_date && row.shipment_date">（按走货日期）</span></small><small>走货 {{ row.shipment_date || '—' }}</small></td><td class="min-w-64 max-w-96"><span class="qc-badge">{{ labels[row.decision_status === 'PENDING' ? row.match_status : row.decision_status] || '待确认' }}</span><label v-if="row.decision_status === 'PENDING'" class="qc-field mt-2"><span>本行处理方式</span><select v-model="actions[row.id]" :aria-label="`第 ${row.source_row_no} 行处理方式`" :disabled="busy || !context.canScheduleWrite.value" @change="selected = selected.filter(id => id !== row.id)"><option :value="undefined">{{ row.match_status === 'INVALID' ? '先修正源文件或选择跳过' : row.match_status === 'NEW' ? '新增订单' : '更新订单' }}</option><option v-if="row.match_status === 'EXACT' || row.match_status === 'MULTIPLE_MATCHES'" value="KEEP">保留原值</option><option v-if="row.match_status !== 'EXACT'" value="SKIP">明确跳过本行</option></select></label><p v-for="issue in row.validation_errors" :key="issue" class="mt-1 text-xs text-red-700">{{ issue }}</p><select v-if="row.match_status === 'MULTIPLE_MATCHES' && row.decision_status === 'PENDING'" v-model="targets[row.id]" class="qc-input mt-2" :disabled="busy" :aria-label="`第 ${row.source_row_no} 行目标订单`" @change="selected = selected.filter(id => id !== row.id)"><option value="">选择要更新的订单</option><option v-for="id in row.candidate_order_ids" :key="id" :value="id">{{ row.candidate_orders?.find(item => item.id === id)?.inspection_no || id }} · PO {{ row.candidate_orders?.find(item => item.id === id)?.customer_po_no }}</option></select><details v-if="row.changes.length" class="mt-2 text-xs"><summary>查看 {{ row.changes.length }} 项变化</summary><p v-for="change in row.changes" :key="change.field" class="mt-1">{{ ({ customer_name: '客户', sales_contract_no: '合同号', customer_po_no: 'PO', customer_item_no: '货号', quantity: '数量', product_name: '产品', shipment_date: '走货日期', planned_inspection_date: '验货日期', inspection_agency: '验货机构', account_manager: '跟客', export_country_code: '出口国' } as Record<string, string>)[change.field] || change.field }}：{{ change.old_value || '空' }} → {{ change.new_value || '空' }}</p></details></td></tr>
        <tr v-if="!pageRows.length"><td colspan="5" class="qc-empty">没有符合筛选条件的预览记录。</td></tr>
      </tbody></table></div>
      <div class="qc-toolbar justify-between"><span class="qc-muted">共 {{ visible.length }} 条 · 第 {{ page }} / {{ Math.max(1, Math.ceil(visible.length / 30)) }} 页</span><div class="flex gap-2"><Button variant="outline" :disabled="page <= 1 || busy" @click="page--">上一页</Button><Button variant="outline" :disabled="page * 30 >= visible.length || busy" @click="page++">下一页</Button></div></div>
      <div class="qc-confirm-bar"><div><b>已选 {{ decisions.length }} 条：新增 {{ newCount }} 条，更新 {{ updateCount }} 条，保留 {{ keepCount }} 条，跳过 {{ skipCount }} 条</b><p class="qc-muted">包含其他页或筛选条件下的勾选。错误行只能明确跳过；未勾选行保持待确认。超过 1,000 条将分段处理。</p></div><Button :disabled="busy || !decisions.length || !context.canScheduleWrite.value" @click="confirm">确认导入所选 {{ decisions.length }} 条</Button></div>
    </template>
  </section>
</template>
