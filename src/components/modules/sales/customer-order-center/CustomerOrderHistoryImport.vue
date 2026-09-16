<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  customerOrderHistoryApi,
  type CustomerOrderHistoryPreview,
  type CustomerOrderHistoryRow,
  type CustomerOrderHistorySection,
  type CustomerOrderHistoryStatus,
} from '@/api/customerOrderHistory'
import { customerOrderLedgerApi, type CustomerOrderLedgerCapabilities } from '@/api/customerOrderLedger'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ factoryId: string }>()
const emit = defineEmits<{ saved: []; close: [] }>()

const emptyCapabilities: CustomerOrderLedgerCapabilities = {
  read: false, write: false, dispatch: false, shipment_confirm: false, inbox_read: false, inbox_receive: false,
}

const customers = ref<Array<{ code: string; name: string }>>([])
const capabilities = ref<CustomerOrderLedgerCapabilities>(emptyCapabilities)
const customerCode = ref('')
const scheduleFile = ref<File | null>(null)
const preview = ref<CustomerOrderHistoryPreview | null>(null)
const selectedIds = ref<string[]>([])
const openingById = ref<Record<string, string>>({})
const statusById = ref<Record<string, CustomerOrderHistoryStatus>>({})
const sectionFilter = ref<'all' | CustomerOrderHistorySection>('all')
const search = ref('')
const page = ref(1)
const cutoffDate = ref('')
const reason = ref('')
const acknowledged = ref(false)
const loadingSetup = ref(false)
const previewing = ref(false)
const saving = ref(false)
const message = ref('')
let setupSequence = 0
let previewSequence = 0
let saveSequence = 0

const canSave = computed(() => capabilities.value.write && capabilities.value.shipment_confirm)
const selectedRows = computed(() => {
  const rowById = new Map(preview.value?.rows.map((row) => [row.id, row]) ?? [])
  return selectedIds.value.map((id) => rowById.get(id)).filter((row): row is CustomerOrderHistoryRow => Boolean(row))
})
const filteredRows = computed(() => (preview.value?.rows ?? []).filter((row) => {
  if (sectionFilter.value !== 'all' && row.section !== sectionFilter.value) return false
  const query = search.value.trim().toLowerCase()
  return !query || [row.reference_no, row.product_no, row.customer_name, row.sheet].some((value) => value.toLowerCase().includes(query))
}))
const pageCount = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / 50)))
const visibleRows = computed(() => filteredRows.value.slice((page.value - 1) * 50, page.value * 50))
const totals = computed(() => {
  const quantities = selectedRows.value.map((row) => row.quantity)
  const openings = selectedRows.value.map((row) => openingById.value[row.id] ?? '')
  const allStatusesChosen = selectedRows.value.every((row) => Boolean(statusFor(row)))
  const allOpeningsValid = openings.every((value, index) => decimalInRange(value, quantities[index] ?? '0'))
  return {
    count: selectedRows.value.length,
    quantity: sumDecimals(quantities),
    opening: allOpeningsValid ? sumDecimals(openings) : '待逐行填写',
    remaining: allOpeningsValid && allStatusesChosen ? sumRemaining(selectedRows.value, openings) : '待逐行确认',
  }
})

function resetPreview(clearFile = false) {
  previewSequence += 1
  saveSequence += 1
  previewing.value = false
  saving.value = false
  preview.value = null
  selectedIds.value = []
  openingById.value = {}
  statusById.value = {}
  sectionFilter.value = 'all'
  search.value = ''
  page.value = 1
  cutoffDate.value = ''
  reason.value = ''
  acknowledged.value = false
  message.value = ''
  if (clearFile) scheduleFile.value = null
}

function resetForFactory() {
  setupSequence += 1
  resetPreview(true)
  customers.value = []
  customerCode.value = ''
  capabilities.value = emptyCapabilities
}

async function loadSetup() {
  const token = ++setupSequence
  const factoryId = props.factoryId
  loadingSetup.value = true
  try {
    const [customerResult, nextCapabilities] = await Promise.all([
      customerOrderHistoryApi.customers(factoryId),
      customerOrderLedgerApi.capabilities(factoryId),
    ])
    if (token !== setupSequence || factoryId !== props.factoryId) return
    customers.value = customerResult.items
    capabilities.value = nextCapabilities
  } catch (error) {
    if (token !== setupSequence || factoryId !== props.factoryId) return
    message.value = `无法读取历史迁入资料：${getApiErrorMessage(error)}`
  } finally {
    if (token === setupSequence) loadingSetup.value = false
  }
}

function onCustomerChange() {
  resetPreview(true)
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  scheduleFile.value = input.files?.[0] ?? null
  resetPreview(false)
}

function canSelect(row: CustomerOrderHistoryRow) {
  return !row.blocked && !row.existing
}

function isSelected(row: CustomerOrderHistoryRow) {
  return selectedIds.value.includes(row.id)
}

function toggleRow(row: CustomerOrderHistoryRow) {
  if (!canSelect(row)) return
  if (isSelected(row)) {
    selectedIds.value = selectedIds.value.filter((id) => id !== row.id)
    return
  }
  if (selectedIds.value.length >= 500) {
    message.value = '一次最多迁入 500 条可选记录。请分批确认。'
    return
  }
  selectedIds.value = [...selectedIds.value, row.id]
}

function setOpening(row: CustomerOrderHistoryRow, value: string) {
  openingById.value = { ...openingById.value, [row.id]: value }
}

function statusFor(row: CustomerOrderHistoryRow): CustomerOrderHistoryStatus | undefined {
  return statusById.value[row.id]
}

function setStatus(row: CustomerOrderHistoryRow, value: string) {
  if (value === '') {
    const next = { ...statusById.value }
    delete next[row.id]
    statusById.value = next
    return
  }
  if (value !== 'active' && value !== 'cancelled') return
  statusById.value = { ...statusById.value, [row.id]: value }
}

function confirmStatusFromSections() {
  const next = { ...statusById.value }
  selectedRows.value.forEach((row) => { next[row.id] = row.section === 'cancelled' ? 'cancelled' : 'active' })
  statusById.value = next
}

function setOpeningForSelected(section: CustomerOrderHistorySection, value: (row: CustomerOrderHistoryRow) => string) {
  const next = { ...openingById.value }
  selectedRows.value.filter((row) => row.section === section).forEach((row) => { next[row.id] = value(row) })
  openingById.value = next
}

function applyFilters() {
  page.value = 1
}

async function requestPreview() {
  if (!customerCode.value || !scheduleFile.value) {
    message.value = '请选择客户和历史排期文件后再预览。'
    return
  }
  const token = ++previewSequence
  const factoryId = props.factoryId
  const customer = customerCode.value
  const file = scheduleFile.value
  previewing.value = true
  message.value = ''
  try {
    const result = await customerOrderHistoryApi.preview(factoryId, customer, file)
    if (token !== previewSequence || factoryId !== props.factoryId || customer !== customerCode.value || file !== scheduleFile.value) return
    if (result.factory_id !== factoryId || result.customer_code !== customer) {
      message.value = '历史排期预览的工厂或客户范围不匹配，请重新选择文件后再试。'
      preview.value = null
      return
    }
    preview.value = result
    selectedIds.value = []
    openingById.value = {}
    statusById.value = {}
    page.value = 1
  } catch (error) {
    if (token !== previewSequence || factoryId !== props.factoryId) return
    message.value = `无法预览历史排期：${getApiErrorMessage(error)}`
  } finally {
    if (token === previewSequence) previewing.value = false
  }
}

function validateSelections() {
  if (!preview.value || selectedRows.value.length === 0) return '请至少选择一条可迁入记录。'
  if (selectedRows.value.length > 500) return '一次最多迁入 500 条记录。'
  for (const row of selectedRows.value) {
    if (!canSelect(row)) return '阻断或已存在的记录不能迁入。请重新预览。'
    if (!statusFor(row)) return `请为 ${row.reference_no || row.product_no || row.id} 明确选择有效或已取消状态。`
    if (!decimalInRange(openingById.value[row.id] ?? '', row.quantity)) return `请为 ${row.reference_no || row.product_no || row.id} 明确填写 0 至订单数量之间的期初走货。`
  }
  if (!cutoffDate.value) return '请填写历史截止日期。'
  if (reason.value.trim().length < 4) return '请填写至少 4 个字的迁入原因。'
  if (!acknowledged.value) return '请确认已核对历史期初与后续走货规则。'
  return ''
}

async function confirmMigration() {
  const validation = validateSelections()
  if (validation) {
    message.value = validation
    return
  }
  if (!canSave.value) {
    message.value = '保存历史迁入需要“写入订单”和“确认走货”权限。'
    return
  }
  const activePreview = preview.value
  const file = scheduleFile.value
  if (!activePreview || !file) return
  const token = ++saveSequence
  const factoryId = props.factoryId
  const customer = customerCode.value
  saving.value = true
  message.value = ''
  try {
    const result = await customerOrderHistoryApi.confirm(factoryId, customer, file, {
      fingerprint: activePreview.fingerprint,
      cutoff_date: cutoffDate.value,
      reason: reason.value.trim(),
      selections: selectedRows.value.map((row) => ({
        id: row.id,
        status: statusFor(row)!,
        opening_shipped_quantity: openingById.value[row.id]!.trim(),
      })),
    })
    if (token !== saveSequence || factoryId !== props.factoryId || customer !== customerCode.value || file !== scheduleFile.value) return
    resetPreview(false)
    message.value = `已迁入 ${result.created_count} 条；已有 ${result.existing_count} 条未覆盖。`
    emit('saved')
  } catch (error) {
    if (token !== saveSequence || factoryId !== props.factoryId) return
    message.value = `无法确认迁入：${getApiErrorMessage(error)}`
  } finally {
    if (token === saveSequence) saving.value = false
  }
}

function sectionLabel(section: CustomerOrderHistorySection) {
  return ({ unshipped: '未走货', shipped: '已走货', cancelled: '已取消' } as Record<CustomerOrderHistorySection, string>)[section]
}

function rowStatus(row: CustomerOrderHistoryRow) {
  if (row.blocked) return '已阻断'
  if (row.existing) return '已存在'
  return '可迁入'
}

function sourceFields(row: CustomerOrderHistoryRow) {
  const declared = row.data.history_fields
  if (Array.isArray(declared)) {
    return declared.flatMap((field) => {
      if (!field || typeof field !== 'object' || Array.isArray(field)) return []
      const source = field as Record<string, unknown>
      const key = typeof source.column === 'string' ? source.column : ''
      const header = typeof source.header === 'string' ? source.header.trim() : ''
      return [{ key: key || header || 'field', label: header || originalFieldLabel(key), value: displayOriginalValue(source.value) }]
    })
  }
  return Object.entries(row.data).map(([key, value]) => ({ key, label: originalFieldLabel(key), value: displayOriginalValue(value) }))
}

function originalFieldLabel(key: string) {
  const labels: Record<string, string> = {
    po_no: '客户 P/O', contract_no: '合同号', customer_po: '客户 P/O', product_no: '产品编号', quantity: '订单数量',
    requested_ship_date: '客户要求交期', ship_date: '客户要求交期', note: '备注', remark: '备注', customer_name: '客户名称',
  }
  return labels[key] ?? `原始字段：${key.replace(/[^a-zA-Z0-9_.\-\u4e00-\u9fff]/g, ' ')}`
}

function displayOriginalValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  try { return JSON.stringify(value) } catch { return '（无法显示的原始值）' }
}

function decimalParts(value: string) {
  const normalized = value.trim()
  if (!/^\d+(?:\.\d+)?$/.test(normalized)) return null
  const [integer, fraction = ''] = normalized.split('.')
  return { integer, fraction }
}

function decimalInRange(value: string, maximum: string) {
  const current = decimalParts(value)
  const upper = decimalParts(maximum)
  if (!current || !upper) return false
  return compareDecimals(value, '0') >= 0 && compareDecimals(value, maximum) <= 0
}

function compareDecimals(left: string, right: string) {
  const leftParts = decimalParts(left)!
  const rightParts = decimalParts(right)!
  const scale = Math.max(leftParts.fraction.length, rightParts.fraction.length)
  const asScaled = (parts: { integer: string; fraction: string }) => BigInt(`${parts.integer}${parts.fraction.padEnd(scale, '0')}`)
  const difference = asScaled(leftParts) - asScaled(rightParts)
  return difference === 0n ? 0 : difference > 0n ? 1 : -1
}

function sumDecimals(values: string[]) {
  const valid = values.map(decimalParts)
  if (valid.some((value) => !value)) return '待填写'
  const scale = Math.max(0, ...valid.map((value) => value!.fraction.length))
  const total = valid.reduce((sum, value) => sum + BigInt(`${value!.integer}${value!.fraction.padEnd(scale, '0')}`), 0n)
  return formatScaled(total, scale)
}

function sumRemaining(rows: CustomerOrderHistoryRow[], openings: string[]) {
  const pairs = rows.map((row, index) => [decimalParts(row.quantity), decimalParts(openings[index] ?? ''), statusFor(row)] as const)
  if (pairs.some(([quantity, opening]) => !quantity || !opening)) return '待填写'
  const scale = Math.max(0, ...pairs.flatMap(([quantity, opening]) => [quantity!.fraction.length, opening!.fraction.length]))
  const total = pairs.reduce((sum, [quantity, opening, status]) => {
    if (status === 'cancelled') return sum
    const q = BigInt(`${quantity!.integer}${quantity!.fraction.padEnd(scale, '0')}`)
    const o = BigInt(`${opening!.integer}${opening!.fraction.padEnd(scale, '0')}`)
    return sum + q - o
  }, 0n)
  return formatScaled(total, scale)
}

function formatScaled(value: bigint, scale: number) {
  const negative = value < 0n
  const raw = (negative ? -value : value).toString().padStart(scale + 1, '0')
  const integer = scale ? raw.slice(0, -scale) : raw
  const fraction = scale ? raw.slice(-scale).replace(/0+$/, '') : ''
  return `${negative ? '-' : ''}${integer}${fraction ? `.${fraction}` : ''}`
}

watch(() => props.factoryId, () => { resetForFactory(); void loadSetup() }, { immediate: true })
watch([sectionFilter, search], applyFilters)
watch(pageCount, (count) => { if (page.value > count) page.value = count })
</script>

<template>
  <div class="history-import__backdrop" @click.self="emit('close')">
    <section class="history-import" role="dialog" aria-modal="true" aria-labelledby="history-import-title">
      <header class="history-import__header">
        <div><p>订单事实台账 · 独立历史迁入</p><h3 id="history-import-title">历史排期迁入</h3></div>
        <button type="button" class="history-import__close" aria-label="关闭历史排期迁入" @click="emit('close')">×</button>
      </header>
      <p class="history-import__notice">历史期初用于登记原排期截至截止日期（含当日）的已走货数量，不会生成新的出货单；截止日期后的实际走货仍须凭出货单确认。</p>

      <div class="history-import__form">
        <label>客户<select v-model="customerCode" :disabled="loadingSetup || previewing || saving" @change="onCustomerChange"><option value="">请选择客户</option><option v-for="customer in customers" :key="customer.code" :value="customer.code">{{ customer.name || customer.code }}</option></select></label>
        <label>历史排期文件<input data-testid="history-file" type="file" accept=".xls,.xlsx,.xlsm" :disabled="previewing || saving" @change="onFileChange"></label>
        <button class="history-import__button history-import__button--primary" type="button" :disabled="previewing || saving || !customerCode || !scheduleFile" @click="requestPreview">{{ previewing ? '正在预览…' : '解析并预览' }}</button>
      </div>
      <p v-if="message" class="history-import__message">{{ message }}</p>

      <template v-if="preview">
        <section class="history-import__summary">
          <div><span>源文件</span><strong>{{ preview.file_name }}</strong></div><div><span>解析记录</span><strong>{{ preview.summary.total }}</strong></div><div><span>阻断</span><strong>{{ preview.summary.blocked }}</strong></div><div><span>已存在</span><strong>{{ preview.summary.existing }}</strong></div>
        </section>
        <ul v-if="preview.warnings.length" class="history-import__warnings"><li v-for="warning in preview.warnings" :key="warning">{{ warning }}</li></ul>
        <div class="history-import__filters"><input v-model="search" type="search" placeholder="搜索参考号、产品编号或来源工作表"><select v-model="sectionFilter" aria-label="历史排期分组"><option value="all">全部分组</option><option value="unshipped">未走货</option><option value="shipped">已走货</option><option value="cancelled">已取消</option></select><span>显示 {{ filteredRows.length }} / {{ preview.rows.length }} 条</span></div>
        <div class="history-import__bulk"><button type="button" class="history-import__button" :disabled="saving" @click="confirmStatusFromSections">按原表分区确认所选状态</button><button type="button" class="history-import__button" :disabled="saving" @click="setOpeningForSelected('unshipped', () => '0')">所选未走货订单期初走货设为 0</button><button type="button" class="history-import__button" :disabled="saving" @click="setOpeningForSelected('shipped', (row) => row.quantity)">所选已走货订单按全量核对</button></div>
        <div class="history-import__table-wrap"><table><thead><tr><th>选择</th><th>来源</th><th>分组（提示）</th><th>参考号 / P/O</th><th>产品编号</th><th>数量</th><th>客户要求交期</th><th>迁入状态</th><th>期初已走货（必填）</th><th>状态 / 问题</th><th>原始字段</th></tr></thead><tbody>
          <tr v-for="row in visibleRows" :key="row.id"><td><input :checked="isSelected(row)" :disabled="!canSelect(row) || saving" type="checkbox" :aria-label="`选择 ${row.reference_no || row.product_no}`" @change="toggleRow(row)"></td><td>{{ row.sheet }} · 第 {{ row.row }} 行</td><td>{{ sectionLabel(row.section) }}</td><td class="history-import__mono">{{ row.reference_no || '—' }}</td><td class="history-import__mono">{{ row.product_no || '—' }}</td><td class="history-import__number">{{ row.quantity }}</td><td>{{ row.requested_ship_date || '—' }}</td><td><select :value="statusFor(row) ?? ''" :disabled="!isSelected(row) || saving" aria-label="迁入状态" @change="setStatus(row, ($event.target as HTMLSelectElement).value)"><option value="">请选择状态</option><option value="active">有效</option><option value="cancelled">已取消</option></select></td><td><input :value="openingById[row.id] ?? ''" :disabled="!isSelected(row) || saving" type="text" inputmode="decimal" placeholder="明确填写 0 至数量" @input="setOpening(row, ($event.target as HTMLInputElement).value)"></td><td><b :class="{ blocked: row.blocked, existing: row.existing }">{{ rowStatus(row) }}</b><ul v-if="row.issues.length"><li v-for="issue in row.issues" :key="issue">{{ issue }}</li></ul></td><td><details><summary>展开</summary><dl><template v-for="field in sourceFields(row)" :key="field.key"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></template></dl></details></td></tr>
          <tr v-if="visibleRows.length === 0"><td colspan="11">当前筛选没有历史排期记录。</td></tr>
        </tbody></table></div>
        <footer class="history-import__pagination"><span>第 {{ page }} / {{ pageCount }} 页，每页 50 条</span><button class="history-import__button" type="button" :disabled="page <= 1" @click="page -= 1">上一页</button><button class="history-import__button" type="button" :disabled="page >= pageCount" @click="page += 1">下一页</button></footer>
        <section class="history-import__confirm"><h4>确认迁入</h4><p>已选 {{ totals.count }} 条 · 订单数量 {{ totals.quantity }} · 期初已走货 {{ totals.opening }} · 后续可走货 {{ totals.remaining }}</p><div class="history-import__form"><label>历史截止日期<input v-model="cutoffDate" type="date" :disabled="saving"></label><label>迁入原因（至少 4 个字）<textarea v-model="reason" rows="2" :disabled="saving" /></label></div><label class="history-import__acknowledge"><input v-model="acknowledged" type="checkbox" :disabled="saving"> 我已逐条核对期初走货；截止日期包含当日走货。这不是新的出货单，截止日期后的走货必须凭出货单确认。</label><p v-if="!canSave" class="history-import__permission">保存需要“写入订单”和“确认走货”权限。</p><button class="history-import__button history-import__button--primary" type="button" :disabled="saving || !canSave" @click="confirmMigration">{{ saving ? '正在确认迁入…' : '确认迁入已选记录' }}</button></section>
      </template>
    </section>
  </div>
</template>

<style scoped>
.history-import__backdrop{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:20px;background:rgb(15 23 42 / .45)}.history-import{width:min(1280px,100%);max-height:calc(100vh - 40px);overflow:auto;border:1px solid #cbd5e1;border-radius:14px;background:#fff;padding:22px;color:#191b23;box-shadow:0 28px 70px rgb(15 23 42 / .3)}.history-import__header{display:flex;justify-content:space-between;gap:16px}.history-import__header p,.history-import__header h3,.history-import__confirm h4{margin:0}.history-import__header p{color:#006559;font-size:11px;font-weight:800;letter-spacing:.06em}.history-import__header h3{margin-top:4px;font-size:22px}.history-import__close{border:0;background:transparent;font-size:28px}.history-import__notice{margin:14px 0;border-left:3px solid #0e7490;background:#ecfeff;padding:10px;color:#155e75;font-size:13px;line-height:1.55}.history-import__form{display:flex;flex-wrap:wrap;gap:10px;align-items:end}.history-import__form label{display:grid;gap:4px;color:#475569;font-size:12px;font-weight:800}.history-import__form select,.history-import__form input,.history-import__form textarea,.history-import__filters input,.history-import__filters select,.history-import__table-wrap input,.history-import__table-wrap select{border:1px solid #cbd5e1;border-radius:6px;padding:8px;background:#fff;font:inherit}.history-import__form textarea{min-width:280px}.history-import__button{border:1px solid #b6c2cd;border-radius:6px;background:#fff;padding:8px 12px;color:#334155;font-size:12px;font-weight:800}.history-import__button--primary{border-color:#006559;background:#006559;color:#fff}.history-import__button:disabled{cursor:not-allowed;opacity:.55}.history-import__message{margin:10px 0;color:#b42318;font-size:13px}.history-import__summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:16px 0}.history-import__summary div{display:grid;gap:4px;border:1px solid #d7e1e6;border-radius:8px;background:#f8fbfc;padding:10px}.history-import__summary span{color:#64748b;font-size:11px}.history-import__summary strong{font-size:14px;word-break:break-word}.history-import__warnings{margin:10px 0;padding:10px 10px 10px 28px;border:1px solid #fcd34d;border-radius:8px;background:#fffbeb;color:#92400e;font-size:12px}.history-import__filters,.history-import__bulk,.history-import__pagination{display:flex;flex-wrap:wrap;gap:9px;align-items:center;margin:12px 0}.history-import__filters input{min-width:260px}.history-import__filters span,.history-import__pagination span{color:#64748b;font-size:12px}.history-import__table-wrap{overflow:auto;border:1px solid #d9e2e7;border-radius:8px}.history-import__table-wrap table{width:100%;min-width:1180px;border-collapse:collapse;font-size:12px}.history-import__table-wrap th,.history-import__table-wrap td{padding:9px;border-bottom:1px solid #e5edf0;vertical-align:top;text-align:left}.history-import__table-wrap th{background:#eff6f7;color:#334155;white-space:nowrap}.history-import__table-wrap td ul{margin:5px 0 0;padding-left:15px;color:#92400e}.history-import__table-wrap input[type=text]{width:150px}.history-import__mono{font-family:ui-monospace,Consolas,monospace}.history-import__number{font-variant-numeric:tabular-nums}.blocked{color:#b42318}.existing{color:#9a6700}.history-import__table-wrap details{min-width:180px}.history-import__table-wrap summary{cursor:pointer;color:#006559;font-weight:800}.history-import__table-wrap dl{display:grid;grid-template-columns:minmax(100px,.45fr) 1fr;gap:5px 8px;margin:8px 0 0}.history-import__table-wrap dt{color:#64748b}.history-import__table-wrap dd{margin:0;overflow-wrap:anywhere}.history-import__pagination{justify-content:flex-end}.history-import__confirm{margin-top:16px;border-top:1px solid #dbe5e8;padding-top:16px}.history-import__confirm h4{font-size:16px}.history-import__confirm>p{color:#475569;font-size:13px}.history-import__acknowledge{display:flex;gap:8px;align-items:flex-start;margin:12px 0;color:#334155;font-size:12px;line-height:1.5}.history-import__permission{color:#b42318!important}@media(max-width:720px){.history-import{padding:16px}.history-import__summary{grid-template-columns:1fr 1fr}.history-import__form{display:grid}.history-import__form textarea{min-width:0;width:100%}.history-import__filters input{min-width:0;width:100%}}
</style>
