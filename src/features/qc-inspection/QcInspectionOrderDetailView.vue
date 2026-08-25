<script setup lang="ts">
import axios from 'axios'
import { AlertTriangle, ArrowLeft, CheckCircle2, Download, FilePlus2, LoaderCircle, Plus, Save, Trash2 } from '@lucide/vue'
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { qcInspectionApi, type QcGeneratedReport, type QcInspectionEvent, type QcInspectionEventPayload, type QcInspectionLine, type QcInspectionOrder } from '@/api/qcInspection'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { useQcInspectionWorkspace } from './context'

const context = useQcInspectionWorkspace()
const route = useRoute()
const order = ref<QcInspectionOrder | null>(null)
const events = ref<QcInspectionEvent[]>([])
const selectedEvent = ref<QcInspectionEvent | null>(null)
const latestReport = ref<QcGeneratedReport | null>(null)
const loading = ref(true)
const saving = ref(false)
const forbidden = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const orderId = computed(() => String(route.params.orderId ?? ''))

function blankLine(): QcInspectionLine {
  return {
    customer_po_no: order.value?.customer_po_no ?? '', release_no: '',
    customer_item_no: order.value?.customer_item_no ?? '', internal_item_no: '',
    batch_no: '', date_code: '', product_name: order.value?.product_name ?? '',
    order_quantity: order.value?.quantity ?? null, inspected_quantity: order.value?.quantity ?? null,
    packing: order.value?.packing ?? '', carton_count: order.value?.carton_count ?? '', upc_ean: '',
  }
}

function blankEvent(): QcInspectionEventPayload {
  return {
    factory_id: context.factoryId.value, inspection_order_id: orderId.value,
    event_type: events.value.length ? 'REINSPECTION' : 'CUSTOMER',
    actual_inspection_date: new Date().toISOString().slice(0, 10),
    inspector_name: '', inspection_agency: order.value?.inspection_agency ?? '', inspection_location: '',
    sampling_standard: 'ANSI/ASQ Z1.4', inspection_level: 'II',
    aql_critical: '0', aql_major: '2.5', aql_minor: '4.0',
    lot_size: Number(order.value?.quantity ?? 0), sample_size: 0,
    critical_defect_count: 0, major_defect_count: 0, minor_defect_count: 0,
    inspection_result: 'PENDING', document_status: 'DRAFT', manual_has_problem: false,
    report_number: '', note: '', lines: [blankLine()], defects: [], tests: [], dispositions: [],
  }
}

const form = reactive<QcInspectionEventPayload>(blankEvent())
const defectCounts = computed(() => ({
  CRITICAL: form.defects.filter((item) => item.severity === 'CRITICAL').reduce((sum, item) => sum + Number(item.quantity || 0), 0),
  MAJOR: form.defects.filter((item) => item.severity === 'MAJOR').reduce((sum, item) => sum + Number(item.quantity || 0), 0),
  MINOR: form.defects.filter((item) => item.severity === 'MINOR').reduce((sum, item) => sum + Number(item.quantity || 0), 0),
}))

function resetForNewEvent() {
  selectedEvent.value = null
  Object.assign(form, blankEvent())
}

function editEvent(event: QcInspectionEvent) {
  selectedEvent.value = event
  const { id: _id, revision: _revision, attempt_no: _attempt, created_at: _createdAt,
    updated_at: _updatedAt, created_by: _createdBy, created_by_name: _createdName,
    updated_by: _updatedBy, updated_by_name: _updatedName, ...values } = event
  Object.assign(form, {
    ...values,
    lines: event.lines.map(({ id: _lineId, line_no: _lineNo, ...item }) => ({ ...item })),
    defects: event.defects.map(({ id: _defectId, ...item }) => ({ ...item })),
    tests: event.tests.map(({ id: _testId, ...item }) => ({ ...item })),
    dispositions: event.dispositions.map(({ id: _dispositionId, ...item }) => ({ ...item })),
  })
}

async function loadOrder() {
  loading.value = true; forbidden.value = false; errorMessage.value = ''
  try {
    const [orderValue, eventValues] = await Promise.all([
      qcInspectionApi.getOrder(orderId.value, context.factoryId.value),
      qcInspectionApi.listInspectionEvents(orderId.value, context.factoryId.value),
    ])
    order.value = orderValue; events.value = eventValues
    eventValues.length ? editEvent(eventValues[0]) : resetForNewEvent()
  } catch (error) {
    order.value = null
    forbidden.value = axios.isAxiosError(error) && error.response?.status === 403
    errorMessage.value = getApiErrorMessage(error)
  } finally { loading.value = false }
}

function eventPayload(): QcInspectionEventPayload {
  return {
    ...form,
    critical_defect_count: defectCounts.value.CRITICAL,
    major_defect_count: defectCounts.value.MAJOR,
    minor_defect_count: defectCounts.value.MINOR,
    manual_has_problem: form.manual_has_problem || Boolean(form.defects.length),
    lines: form.lines.map((item) => ({ ...item })), defects: form.defects.map((item) => ({ ...item })),
    tests: form.tests.map((item) => ({ ...item })), dispositions: form.dispositions.map((item) => ({ ...item })),
  }
}

function saveBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob); const anchor = document.createElement('a')
  anchor.href = url; anchor.download = fileName; anchor.click(); URL.revokeObjectURL(url)
}

async function saveEvent(generateReport: boolean) {
  if (!order.value || !context.canResultWrite.value) return
  errorMessage.value = ''; successMessage.value = ''
  if (!form.actual_inspection_date) { errorMessage.value = '请填写实际验货日期。'; return }
  if (!form.lines.length || form.lines.some((item) => !item.customer_po_no.trim() || !item.customer_item_no.trim())) {
    errorMessage.value = '至少保留一行 PO / 货号，并填写 PO 和客户货号。'; return
  }
  saving.value = true
  try {
    const saved = selectedEvent.value
      ? await qcInspectionApi.updateInspectionEvent(order.value.id, selectedEvent.value.id, { ...eventPayload(), expected_revision: selectedEvent.value.revision, reason: 'QC 更新本次验货报告资料' })
      : await qcInspectionApi.createInspectionEvent(order.value.id, eventPayload())
    const index = events.value.findIndex((item) => item.id === saved.id)
    if (index >= 0) events.value.splice(index, 1, saved); else events.value.unshift(saved)
    editEvent(saved)
    let completedMessage = ''
    if (generateReport) {
      const report = await qcInspectionApi.generateOrderReport(order.value.id, saved.id, context.factoryId.value)
      latestReport.value = report
      const result = await qcInspectionApi.downloadReport(report.id, report.artifact_file_name, context.factoryId.value)
      saveBlob(result.blob, result.fileName)
      completedMessage = `第 ${saved.attempt_no} 次验货已保存，报告已生成并下载。`
    } else completedMessage = `第 ${saved.attempt_no} 次验货记录已保存。`
    order.value = await qcInspectionApi.getOrder(order.value.id, context.factoryId.value)
    successMessage.value = completedMessage
  } catch (error) { errorMessage.value = getApiErrorMessage(error) } finally { saving.value = false }
}

watch(orderId, () => void loadOrder(), { immediate: true })
</script>

<template>
  <div class="space-y-6">
    <RouterLink :to="{ name: 'qc-inspection-schedule', query: { factory: context.factoryId.value, week: context.weekKey.value } }" class="inline-flex items-center gap-2 text-sm font-semibold text-teal-700"><ArrowLeft class="size-4" />返回验货排期</RouterLink>
    <SectionPanel v-if="loading" title="正在读取验货主单"><div class="grid min-h-52 place-items-center"><LoaderCircle class="size-7 animate-spin text-teal-700" /></div></SectionPanel>
    <SectionPanel v-else-if="forbidden" title="无权查看此验货主单"><p role="alert" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm">{{ errorMessage }}</p></SectionPanel>
    <SectionPanel v-else-if="!order" title="验货主单不可用"><p role="alert" class="rounded-xl border border-red-200 bg-red-50 p-4 text-sm">{{ errorMessage || '没有找到对应验货主单。' }}</p></SectionPanel>
    <template v-else>
      <SectionPanel :title="order.inspection_no || '验货主单'" subtitle="一张主单可保留多次验货/复验；每次验货独立形成可追溯报告。">
        <template #action><StatusPill :label="order.status || 'SCHEDULED'" :tone="order.status === 'COMPLETED' ? 'green' : 'blue'" /></template>
        <dl class="grid gap-3 sm:grid-cols-2 xl:grid-cols-6"><div v-for="item in [['客户', order.customer_name], ['合同号', order.sales_contract_no], ['PO', order.customer_po_no], ['货号', order.customer_item_no], ['产品', order.product_name], ['数量', String(order.quantity)]]" :key="item[0]" class="rounded-xl border bg-slate-50 px-3 py-2"><dt class="text-xs text-slate-500">{{ item[0] }}</dt><dd class="mt-1 text-sm font-semibold">{{ item[1] }}</dd></div></dl>
      </SectionPanel>

      <SectionPanel title="验货记录 / 复验" subtitle="选择历史记录可修订；新建复验会保留原记录。">
        <template #action><Button type="button" variant="outline" @click="resetForNewEvent"><FilePlus2 class="size-4" />新建复验</Button></template>
        <div class="flex gap-3 overflow-x-auto"><button v-for="item in events" :key="item.id" type="button" class="min-w-44 rounded-xl border p-3 text-left" :class="selectedEvent?.id === item.id ? 'border-teal-600 bg-teal-50' : 'border-slate-200'" @click="editEvent(item)"><b class="text-sm">第 {{ item.attempt_no }} 次 · {{ item.actual_inspection_date }}</b><span class="mt-1 block text-xs text-slate-500">{{ item.event_type }} · {{ item.inspection_result }}</span></button><p v-if="!events.length" class="rounded-xl border border-dashed p-4 text-sm text-slate-500">尚无记录，填写下方资料即可创建首份报告。</p></div>
      </SectionPanel>

      <SectionPanel title="验货报告工作台" subtitle="填完结论、PO/货号、缺陷、测试和处置后，可一键保存并下载报告。">
        <div class="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
          <label class="field"><span>验货日期 *</span><input v-model="form.actual_inspection_date" type="date"></label>
          <label class="field"><span>验货类型</span><select v-model="form.event_type"><option value="CUSTOMER">客验</option><option value="THIRD_PARTY">第三方</option><option value="LINE">巡线</option><option value="SELF">自检</option><option value="REINSPECTION">复验</option><option value="SAMPLE">抽检</option></select></label>
          <label class="field"><span>验货结果 *</span><select v-model="form.inspection_result"><option value="PENDING">待验</option><option value="PASS">PASS</option><option value="CONDITIONAL_PASS">有条件通过</option><option value="FAIL">FAIL</option><option value="REJECTED">拒收</option><option value="CANCELLED">取消</option></select></label>
          <label class="field"><span>验货员</span><input v-model="form.inspector_name"></label>
          <label class="field"><span>验货机构</span><input v-model="form.inspection_agency"></label>
          <label class="field"><span>报告号</span><input v-model="form.report_number"></label>
          <label class="field"><span>验货地点</span><input v-model="form.inspection_location"></label>
          <label class="field"><span>抽样标准</span><input v-model="form.sampling_standard"></label>
          <label class="field"><span>检验水平</span><input v-model="form.inspection_level"></label>
          <label class="field"><span>批量</span><input v-model.number="form.lot_size" type="number" min="0"></label>
          <label class="field"><span>抽样数</span><input v-model.number="form.sample_size" type="number" min="0"></label>
          <label class="field"><span>文档状态</span><select v-model="form.document_status"><option value="DRAFT">草稿</option><option value="FINAL">定稿</option><option value="REVISED">修订</option></select></label>
        </div>
        <div class="mt-4 grid gap-3 sm:grid-cols-3"><div class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">致命 {{ defectCounts.CRITICAL }}</div><div class="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">主要 {{ defectCounts.MAJOR }}</div><div class="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800">次要 {{ defectCounts.MINOR }}</div></div>

        <div class="section-heading"><h3>PO / 货号明细 *</h3><Button size="sm" variant="outline" @click="form.lines.push(blankLine())"><Plus class="size-4" />增加一行</Button></div>
        <div class="space-y-3"><div v-for="(line, index) in form.lines" :key="index" class="entry-grid xl:grid-cols-6"><input v-model="line.customer_po_no" placeholder="PO *"><input v-model="line.customer_item_no" placeholder="客户货号 *"><input v-model="line.release_no" placeholder="Release"><input v-model="line.batch_no" placeholder="批次"><input v-model="line.date_code" placeholder="Date Code"><div class="flex gap-2"><input v-model="line.inspected_quantity" class="min-w-0 flex-1" placeholder="验货数量"><button type="button" class="text-red-600" :disabled="form.lines.length === 1" @click="form.lines.splice(index, 1)"><Trash2 class="size-4" /></button></div></div></div>

        <div class="section-heading"><h3>缺陷明细</h3><Button size="sm" variant="outline" @click="form.defects.push({ event_line_id: '', category: '', severity: 'MAJOR', quantity: 1, defect_location: '', description: '', production_department: order?.production_department || '', photo_reference: '' })"><Plus class="size-4" />增加缺陷</Button></div>
        <div class="space-y-3"><div v-for="(item, index) in form.defects" :key="index" class="entry-grid md:grid-cols-[150px_100px_1fr_44px]"><select v-model="item.severity"><option value="CRITICAL">致命</option><option value="MAJOR">主要</option><option value="MINOR">次要</option><option value="OBSERVATION">观察项</option></select><input v-model.number="item.quantity" type="number" min="0"><input v-model="item.description" placeholder="问题描述 *"><button type="button" class="text-red-600" @click="form.defects.splice(index, 1)"><Trash2 class="size-4" /></button></div></div>

        <div class="mt-7 grid gap-6 xl:grid-cols-2">
          <div><div class="section-heading mt-0"><h3>测试记录</h3><Button size="sm" variant="outline" @click="form.tests.push({ test_item: '', method_standard: '', specification: '', measured_value: '', unit: '', sample_size: 1, result: 'PENDING', operator_name: '', reviewer_name: '' })"><Plus class="size-4" />增加测试</Button></div><div v-for="(item, index) in form.tests" :key="index" class="entry-grid mb-3 sm:grid-cols-[1fr_1fr_120px_40px]"><input v-model="item.test_item" placeholder="测试项目 *"><input v-model="item.measured_value" placeholder="实测值"><select v-model="item.result"><option value="PENDING">待定</option><option value="PASS">PASS</option><option value="FAIL">FAIL</option><option value="NA">不适用</option></select><button type="button" class="text-red-600" @click="form.tests.splice(index, 1)"><Trash2 class="size-4" /></button></div></div>
          <div><div class="section-heading mt-0"><h3>处置记录</h3><Button size="sm" variant="outline" @click="form.dispositions.push({ disposition_type: 'REWORK', return_quantity: null, rework_quantity: null, reason: '', approved_by: '', approved_date: '', verification_result: '' })"><Plus class="size-4" />增加处置</Button></div><div v-for="(item, index) in form.dispositions" :key="index" class="entry-grid mb-3 sm:grid-cols-[150px_1fr_40px]"><select v-model="item.disposition_type"><option value="RETURN">退货</option><option value="REWORK">返工</option><option value="AOD">AOD</option><option value="CONCESSION_ACCEPTED">让步接收</option><option value="ON_HOLD">暂停</option><option value="NO_ACTION">无需处置</option></select><input v-model="item.reason" placeholder="处置原因"><button type="button" class="text-red-600" @click="form.dispositions.splice(index, 1)"><Trash2 class="size-4" /></button></div></div>
        </div>
        <label class="field mt-6"><span>验货备注</span><textarea v-model="form.note" rows="3"></textarea></label>
        <div v-if="form.inspection_result === 'PASS' && form.dispositions.some((item) => item.disposition_type === 'RETURN')" class="mt-4 flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm"><AlertTriangle class="size-4" />PASS 不能同时登记退货处置。</div>
        <p v-if="errorMessage" role="alert" class="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{{ errorMessage }}</p>
        <p v-if="successMessage" class="mt-4 flex gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"><CheckCircle2 class="size-4" />{{ successMessage }}</p>
        <div class="mt-5 flex justify-end gap-3"><Button variant="outline" :disabled="saving || !context.canResultWrite.value" @click="saveEvent(false)"><Save class="size-4" />只保存记录</Button><Button :disabled="saving || !context.canResultWrite.value || !context.canReportExport.value" @click="saveEvent(true)"><LoaderCircle v-if="saving" class="size-4 animate-spin" /><Download v-else class="size-4" />保存并生成验货报告</Button></div>
        <p v-if="latestReport" class="mt-3 text-right text-xs text-slate-500">最近生成：{{ latestReport.artifact_file_name }}</p>
      </SectionPanel>
    </template>
  </div>
</template>

<style scoped>
.field { display: grid; gap: .35rem; font-size: .75rem; font-weight: 600; color: rgb(51 65 85); }
.field input, .field select, .field textarea, .entry-grid input, .entry-grid select { width: 100%; border: 1px solid rgb(226 232 240); border-radius: .5rem; background: white; padding: .55rem .7rem; font-size: .875rem; outline: none; }
.field input, .field select, .entry-grid input, .entry-grid select { height: 2.5rem; }
.section-heading { margin-top: 1.75rem; margin-bottom: .75rem; display: flex; align-items: center; justify-content: space-between; gap: .75rem; font-weight: 600; }
.entry-grid { display: grid; gap: .75rem; border: 1px solid rgb(226 232 240); border-radius: .75rem; padding: .75rem; }
</style>
