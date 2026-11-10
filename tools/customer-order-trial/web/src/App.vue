<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import CustomerOrderLedger from '@/components/modules/sales/customer-order-center/CustomerOrderLedger.vue'
import CustomerOrderSchedule from '@/components/modules/sales/customer-order-center/CustomerOrderSchedule.vue'
import { customerOrderLedgerApi } from '@/api/customerOrderLedger'
import { quantityReconciliationRowId } from '@/lib/customerOrderReconciliation'
import type { CustomerOrderImportPreview, CustomerOrderIssue } from '@/types/customerOrder'
import { api, errorMessage, type TrialConfig, type DownloadResult } from './api'
import { businessFields, fieldLabels } from './fields'
import { exportControls, isResolved, manualInputType } from './controls'
import LocalInbox from './LocalInbox.vue'
import ExportHistory from './ExportHistory.vue'
import ExistingOrderLink, { type ExistingOrderSelection } from './ExistingOrderLink.vue'

const config = ref<TrialConfig | null>(null)
const configLoading = ref(false)
const setupError = ref('')
const tab = ref('import')
const customerCode = ref('')
const receivedDate = ref(new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()))
const sourceKind = ref('formal')
const poFiles = ref<File[]>([])
const scheduleFile = ref<File | null>(null)
const preview = ref<CustomerOrderImportPreview | null>(null)
const busy = ref('')
const message = ref('')
const failure = ref('')
const skipped = ref<string[]>([])
const values = ref<Record<string, string>>({})
const reason = ref('')
const existingOrder = ref<ExistingOrderSelection>({ enabled: false, lineId: '', expectedRevision: 0, reason: '' })
const generated = ref<{ url: string; fileName: string; passwordRequired: boolean } | null>(null)
const search = ref('')
const previewPage = ref(1)
const fileKey = ref(0)
let sequence = 0
const customer = computed(() => config.value?.customers.find(item => item.code === customerCode.value))
const controls = computed(() => exportControls(preview.value, skipped.value, values.value))
const pendingInformationItems = computed(() => (preview.value?.rows ?? [])
  .filter(row => row.row_role !== 'parent')
  .flatMap(row => row.issues
    .filter(issue => issue.severity === 'warning' && issue.pending_information && !isResolved(issue, skipped.value, values.value))
    .map(issue => ({ row, issue }))))
const reconciliationDetails = computed(() => (preview.value?.rows ?? []).filter(row => row.row_role !== 'parent'))
const reconciliationProductNo = computed(() => {
  const row = reconciliationDetails.value[0]
  if (!row) return ''
  return controls.value.overrides.find(item => item.row_id === row.id && item.field === 'product_no')?.value ?? row.product_no
})
const reasonInvalid = computed(() => controls.value.keys.length > 0 && (reason.value.trim().length < 4 || reason.value.trim().length > 500))
const canSaveLink = computed(() => !existingOrder.value.enabled || Boolean(existingOrder.value.lineId && existingOrder.value.expectedRevision > 0 && existingOrder.value.reason.trim().length >= 4 && existingOrder.value.reason.trim().length <= 500))
const canConfirm = computed(() => Boolean(preview.value?.rows.length && !controls.value.unresolved.length && !reasonInvalid.value && !busy.value))
const quantityReconciliationId = computed(() => quantityReconciliationRowId(
  preview.value, sourceKind.value, existingOrder.value, existingOrder.value.target, controls.value.overrides,
))
const canSave = computed(() => Boolean(preview.value?.rows.length && !controls.value.unresolved.some(issue => !(
  issue.rowId === quantityReconciliationId.value && issue.code === 'existing_quantity_conflict'
)) && !reasonInvalid.value && canSaveLink.value && !busy.value))
const filteredRows = computed(() => (preview.value?.rows ?? []).filter(row => !search.value.trim() || [row.po_no, row.contract_no, row.product_no, row.customer_name].join(' ').toLowerCase().includes(search.value.trim().toLowerCase())))
const totalPages = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / 30)))
const visibleRows = computed(() => filteredRows.value.slice((previewPage.value - 1) * 30, previewPage.value * 30))
watch(search, () => { previewPage.value = 1 })
const tabs = computed(() => [
  { id: 'import', label: '订单导入' }, { id: 'ledger', label: '订单台账与走货' },
  ...(config.value?.capabilities?.ledger_schedule ? [{ id: 'schedule', label: '各客排期' }] : []),
  { id: 'inbox', label: '本机部门收件' }, { id: 'exports', label: '排期文件历史' },
])

function clearDownload() {
  if (generated.value) URL.revokeObjectURL(generated.value.url)
  generated.value = null
}
function resetPreview() {
  sequence += 1
  preview.value = null
  skipped.value = []
  values.value = {}
  reason.value = ''
  existingOrder.value = { enabled: false, lineId: '', expectedRevision: 0, reason: '' }
  message.value = ''
  failure.value = ''
  previewPage.value = 1
  clearDownload()
}
function changeCustomer() {
  poFiles.value = []
  scheduleFile.value = null
  fileKey.value += 1
  resetPreview()
}
function chooseFiles(event: Event, kind: 'po' | 'schedule') {
  const files = Array.from((event.target as HTMLInputElement).files ?? [])
  resetPreview()
  if (kind === 'po') poFiles.value = files
  else scheduleFile.value = files[0] ?? null
}
function validateFiles() {
  if (!config.value || !customer.value) throw new Error('请先选择客户。')
  if (!poFiles.value.length || !scheduleFile.value) throw new Error('请同时选择客户原始 PO 和该客户现有排期。')
  const limits = config.value.limits
  if (poFiles.value.length > limits.po_files) throw new Error(`每批最多 ${limits.po_files} 份 PO。`)
  const accepts = (file: File, extensions: string[]) => extensions.some(ext => file.name.toLowerCase().endsWith(ext.toLowerCase().startsWith('.') ? ext.toLowerCase() : `.${ext.toLowerCase()}`))
  if (poFiles.value.some(file => !accepts(file, customer.value!.po_extensions))) throw new Error('PO 文件格式不在当前客户支持范围内，请核对文件。')
  if (!accepts(scheduleFile.value, customer.value.schedule_extensions)) throw new Error('排期文件格式不在当前客户支持范围内。')
  if (poFiles.value.some(file => file.size > limits.po_bytes) || poFiles.value.reduce((sum, file) => sum + file.size, 0) > limits.batch_po_bytes || scheduleFile.value.size > limits.schedule_bytes) throw new Error('所选文件超过本机试用的大小限制，请缩小批次。')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(receivedDate.value)) throw new Error('请填写有效的来单日期。')
}
function payload(confirm = false) {
  validateFiles()
  const body = new FormData()
  body.append('factory_id', config.value!.factory_id)
  body.append('customer_code', customerCode.value)
  body.append('received_date', receivedDate.value)
  poFiles.value.forEach(file => body.append('po_files', file))
  body.append('schedule_file', scheduleFile.value!)
  if (confirm) {
    body.append('confirmed', 'true')
    body.append('preview_fingerprint', preview.value!.preview_fingerprint)
    body.append('skipped_issue_keys', JSON.stringify(controls.value.keys))
    body.append('manual_overrides', JSON.stringify(controls.value.overrides))
    body.append('confirmation_reason', reason.value.trim())
    body.append('source_kind', sourceKind.value)
  }
  return body
}
async function loadConfig() {
  configLoading.value = true
  setupError.value = ''
  try {
    const result = await api.config()
    if (!result.factory_id || !result.customers.length) throw new Error('本机试用配置中没有可用客户。')
    config.value = result
  } catch (error) { setupError.value = await errorMessage(error) }
  finally { configLoading.value = false }
}
async function parse() {
  if (busy.value) return
  resetPreview()
  const token = sequence
  busy.value = '正在解析原件…'
  try {
    const result = await api.preview(payload())
    if (token !== sequence) return
    if (result.factory_id !== config.value!.factory_id || result.customer_code !== customerCode.value || !result.preview_fingerprint) throw new Error('返回的预览与当前厂区或客户不一致，请重新解析。')
    preview.value = result
    message.value = '解析完成，请逐行核对数量、价格、交期和提醒。'
  } catch (error) { if (token === sequence) failure.value = await errorMessage(error) }
  finally { if (token === sequence) busy.value = '' }
}
function editIssue(issue: CustomerOrderIssue, event: Event) {
  values.value[issue.skip_key] = (event.target as HTMLInputElement).value
  if (values.value[issue.skip_key]?.trim()) skipped.value = skipped.value.filter(key => key !== issue.skip_key)
  message.value = ''
  clearDownload()
}
function skipIssue(issue: CustomerOrderIssue, event: Event) {
  if ((event.target as HTMLInputElement).checked) {
    skipped.value = [...new Set([...skipped.value, issue.skip_key])]
    delete values.value[issue.skip_key]
  } else skipped.value = skipped.value.filter(key => key !== issue.skip_key)
  message.value = ''
  clearDownload()
}
function retainDownload(result: DownloadResult) {
  clearDownload()
  generated.value = { url: URL.createObjectURL(result.blob), fileName: result.fileName, passwordRequired: result.passwordRequired }
  const link = document.createElement('a')
  link.href = generated.value.url
  link.download = generated.value.fileName
  link.click()
}
async function confirm(kind: 'save' | 'export') {
  if (kind === 'save' ? !canSave.value : !canConfirm.value) return
  busy.value = kind === 'save' ? '正在保存本机订单…' : '正在生成客户排期…'
  failure.value = ''
  message.value = ''
  try {
    const body = payload(true)
    if (kind === 'save') {
      if (existingOrder.value.enabled) {
        body.append('reconcile_line_id', existingOrder.value.lineId)
        body.append('expected_revision', String(existingOrder.value.expectedRevision))
        body.append('reconciliation_reason', existingOrder.value.reason.trim())
      }
      const result = await customerOrderLedgerApi.importConfirmed(customerCode.value, body)
      message.value = `本机订单保存完成：新增 ${result.created_count} 条，已有 ${result.existing_count} 条，关联修订 ${result.reconciled_count} 条。请在订单台账核对；排期副本可到文件历史下载。`
    } else {
      retainDownload(await api.export(body))
      message.value = '客户排期已生成并保存到本机文件历史。需要台账及发送、走货记录时，请另点“确认并保存订单”。'
    }
  } catch (error) { failure.value = await errorMessage(error) }
  finally { busy.value = '' }
}
onMounted(() => { void loadConfig() })
onBeforeUnmount(() => { sequence += 1; clearDownload() })
</script>

<template>
  <main class="trial-shell">
    <PageHeader :title="`${config?.factory_name || '客户订单排期'}｜本地试用`" eyebrow="订单与排期工作台" description="沿用原系统的订单识别、人工核对和排期格式。先用随包演示资料熟悉流程，再选择自己的客户原件。">
      <template #actions><StatusPill label="数据保存在本机" tone="teal" /></template>
    </PageHeader>
    <div class="trial-notice" role="note">本机数据、编号和记录独立保存。发送只写入这台电脑的部门收件箱，不会通知线上员工或更新正式台账、仓库。关闭启动窗口会停止本机服务。</div>
    <div v-if="setupError" class="notice error" role="alert">{{ setupError }} <Button variant="outline" :disabled="configLoading" @click="loadConfig">重新加载</Button></div>
    <p v-else-if="configLoading" role="status">正在读取本机配置…</p>
    <template v-if="config">
      <nav class="trial-tabs" aria-label="试用功能"><Button v-for="item in tabs" :key="item.id" :variant="tab === item.id ? 'default' : 'outline'" :aria-current="tab === item.id ? 'page' : undefined" :disabled="Boolean(busy)" @click="tab = item.id">{{ item.label }}</Button></nav>
      <div v-show="tab === 'import'" class="trial-stack">
        <SectionPanel title="导入客户订单与排期" subtitle="保持客户原始文件不变，生成新的排期副本。切换客户后需重新选择文件。">
          <fieldset :disabled="Boolean(busy)" class="trial-fields">
            <label>当前客户<select v-model="customerCode" data-testid="customer" @change="changeCustomer"><option value="">请选择客户</option><option v-for="item in config.customers" :key="item.code" :value="item.code">{{ item.name }}（{{ item.code }}）</option></select></label>
            <label>来单日期<input v-model="receivedDate" data-testid="received-date" type="date" @change="resetPreview"></label>
            <label>台账资料类型<select v-model="sourceKind" @change="message = ''; clearDownload()"><option value="formal">正式 PO</option><option value="supplementary">补充资料</option></select></label>
            <div :key="fileKey" class="file-grid">
              <label class="file-card">01 · 客户原始 PO <small>每批最多 {{ config.limits.po_files }} 份；支持 {{ customer?.po_extensions.join('、') || '先选择客户' }}</small><input data-testid="po-files" type="file" multiple :accept="customer?.po_extensions.join(',')" :disabled="!customer" @change="chooseFiles($event, 'po')"><span v-if="poFiles.length">{{ poFiles.map(file => file.name).join('；') }}</span></label>
              <label class="file-card">02 · 客户现有排期 <small>支持 {{ customer?.schedule_extensions.join('、') || '先选择客户' }}</small><input data-testid="schedule-file" type="file" :accept="customer?.schedule_extensions.join(',')" :disabled="!customer" @change="chooseFiles($event, 'schedule')"><span>{{ scheduleFile?.name || '请选择与当前客户对应的统一排期' }}</span></label>
            </div>
          </fieldset>
          <div class="trial-actions"><Button :disabled="!customer || !poFiles.length || !scheduleFile || Boolean(busy)" @click="parse">{{ busy || '解析并进入预览' }}</Button><span v-if="busy" role="status">文件较大时可能需要几分钟，请等待当前操作完成。</span></div>
        </SectionPanel>
        <p v-if="failure" class="notice error" role="alert">{{ failure }}</p>
        <p v-if="message" class="notice success" role="status">{{ message }}</p>
        <SectionPanel v-if="preview" title="预览与人工核对" :subtitle="`${preview.po_file_count} 份 PO · ${preview.rows.length} 条明细 · 输出 ${preview.output_file_name}`">
          <div class="trial-actions"><StatusPill :label="`原始有效 ${preview.summary.valid}`" tone="teal" /><StatusPill :label="`提醒 ${preview.summary.warning}`" tone="amber" /><StatusPill :label="`仍待处理 ${controls.unresolved.length}`" :tone="controls.unresolved.length ? 'red' : 'teal'" /></div>
          <ul v-if="preview.warnings.length" class="notice warning"><li v-for="(warning, index) in preview.warnings" :key="index">{{ warning }}</li></ul>
          <div v-if="pendingInformationItems.length" class="notice warning" data-testid="pending-information" role="status">
            <strong>资料待补：{{ pendingInformationItems.length }} 项</strong>
            <p>这些缺失信息可先留空，保存订单或生成排期不要求逐项确认。其他阻断或重复确认仍须处理；缺交期的订单需补齐并保存后再发送。</p>
            <ul><li v-for="({ row, issue }, index) in pendingInformationItems.slice(0, 8)" :key="`${row.id}-${issue.code}-${index}`">{{ row.po_no || row.contract_no || row.id }} · {{ row.product_no }}：{{ issue.message }}</li></ul>
            <p v-if="pendingInformationItems.length > 8">其余 {{ pendingInformationItems.length - 8 }} 项见下方各行提醒。</p>
          </div>
          <div v-if="controls.unresolved.length" class="notice error" role="status">仍有 {{ controls.unresolved.length }} 项阻断或待确认，必须按每行提示处理。<ul><li v-for="(issue, index) in controls.unresolved.slice(0, 8)" :key="index">{{ issue.rowId }}：{{ issue.message }}</li></ul></div>
          <label class="search-label">查找明细<input v-model="search" type="search" placeholder="客户 PO、合同号或完整货号"></label>
          <div class="preview-table" tabindex="0" aria-label="订单明细横向滚动表格"><table><thead><tr><th>核对状态</th><th>客户 PO / 合同号</th><th>完整货号</th><th>数量 / 装箱</th><th>客户交期</th><th>港币单价 / 金额</th><th>美元单价 / 金额</th><th>来源与详细字段</th></tr></thead>
            <tbody><template v-for="row in visibleRows" :key="row.id"><tr><td>{{ row.status_label }}</td><td>{{ row.po_no || '—' }}<br>{{ row.contract_no }}</td><td>{{ row.product_no }}<small v-if="row.product_version">{{ row.product_version }}</small></td><td>{{ row.quantity }} / {{ row.units_per_carton || '—' }}<small>箱数 {{ row.carton_count || '—' }}</small></td><td>{{ row.requested_ship_date || '待补' }}</td><td>{{ row.unit_price_hkd || '—' }} / {{ row.amount_hkd || '—' }}</td><td>{{ row.unit_price_usd || '—' }} / {{ row.amount_usd || '—' }}</td><td><details><summary>原始字段与来源</summary><p>{{ row.source_po_file_name }}</p><p>{{ row.price_details_text }}</p><dl class="trace-fields"><template v-for="field in businessFields({ ...row })" :key="field.key"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></template></dl><h4>字段来源</h4><dl class="trace-fields"><template v-for="(source, key) in row.lineage" :key="key"><dt>{{ fieldLabels[key] || key }}</dt><dd>{{ source }}</dd></template></dl></details></td></tr>
              <tr v-if="row.issues.length"><td colspan="8"><fieldset :disabled="Boolean(busy)" class="issue-list"><div v-for="(issue, index) in row.issues" :key="`${issue.skip_key}-${index}`" class="issue" :class="{ resolved: isResolved(issue, skipped, values) }"><strong>{{ issue.message }}</strong><small>{{ issue.field }} · {{ isResolved(issue, skipped, values) ? '已记录人工处理' : issue.severity === 'warning' ? '提醒' : '待处理' }}</small><label v-if="issue.can_edit && issue.edit_field && issue.skip_key">{{ issue.edit_label || issue.field }}<textarea v-if="issue.edit_input_type === 'textarea' || ['product_version', 'po_unit_prices'].includes(issue.edit_field)" :value="values[issue.skip_key] || ''" rows="3" :placeholder="issue.edit_field === 'po_unit_prices' ? '各 PO 单价（HKD），每行 PO=单价' : '按原件核对后填写'" @input="editIssue(issue, $event)" /><input v-else :value="values[issue.skip_key] || ''" :type="manualInputType(issue)" step="any" @input="editIssue(issue, $event)"></label><label v-if="issue.can_skip && issue.skip_key && issue.severity !== 'warning'" class="check"><input type="checkbox" :checked="skipped.includes(issue.skip_key)" @change="skipIssue(issue, $event)">{{ issue.skip_label || '已人工核对，确认继续' }}</label></div></fieldset></td></tr>
            </template><tr v-if="!visibleRows.length"><td colspan="8">没有符合条件的明细。</td></tr></tbody></table></div>
          <div class="pagination"><span>第 {{ previewPage }} / {{ totalPages }} 页，共 {{ filteredRows.length }} 条</span><Button variant="outline" :disabled="previewPage <= 1" @click="previewPage--">上一页</Button><Button variant="outline" :disabled="previewPage >= totalPages" @click="previewPage++">下一页</Button></div>
          <label v-if="controls.keys.length" class="reason">人工处理原因（4–500 字）<textarea v-model="reason" maxlength="500" rows="3" :disabled="Boolean(busy)" @input="message = ''; clearDownload()"/><small>已处理 {{ controls.keys.length }} 项，其中人工更正 {{ controls.overrides.length }} 项；原始文件与人工值一起保留。{{ reason.trim().length }} / 500</small></label>
          <ExistingOrderLink v-model="existingOrder" :factory-id="config.factory_id" :customer-code="customerCode" :product-no="reconciliationProductNo" :eligible="sourceKind === 'formal' && reconciliationDetails.length === 1" :disabled="Boolean(busy)" />
          <p v-if="quantityReconciliationId" class="notice warning">此数量变更将通过“确认并保存订单”修订所选原订单；单独生成排期仍须处理原冲突。</p>
          <div class="trial-actions"><Button data-testid="save" variant="outline" :disabled="!canSave" @click="confirm('save')">{{ busy || '确认并保存订单' }}</Button><Button data-testid="export" :disabled="!canConfirm" @click="confirm('export')">{{ busy || '确认警告并生成客户排期' }}</Button></div>
          <p class="muted">保存订单后可在本机台账修改、发送及登记走货。生成排期只产生文件副本，不代表订单已入台账；人工更正的最终数量与金额以服务器校验后的文件为准。</p>
          <div v-if="generated" class="notice success"><a :href="generated.url" :download="generated.fileName">下载 {{ generated.fileName }}</a><p v-if="generated.passwordRequired">下载文件保留原排期保护设置，请使用业务原密码打开。</p></div>
        </SectionPanel>
      </div>
      <SectionPanel v-if="tab === 'ledger'"><CustomerOrderLedger :factory-id="config.factory_id" :factory-name="config.factory_name" :history-import-enabled="Boolean(config.capabilities?.history_import)" :local-only="true" @import="tab = 'import'" /></SectionPanel>
      <SectionPanel v-if="tab === 'schedule' && config.capabilities?.ledger_schedule"><CustomerOrderSchedule :factory-id="config.factory_id" :factory-name="config.factory_name" :history-import-enabled="Boolean(config.capabilities?.history_import)" :workbook-tools-enabled="Boolean(config.capabilities?.workbook_tools)" :local-only="true" @import="tab = 'import'" /></SectionPanel>
      <LocalInbox v-if="tab === 'inbox'" :factory-id="config.factory_id" />
      <ExportHistory v-if="tab === 'exports'" />
    </template>
  </main>
</template>

<style>
.trial-shell{max-width:1720px;margin:0 auto;padding:32px 28px 64px;display:grid;gap:22px;color:var(--foreground);font-size:14px}.trial-notice{padding:13px 16px;border:1px solid var(--border);border-left:3px solid var(--primary);border-radius:8px;background:var(--card);color:var(--muted-foreground);line-height:1.7}.trial-tabs,.trial-actions,.pagination{display:flex;flex-wrap:wrap;align-items:center;gap:10px}.trial-tabs{border-bottom:1px solid var(--border);padding-bottom:16px}.trial-stack{display:grid;gap:20px}.trial-fields{display:grid;grid-template-columns:2fr 1fr 1fr;gap:16px;border:0;padding:0;margin:0}.trial-shell label{display:grid;gap:7px;font-size:13px;font-weight:600}.trial-shell input:not([type=checkbox]),.trial-shell select,.trial-shell textarea{width:100%;min-width:0;border:1px solid var(--border);border-radius:7px;padding:9px 10px;background:var(--card);color:var(--foreground);font:inherit}.trial-shell :focus-visible{outline:2px solid var(--primary);outline-offset:3px}.file-grid{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr;gap:18px}.trial-shell .file-card{padding:22px;border:1px dashed var(--border);border-radius:10px;background:var(--muted);min-width:0;gap:14px}.file-card span{overflow-wrap:anywhere;line-height:1.6;font-weight:400}.trial-shell small,.muted,.trial-actions>span{font-size:12px;color:var(--muted-foreground);font-weight:400;line-height:1.6}.trial-actions{margin:16px 0}.notice{border-radius:8px;border:1px solid;padding:12px 16px;margin:0;line-height:1.7;overflow-wrap:anywhere}.notice ul,.notice:is(ul){padding-left:26px}.error{background:#fff1f2;border-color:#fecdd3;color:#9f1239}.success{background:#ecfdf5;border-color:#a7f3d0;color:#065f46}.warning{background:#fffbeb;border-color:#fde68a;color:#92400e}.search-label{max-width:440px;margin:16px 0}.preview-table,.trial-table{overflow:auto;border:1px solid var(--border);border-radius:8px}.preview-table table,.trial-table table{border-collapse:collapse;width:100%;min-width:1120px;font-size:12px}.preview-table th,.trial-table th{background:var(--muted);text-align:left;white-space:nowrap}.preview-table td,.preview-table th,.trial-table td,.trial-table th{padding:12px;border-bottom:1px solid var(--border);vertical-align:top}.preview-table td small{display:block}.preview-table td:nth-child(8){min-width:180px}.preview-table details pre,.inbox-snapshot{white-space:pre-wrap;overflow-wrap:anywhere;max-width:580px;max-height:420px;overflow:auto;font-size:11px;line-height:1.6;margin-top:12px}.trace-fields{display:grid;grid-template-columns:100px minmax(200px,1fr);gap:7px 12px;max-width:600px;margin:12px 0}.trace-fields dt{color:var(--muted-foreground)}.trace-fields dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}.preview-table details[open]{min-width:300px}.issue-list{padding:0;border:0;display:grid;gap:12px}.issue{padding:12px;border-left:3px solid #f59e0b;background:#fffbeb;display:grid;gap:8px;max-width:1050px}.issue.resolved{border-left-color:#10b981;background:#ecfdf5}.issue strong{font-weight:600}.issue label{max-width:680px}.trial-shell .check{display:flex;align-items:center;gap:8px}.check input{accent-color:var(--primary)}.pagination{justify-content:flex-end;margin:16px 0}.pagination>span{margin-right:auto;color:var(--muted-foreground);font-size:12px}.reason{margin:18px 0;max-width:900px}.notice a{font-weight:700;text-decoration:underline}.trial-shell button:disabled,.trial-shell fieldset:disabled{opacity:.65}.inbox-grid{display:grid;gap:14px}.inbox-card{border:1px solid var(--border);border-radius:9px;padding:18px;display:grid;gap:10px}.inbox-card header{display:flex;gap:12px;justify-content:space-between;flex-wrap:wrap}.inbox-card h3{font-weight:700;margin:0}.inbox-card dl{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.inbox-card dt{font-size:12px;color:var(--muted-foreground)}.inbox-card dd{margin:4px 0;font-weight:600;overflow-wrap:anywhere}@media(max-width:760px){.trial-shell{padding:18px 14px 40px;gap:16px}.trial-fields,.file-grid{grid-template-columns:1fr}.trial-fields>label{grid-column:1}.trial-shell .file-card{padding:16px}.inbox-card dl{grid-template-columns:1fr 1fr}.trial-actions>button{white-space:normal;min-height:38px;height:auto;padding-top:8px;padding-bottom:8px}}
</style>
