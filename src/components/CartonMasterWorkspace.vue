<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { Database, X } from '@lucide/vue'
import CartonMasterSettings from './CartonMasterSettings.vue'
import { cartonMasterApi, masterPaperOptions, defaultMasterData, defaultNumberRule, emptyMaster, automaticNumberRule, historicalNumberSamples, type MasterRecord, type MasterData, type MasterImportKind, type MasterImportResult } from '@/api/cartonMaster'
import { recognizeNumberTemplates, parseNumberTemplate, describeNumberTemplate } from '@/lib/cartonNumberPatterns'
import { cartonPositionsApi, type CartonLocation } from '@/api/cartonPositions'
import type { CartonCustomerResponse } from '@/api/cartonProcurement'
import { getApiErrorMessage, getApiErrorMessageAsync } from '@/lib/http'
const props = defineProps<{ factoryId: string; customers: CartonCustomerResponse[]; initialTab?: string }>()
const emit = defineEmits<{ changed: []; customers: [row?: CartonCustomerResponse]; use: [MasterRecord] }>()
const workspace = ref(emptyMaster()), busy = ref(false), error = ref(''), loading = ref(false)
const tab = ref('SETTINGS'), search = ref(''), customer = ref(''), editing = ref(false), editingId = ref('')
const statusFilter = ref('ALL'), preferredOnly = ref(false)
const warehouseDeleting = ref(false)
const warehouseEditing = ref(false), warehouseOriginal = ref(''), locationWarehouseLocked = ref(false)
const sourceRow = ref<MasterRecord | null>(null), locationRow = ref<CartonLocation | null>(null)
const container = ref<HTMLElement | null>(null)
const importKind = ref<MasterImportKind | null>(null), importFile = ref<File | null>(null)
const importPreview = ref<MasterImportResult | null>(null), importError = ref(''), importBusy = ref(false), importDone = ref(false)
const importLabels: Record<MasterImportKind, string> = { 'paper-options': '纸品选项', configurations: '货号与包装', locations: '仓库仓位' }
let importGeneration = 0
function openImport(kind: MasterImportKind) {
  importGeneration++; importKind.value = kind; importFile.value = null; importPreview.value = null
  importError.value = ''; importDone.value = false; importBusy.value = false
}
function closeImport() { if (!importBusy.value) { importGeneration++; importKind.value = null } }
function chooseImportFile(event: Event) {
  importGeneration++; importPreview.value = null; importError.value = ''; importDone.value = false
  importFile.value = (event.target as HTMLInputElement).files?.[0] || null
}
async function downloadTemplate(kind: MasterImportKind) {
  const factory = props.factoryId
  try {
    const blob = await cartonMasterApi.template(factory, kind)
    if (factory !== props.factoryId) return
    const url = URL.createObjectURL(blob), anchor = document.createElement('a')
    anchor.href = url; anchor.download = `${importLabels[kind]}导入模板.xlsx`
    anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e) {
    const message = await getApiErrorMessageAsync(e)
    if (factory === props.factoryId) error.value = message
  }
}
async function processImport(apply = false) {
  if (importBusy.value || !importKind.value || !importFile.value) return
  const factory = props.factoryId, kind = importKind.value, file = importFile.value, version = ++importGeneration
  const preview = importPreview.value
  if (apply && (!preview || preview.errors.length || importDone.value)) return
  importBusy.value = true; importError.value = ''
  try {
    if (!/\.(xlsx|xlsm)$/i.test(file.name) || file.size > 5 * 1024 * 1024) throw new Error('请选择不超过 5 MB 的 .xlsx 或 .xlsm 文件')
    const result = apply ? await cartonMasterApi.importApply(factory, kind, file, preview!.preview_token)
      : await cartonMasterApi.importPreview(factory, kind, file)
    if (factory !== props.factoryId || version !== importGeneration) return
    importPreview.value = result
    if (apply) { importDone.value = true; await load(); if (factory === props.factoryId) emit('changed') }
  } catch (e) {
    if (factory === props.factoryId && version === importGeneration) { importError.value = getApiErrorMessage(e); importPreview.value = null }
  } finally { if (version === importGeneration) importBusy.value = false }
}
let returnFocus: HTMLElement | null = null
watch(() => props.initialTab, value => { tab.value = value === 'CONFIG' ? 'CONFIG' : 'SETTINGS' }, { immediate: true })
watch(() => editing.value || !!locationRow.value || !!sourceRow.value || warehouseEditing.value || !!importKind.value, async open => {
  if (open) {
    returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    container.value?.querySelector<HTMLElement>('[role="dialog"] button:not(:disabled), [role="dialog"] input:not(:disabled)')?.focus()
  } else returnFocus?.focus()
})
function dialogKeys(event: KeyboardEvent) {
  const dialog = (event.target as HTMLElement).closest('[role="dialog"]')
  if (!dialog) return
  if (event.key === 'Escape') {
    event.stopPropagation(); event.preventDefault()
    if (!busy.value && !importBusy.value) { editing.value = false; locationRow.value = null; sourceRow.value = null; warehouseEditing.value = false; closeImport() }
  }
  if (event.key === 'Tab') {
    const nodes = [...dialog.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]')]
    const first = nodes[0], last = nodes[nodes.length - 1]
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }
}
const paperOnly = ref(false)
const paperFields = { paper_types: 'packaging_type', paper_qualities: 'paper_quality', specifications: 'specification' } as const
const paperBaseline: Record<keyof typeof paperFields, string[]> = { paper_types: [], paper_qualities: [], specifications: [] }
const paperOptionText = reactive({ paper_types: '', paper_qualities: '', specifications: '' })
const paperOptionLabels = { paper_types: '纸品类型', paper_qualities: '纸质', specifications: '规格' }
const form = reactive({ kind: 'CONFIG' as MasterRecord['kind'], code: '', customer_code: '', status: 'ACTIVE' as MasterRecord['status'], preferred: false, expected_revision: 0, reason: '', data: defaultMasterData() })
const warehouseForm = reactive({ name: '', bin: '', reason: '', revisions: {} as Record<string, number> })
const locationForm = reactive({ warehouse: '', bin_code: '', status: 'ACTIVE', expected_revision: 1, reason: '' })
const originalStatus = ref('ACTIVE'), originalLocationStatus = ref('ACTIVE')
const originalHardCheck = ref(false)
const ruleScopeLocked = ref(false)
const specificReason = computed(() => form.kind === 'ACCESS' || (form.kind === 'RULE' &&
  (originalHardCheck.value || [form.data.contract_rule.mode, form.data.item_rule.mode, form.data.customer_po_rule.mode].includes('BLOCK'))))
const suggestedReason = computed(() => specificReason.value ? '' : !editingId.value ? '新增基础资料'
  : form.status !== originalStatus.value ? (form.status === 'ACTIVE' ? '启用基础资料' : '停用不再使用资料')
  : form.kind === 'RULE' ? '调整默认交期及编号规则' : form.kind === 'WORKSHOP' ? '调整车间资料' : '修正基础资料')
watch(suggestedReason, (value, previous) => { if (!form.reason.trim() || form.reason === previous) form.reason = value })
const suggestedLocationReason = computed(() => !locationRow.value?.id ? '新增仓库仓位'
  : locationForm.status !== originalLocationStatus.value ? (locationForm.status === 'ACTIVE' ? '启用仓库仓位' : '停用不再使用仓位') : '调整仓库仓位名称')
watch(suggestedLocationReason, (value, previous) => { if (!locationForm.reason.trim() || locationForm.reason === previous) locationForm.reason = value })
type FormatKey = 'contract_rule' | 'item_rule' | 'customer_po_rule'
const templateText = reactive({ contract_rule: '', item_rule: '', customer_po_rule: '' })
const recognizedText = reactive({ contract_rule: '', item_rule: '', customer_po_rule: '' })
const recognitionErrors = reactive({ contract_rule: '', item_rule: '', customer_po_rule: '' })
const recognitionHints = reactive({ contract_rule: '', item_rule: '', customer_po_rule: '' })
async function resetNumberRule(key: FormatKey) {
  if (busy.value) return
  const label = key === 'customer_po_rule' ? '客户 PO' : key === 'contract_rule' ? '合同号' : '货号'
  const row = workspace.value.records.find(record => record.id === editingId.value && record.kind === 'RULE')
  if (row?.data[key]?.mode === 'BLOCK' && form.reason.trim().length < 4) {
    error.value = `删除${label}强制检查前，请填写具体说明`
    return
  }
  const factory = props.factoryId, editingSession = editingId.value, customerCode = form.customer_code
  busy.value = true; error.value = ''
  try {
    const data = { ...defaultMasterData(), ...JSON.parse(JSON.stringify(row?.data || {})), [key]: { ...defaultNumberRule(), reset: true } } as MasterData
    const saved = await cartonMasterApi.save(factory, {
      kind: 'RULE', code: row?.code || '', customer_code: customerCode,
      status: row?.status || 'ACTIVE', preferred: row?.preferred || false, expected_revision: row?.revision || 0,
      reason: row?.data[key]?.mode === 'BLOCK' ? form.reason.trim() : `删除旧${label}格式，等待下次正式订单重新记录`, data,
    }, row?.id || '')
    if (factory !== props.factoryId || editingId.value !== editingSession || form.customer_code !== customerCode) return
    workspace.value.records = row
      ? workspace.value.records.map(record => record.id === row.id ? { ...saved, sources: record.sources } : record)
      : [...workspace.value.records, saved]
    editingId.value = saved.id
    form.expected_revision = saved.revision
    originalHardCheck.value = ['contract_rule', 'item_rule', 'customer_po_rule'].some(rule => saved.data[rule as FormatKey]?.mode === 'BLOCK')
    emit('changed')
  } catch (e) { error.value = getApiErrorMessage(e); return }
  finally { busy.value = false }
  form.data[key] = { ...defaultNumberRule(), reset: true }
  templateText[key] = ''; recognizedText[key] = ''; recognitionErrors[key] = ''
  recognitionHints[key] = `旧${label}格式已删除；历史订单保留。下次确认并锁定该客户订单时，如编号可识别，将自动记录新格式。`
}
function identifyNumberRule(key: FormatKey) {
  const rule = form.data[key], raw = (rule.sample_text || '').trim()
  recognitionErrors[key] = ''; recognitionHints[key] = ''
  if (rule.reset && !raw) {
    recognitionHints[key] = '旧格式已删除；请填写新样例，或等待下次正式订单自动记录。'
    return
  }
  try {
    const values = raw ? raw.split(/[\n\r,，;；]+/).map(value => value.trim()).filter(Boolean) : historicalNumberSamples(workspace.value.records, form.customer_code, key)
    const result = recognizeNumberTemplates(values)
    templateText[key] = result.templates.join('\n')
    Object.assign(rule, { templates: result.templates, frozen: result.templates.length > 0, reset: false, source: raw ? 'MANUAL' : values.length ? 'HISTORY' : 'NONE', sample_count: result.sampleCount })
    recognizedText[key] = raw
    if (!values.length) recognitionHints[key] = key === 'customer_po_rule' ? '该客户的正式历史订单未填写客户 PO，请粘贴客户 PO 样例；不会用合同号代替。' : '该客户暂无可识别的正式历史编号，请填写完整样例。'
  } catch (e) { recognitionErrors[key] = e instanceof Error ? e.message : '无法识别样例' }
}
function editNumberTemplate(key: FormatKey) { recognizedText[key] = (form.data[key].sample_text || '').trim(); recognitionErrors[key] = ''; recognitionHints[key] = ''; form.data[key].reset = false }
function resetNumberRules() {
  if (form.kind !== 'RULE') return
  for (const key of ['contract_rule', 'item_rule', 'customer_po_rule'] as const) {
    form.data[key] = defaultNumberRule(); templateText[key] = ''; recognizedText[key] = ''
    if (form.customer_code) identifyNumberRule(key)
  }
}

const itemText = ref(''), warehouseText = ref('')
const tabs = [{ id: 'CONFIG', label: '货号与包装' }, { id: 'CONTRACT', label: '合同登记' }, { id: 'RULE', label: '客户与交期规则' }, { id: 'WORKSHOP', label: '车间' }, { id: 'LOCATION', label: '仓库与仓位' }, { id: 'ACCESS', label: '仓库维护授权' }]
const rows = computed(() => workspace.value.records.filter(r => r.kind === 'CONFIG' && (statusFilter.value === 'ALL' || r.status === statusFilter.value) && (!preferredOnly.value || r.preferred) && JSON.stringify([r.code, r.data]).toLowerCase().includes(search.value.toLowerCase())))
function editRule(code: string) {
  const existing = workspace.value.records.find(r => r.kind === 'RULE' && r.customer_code === code)
  edit(existing, 'RULE', code)
}
function editPaperOptions() {
  editRule('')
  paperOnly.value = true
  const existing = workspace.value.records.find(row => row.kind === 'RULE' && !row.customer_code)
  form.data = { ...defaultMasterData(), ...JSON.parse(JSON.stringify(existing?.data || {})) }
  form.reason = '维护纸品选项'
  for (const key of Object.keys(paperFields) as (keyof typeof paperFields)[]) {
    paperBaseline[key] = masterPaperOptions(workspace.value.records, paperFields[key], workspace.value.paper_history)
    paperOptionText[key] = paperBaseline[key].join('\n')
  }
}
function createRecord(kind: MasterRecord['kind'], code = '') { edit(undefined, kind, code) }
const customerName = (code: string) => props.customers.find(c => c.customer_code === code)?.customer_name || (code || '本厂默认')
const canPlace = (warehouse: string) => workspace.value.can_manage || workspace.value.warehouses.includes(warehouse)
let generation = 0
async function load() {
  const version = ++generation; loading.value = true; error.value = ''
  try { const data = await cartonMasterApi.get(props.factoryId); if (version === generation) workspace.value = data }
  catch (e) { if (version === generation) error.value = getApiErrorMessage(e) }
  finally { if (version === generation) loading.value = false }
}
watch(() => props.factoryId, () => { importGeneration++; importKind.value = null; importPreview.value = null; importFile.value = null; importBusy.value = false; workspace.value = emptyMaster(); editing.value = false; locationRow.value = null; sourceRow.value = null; warehouseEditing.value = false; customer.value = ''; void load() }, { immediate: true })
function edit(row?: MasterRecord, kind: MasterRecord['kind'] = 'CONFIG', code = customer.value) {
  paperOnly.value = false
  ruleScopeLocked.value = (row?.kind || kind) === 'RULE'
  editingId.value = row?.id || ''; error.value = ''
  originalStatus.value = row?.status || 'ACTIVE'
  originalHardCheck.value = row?.data.contract_rule?.mode === 'BLOCK' || row?.data.item_rule?.mode === 'BLOCK' || row?.data.customer_po_rule?.mode === 'BLOCK'
  Object.assign(form, { kind: row?.kind || kind, code: row?.code || '', customer_code: row?.customer_code ?? code, status: row?.status || 'ACTIVE', preferred: row?.preferred || false, expected_revision: row?.revision || 0, reason: '', data: { ...defaultMasterData(), ...JSON.parse(JSON.stringify(row?.data || {})), contract_rule: { ...defaultNumberRule(), ...row?.data.contract_rule }, customer_po_rule: { ...defaultNumberRule(), ...row?.data.customer_po_rule }, item_rule: { ...defaultNumberRule(), ...row?.data.item_rule } } })
  for (const key of ['paper_types', 'paper_qualities', 'specifications'] as const) paperOptionText[key] = (form.data[key] || []).join('\n')
  itemText.value = (form.data.item_nos || []).join('\n'); warehouseText.value = (form.data.warehouses || []).join('\n')
  if (!['CONTRACT', 'RULE'].includes(form.kind)) form.customer_code = ''
  for (const key of ['contract_rule', 'item_rule', 'customer_po_rule'] as const) {
    const rule = form.data[key]
    recognitionErrors[key] = ''; recognitionHints[key] = ''
    if (automaticNumberRule(rule)) rule.mode = 'AUTO'
    templateText[key] = (rule.templates || []).join('\n'); recognizedText[key] = (rule.sample_text || '').trim()
    if (form.kind === 'RULE' && form.customer_code && rule.mode === 'AUTO' && !rule.frozen && !rule.reset) identifyNumberRule(key)
  }
  form.reason = suggestedReason.value
  editing.value = true
}
function addPaper() { form.data.lines.push({ packaging_type: '', paper_quality: '', specification: '', dimension_unit: 'cm', unit: '个', usage_quantity: '' }) }
async function save() {
  if (busy.value) return
  busy.value = true; error.value = ''; const factory = props.factoryId
  try {
    if (form.kind === 'RULE' && form.customer_code) for (const key of ['contract_rule', 'item_rule', 'customer_po_rule'] as const) {
      const rule = form.data[key]
      if (rule.mode === 'OFF') continue
      if (recognitionErrors[key]) throw new Error('请先处理各编号下的识别提示，或重置对应格式')
      if ((rule.sample_text || '').trim() !== recognizedText[key]) throw new Error('样例已修改，请点击识别格式，或手动修改下方格式后再保存')
      const templates = [...new Set(templateText[key].split('\n').map(t => t.trim()).filter(Boolean))]
      if (templates.length > 20) throw new Error('每项最多保存 20 种格式')
      templates.forEach(parseNumberTemplate)
      rule.templates = templates; rule.frozen = templates.length > 0
    }
    if (!paperOnly.value) {
    form.data.lead_days = form.data.lead_days === null || String(form.data.lead_days) === '' ? null : Number(form.data.lead_days)
    form.data.customer_days = form.data.customer_days === null || String(form.data.customer_days) === '' ? null : Number(form.data.customer_days)
    }
    if (paperOnly.value) for (const key of Object.keys(paperFields) as (keyof typeof paperFields)[]) {
      const values = [...new Set(paperOptionText[key].split('\n').map(value => value.trim()).filter(Boolean))]
      form.data[key] = values
      const hiddenKey = `hidden_${key}` as const
      form.data[hiddenKey] = [...new Set([...(form.data[hiddenKey] || []), ...paperBaseline[key]])].filter(value => !values.includes(value))
    }
    if (!paperOnly.value) {
    form.data.item_nos = itemText.value.split(/[\n,，]/).map(s => s.trim()).filter(Boolean)
    form.data.warehouses = warehouseText.value.split(/[\n,，]/).map(s => s.trim()).filter(Boolean)
    }
    await cartonMasterApi.save(factory, { ...form, data: JSON.parse(JSON.stringify(form.data)) as MasterData }, editingId.value)
    if (factory !== props.factoryId) return
    editing.value = false; await load(); emit('changed')
  } catch (e) { error.value = getApiErrorMessage(e) } finally { busy.value = false }
}
function editLocation(row?: CartonLocation, warehouse?: string) {
  locationWarehouseLocked.value = Boolean(warehouse)
  originalLocationStatus.value = row?.status || 'ACTIVE'
  locationRow.value = row || { id: '', factory_id: props.factoryId, warehouse: '', bin_code: '', label: '' }
  Object.assign(locationForm, { warehouse: warehouse || row?.warehouse || workspace.value.warehouses[0] || '', bin_code: row?.bin_code || '', status: row?.status || 'ACTIVE', expected_revision: row?.revision || 1, reason: '' })
  locationForm.reason = suggestedLocationReason.value
}
async function saveLocation() {
  if (busy.value || !locationRow.value) return
  busy.value = true; error.value = ''; const factory = props.factoryId
  try {
    if (locationRow.value.id) await cartonMasterApi.location(factory, locationRow.value.id, locationForm)
    else await cartonPositionsApi.create(factory, locationForm.warehouse, locationForm.bin_code, locationForm.reason)
    if (factory !== props.factoryId) return
    locationRow.value = null; await load(); emit('changed')
  } catch (e) { error.value = getApiErrorMessage(e) } finally { busy.value = false }
}
function editWarehouse(name = '') {
  if (!workspace.value.can_manage) return
  warehouseDeleting.value = false
  warehouseOriginal.value = name
  warehouseForm.name = name; warehouseForm.bin = ''; warehouseForm.reason = name ? '修改仓库名称' : '添加仓库资料'
  warehouseForm.revisions = Object.fromEntries(workspace.value.locations.filter(row => row.warehouse === name).map(row => [row.id, row.revision || 1]))
  error.value = ''; warehouseEditing.value = true
}
async function saveWarehouse() {
  if (busy.value || !workspace.value.can_manage) return
  const factory = props.factoryId, original = warehouseOriginal.value
  busy.value = true; error.value = ''
  try {
    if (warehouseDeleting.value && original) await cartonMasterApi.deleteWarehouse(factory, original, warehouseForm.revisions, warehouseForm.reason)
    else if (original) await cartonMasterApi.renameWarehouse(factory, original, warehouseForm.name, warehouseForm.revisions, warehouseForm.reason)
    else await cartonMasterApi.createWarehouse(factory, warehouseForm.name, warehouseForm.bin, warehouseForm.reason)
    if (factory !== props.factoryId) return
    warehouseEditing.value = false; await load(); emit('changed')
  } catch (e) { if (factory === props.factoryId) error.value = getApiErrorMessage(e) }
  finally { busy.value = false }
}

</script>

<template>
  <section ref="container" class="space-y-4" aria-label="纸箱基础资料" @keydown="dialogKeys">
    <article class="rounded-xl border border-teal-200 bg-white p-4 shadow-sm">
      <div class="flex items-center justify-between gap-3"><div><h2 class="flex items-center gap-2 text-lg font-bold"><Database class="size-5 text-teal-700" />基础资料</h2><p class="mt-1 text-xs text-slate-500">历史正式订单自动加入；落单可直接带出，不同配置保留并提醒。修改仅影响后续引用。</p></div><button type="button" :disabled="loading" class="rounded-lg border px-3 py-2 text-xs" @click="load">刷新资料</button></div>
      <p class="mt-3 text-xs text-teal-700">{{ workspace.can_manage ? '可维护本厂基础资料：客户、规则、货号包装、车间及仓位；修改会留痕。' : workspace.warehouses.length ? `可维护仓库：${workspace.warehouses.join('、')}；其他基础资料可查询和引用。` : '可查询和引用资料；修改由主管或授权负责人处理。' }}</p>
    </article>
    <div class="flex gap-1 rounded-xl border border-slate-200 bg-white p-2" role="tablist" aria-label="基础资料页面">
      <button v-for="item in [{ id: 'SETTINGS', label: '基础设置' }, { id: 'CONFIG', label: '货号与包装' }]" :key="item.id" type="button" role="tab" :aria-selected="tab === item.id" class="rounded-lg px-5 py-2 text-sm font-bold" :class="tab === item.id ? 'bg-teal-700 text-white' : 'text-slate-600 hover:bg-slate-50'" @click="tab = item.id">{{ item.label }}</button>
    </div>
    <p v-if="error && !editing && !locationRow" role="alert" class="text-sm text-red-700">{{ error }}</p>
    <div v-if="loading" class="p-10 text-center text-slate-500">正在整理历史与基础资料…</div>
    <CartonMasterSettings v-else-if="tab === 'SETTINGS'" :key="factoryId" :workspace="workspace" :customers="customers" @rule="editRule" @paper="editPaperOptions" @paper-template="downloadTemplate('paper-options')" @paper-import="openImport('paper-options')" @location-template="downloadTemplate('locations')" @location-import="openImport('locations')" @edit="edit($event)" @create="createRecord" @location="editLocation" @warehouse="editWarehouse" @customer="emit('customers', $event)" @source="sourceRow = $event" />
    <article v-else class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm" aria-label="货号与包装资料">
      <div class="flex flex-wrap items-center gap-3 border-b bg-slate-50 p-3">
        <span class="text-xs text-slate-500">本厂货号共用，不绑定客户</span>
        <input v-model="search" aria-label="基础资料搜索" placeholder="查找货号、产品名称、纸品或规格" class="h-9 min-w-56 flex-1 rounded-lg border bg-white px-3 text-xs">
        <select v-model="statusFilter" aria-label="货号资料状态" class="h-9 rounded-lg border px-3 text-xs"><option value="ALL">全部状态</option><option value="ACTIVE">启用</option><option value="INACTIVE">停用</option></select><label class="text-xs"><input v-model="preferredOnly" type="checkbox"> 仅推荐</label><button type="button" class="h-9 rounded-lg border px-3 text-xs" @click="customer = ''; search = ''; statusFilter = 'ALL'; preferredOnly = false">清空筛选</button>
        <button v-if="workspace.can_manage" type="button" class="h-9 rounded-lg bg-teal-700 px-4 text-xs font-bold text-white" @click="edit()">新增货号与包装</button>
        <button v-if="workspace.can_manage" type="button" class="h-9 rounded-lg border px-3 text-xs" @click="downloadTemplate('configurations')">下载货号包装模板</button>
        <button v-if="workspace.can_manage" type="button" class="h-9 rounded-lg border px-3 text-xs" @click="openImport('configurations')">导入货号与包装</button>
      </div>
      <p class="border-b border-teal-100 bg-teal-50/60 px-3 py-2 text-xs leading-5 text-teal-800">一个货号可以有多个纸品：手工新增时点击“添加纸品”；模板导入时每个纸品写一行，同一套纸品使用相同的“货号 + 配置组”，并在每行重复填写相同的产品名称、推荐、状态和备注。</p>
      <div class="overflow-x-auto"><table class="w-full min-w-[960px] text-left text-xs"><thead class="bg-slate-50 text-slate-500"><tr><th class="p-3">包装方式</th><th class="p-3">货号 / 产品名称</th><th class="p-3">纸品类型 / 纸质 / 规格 / 单位 / 装箱数</th><th class="p-3">来源 / 状态</th><th class="p-3 text-right">操作</th></tr></thead>
        <tbody class="divide-y divide-slate-100"><tr v-for="row in rows" :key="row.id" class="hover:bg-slate-50/60"><td class="p-3 font-semibold">{{ row.data.packing_name || '其他包装' }}</td><td class="p-3"><b class="font-mono">{{ row.code }}</b><div class="mt-1 text-slate-500">{{ row.data.product_name }}</div></td><td class="p-3"><div v-for="(line, i) in row.data.lines" :key="i" class="mb-1">{{ line.packaging_type }} · {{ line.paper_quality }} · {{ line.specification }} {{ line.dimension_unit }} · {{ line.unit }} · 每箱 {{ line.usage_quantity }} 件</div><span v-if="workspace.records.filter(r => r.kind === 'CONFIG' && r.code === row.code).length > 1" class="text-amber-700">存在不同配置，落单时请核对</span><p class="mt-1 text-slate-500">{{ row.data.note }}</p></td><td class="p-3"><div>{{ row.maintained ? '高级权限维护' : '历史自动加入' }}</div><div class="mt-1" :class="row.status === 'ACTIVE' ? 'text-teal-700' : 'text-slate-400'">{{ row.status === 'ACTIVE' ? '启用' : '停用' }}{{ row.preferred ? ' · 推荐' : '' }}</div><button v-if="row.sources.length" type="button" class="mt-1 text-teal-700 underline" @click="sourceRow = row">{{ row.sources.length }} 条历史来源</button></td><td class="p-3"><div class="flex justify-end gap-2 whitespace-nowrap"><button v-if="workspace.can_manage" type="button" class="rounded-lg border px-3 py-2" :aria-label="`修改基础资料 ${row.code}`" @click="edit(row)">修改</button><button v-if="row.status === 'ACTIVE'" type="button" class="rounded-lg border border-teal-200 px-3 py-2 text-teal-700" @click="emit('use', row)">用于落单</button></div></td></tr><tr v-if="!rows.length"><td colspan="5" class="p-12 text-center text-slate-400">暂无对应资料；正式历史订单中的货号与纸品配置会自动加入。</td></tr></tbody>
      </table></div>
    </article>
    <div v-if="importKind" class="fixed inset-0 z-[65] flex items-center justify-center bg-slate-950/45 p-4" data-testid="master-import-backdrop">
      <div role="dialog" aria-modal="true" aria-label="基础资料模板导入" class="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-xl bg-white p-5 shadow-xl">
        <div class="flex items-center justify-between"><h3 class="font-bold">导入{{ importLabels[importKind] }}</h3><button type="button" :disabled="importBusy" aria-label="关闭导入" @click="closeImport"><X class="size-5" /></button></div>
        <p class="my-3 text-xs leading-6 text-slate-500">下载的是空白模板，请先在“导入数据”页填写至少一行，再选择文件、预览核对并确认导入。说明与示例不会导入。支持 .xlsx / .xlsm，最多 5 MB、1000 行。<template v-if="importKind === 'locations'">仓库与仓位均填真实文本；范围可填 A1-A25、B01-B03，补零宽度须一致。展开后合计最多 1000 个仓位。</template><template v-else-if="importKind === 'configurations'">一个货号多个纸品时，每个纸品写一行；相同“货号 + 配置组”组成一套配置，同组产品名称、推荐、状态和备注须重复填写且保持一致。</template><template v-else>纸品类型、纸质每格单一项，规格分别填写长、宽、高。</template></p>
        <input type="file" accept=".xlsx,.xlsm" aria-label="选择基础资料模板文件" :disabled="importBusy" @change="chooseImportFile">
        <p v-if="importFile" class="mt-2 text-xs">文件：{{ importFile.name }}</p>
        <p v-if="importError" role="alert" class="mt-3 text-sm text-red-700">{{ importError }}</p>
        <div v-if="importPreview" class="mt-4 rounded-lg border p-3 text-sm" aria-live="polite">
          <p>{{ importDone ? '导入完成' : '预览结果' }}：{{ importDone ? '已新增' : '待新增' }} {{ importPreview.added }} · 跳过 {{ importPreview.skipped }} · 错误 {{ importPreview.errors.length }}</p>
          <p v-if="importKind === 'paper-options'" class="mt-1 text-xs text-slate-500">按选项数统计；恢复曾隐藏的选项计入新增。</p>
          <p v-if="importKind === 'locations'" class="mt-1 text-xs text-slate-500">按展开后的仓位数统计；已有启用或停用仓位只跳过，不修改状态、库存或历史。</p>
          <ul v-if="importPreview.errors.length" role="alert" class="mt-2 max-h-48 overflow-auto text-red-700"><li v-for="(message, i) in importPreview.errors" :key="i">{{ message }}</li></ul>
          <ul class="mt-2 max-h-48 overflow-auto text-xs text-slate-600"><li v-for="(message, i) in importPreview.details" :key="i">{{ message }}</li></ul>
        </div>
        <div class="mt-4 flex justify-end gap-2"><button type="button" class="rounded-lg border px-4 py-2 text-sm" :disabled="importBusy" @click="closeImport">关闭</button><button v-if="!importDone" type="button" class="rounded-lg border px-4 py-2 text-sm" :disabled="importBusy || !importFile" @click="processImport()">{{ importBusy ? '处理中…' : '预览导入' }}</button><button v-if="!importDone" type="button" class="rounded-lg bg-teal-700 px-4 py-2 text-sm text-white disabled:opacity-40" :disabled="importBusy || !importPreview || !!importPreview.errors.length" @click="processImport(true)">确认导入</button></div>
      </div>
    </div>
    <div v-if="editing" class="fixed inset-0 z-[65] flex items-center justify-center bg-slate-950/45 p-4">
      <form role="dialog" aria-modal="true" aria-label="维护基础资料" class="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-xl" @submit.prevent="save">
        <div class="flex items-center justify-between border-b p-4"><h3 class="font-bold">{{ paperOnly ? '添加 / 修改纸品选项' : (editingId ? '修改' : '新增') + tabs.find(t => t.id === form.kind)?.label }}</h3><button type="button" :disabled="busy" aria-label="关闭基础资料编辑" @click="editing = false"><X class="size-5" /></button></div>
        <div class="min-h-0 overflow-y-auto p-5 text-xs" :class="form.kind === 'RULE' ? 'space-y-3' : 'space-y-4'">
          <div v-if="!paperOnly" class="grid gap-3" :class="form.kind === 'RULE' ? 'sm:grid-cols-[2fr_1fr]' : 'sm:grid-cols-3'">
            <label v-if="['CONTRACT','RULE'].includes(form.kind)">客户<select v-model="form.customer_code" @change="resetNumberRules" :disabled="!!editingId || ruleScopeLocked" :required="form.kind !== 'RULE'" aria-label="资料所属客户" class="mt-1 h-9 w-full rounded-lg border px-2"><option value="">{{ form.kind === 'RULE' ? '本厂默认规则' : '请选择客户' }}</option><option v-for="c in customers" :key="c.id" :value="c.customer_code">{{ c.customer_name }}</option></select></label>
            <label v-if="form.kind !== 'RULE' && form.kind !== 'ACCESS'">{{ form.kind === 'CONFIG' ? '货号' : form.kind === 'CONTRACT' ? '合同号' : '车间名称' }}<input v-model="form.code" :disabled="!!editingId && form.kind !== 'WORKSHOP'" required maxlength="128" aria-label="资料编号名称" class="mt-1 h-9 w-full rounded-lg border px-2"></label>
            <label v-if="form.kind === 'ACCESS'">授权人员<select v-model="form.code" :disabled="!!editingId" required aria-label="仓库授权人员" class="mt-1 h-9 w-full rounded-lg border px-2"><option value="">选择人员</option><option v-for="u in workspace.users" :key="u.id" :value="u.id">{{ u.name }}</option></select></label>
            <label>状态<select v-model="form.status" aria-label="基础资料状态" class="mt-1 h-9 w-full rounded-lg border px-2"><option value="ACTIVE">启用</option><option value="INACTIVE">停用</option></select></label>
          </div>
          <template v-if="form.kind === 'CONFIG'">
            <p class="text-xs text-teal-700">包装方式：{{ form.data.packing_name || '保存后自动识别' }} · 首次为标准装，后续不同配置请核对。</p>
            <div class="flex items-center gap-3"><label class="flex-1">产品名称<input v-model="form.data.product_name" maxlength="255" aria-label="基础资料产品名称" class="mt-1 h-9 w-full rounded-lg border px-2"></label><label><input v-model="form.preferred" type="checkbox"> 设为推荐配置</label><button type="button" class="rounded-lg border px-3 py-2" @click="addPaper">添加纸品</button></div>
            <div class="overflow-x-auto"><table class="w-full min-w-[800px] text-left"><thead class="bg-slate-50"><tr><th class="p-2">纸品类型</th><th class="p-2">纸质</th><th class="p-2">规格</th><th class="p-2">尺寸单位</th><th class="p-2">计量单位</th><th class="p-2">每箱装产品数</th><th></th></tr></thead><tbody><tr v-for="(line, i) in form.data.lines" :key="i"><td class="p-1"><input v-model="line.packaging_type" required aria-label="资料纸品类型" class="h-9 w-full rounded border px-2"></td><td class="p-1"><input v-model="line.paper_quality" aria-label="资料纸质" class="h-9 w-full rounded border px-2"></td><td class="p-1"><input v-model="line.specification" aria-label="资料规格" class="h-9 w-full rounded border px-2"></td><td class="p-1"><select v-model="line.dimension_unit" aria-label="资料尺寸单位" class="h-9 rounded border"><option value="">未记录</option><option>mm</option><option>cm</option><option>inch</option></select></td><td class="p-1"><input v-model="line.unit" required aria-label="资料计量单位" class="h-9 w-16 rounded border px-2"></td><td class="p-1"><input v-model="line.usage_quantity" type="number" min="0.00000001" step="any" required aria-label="资料装箱数" class="h-9 w-24 rounded border px-2"></td><td><button type="button" class="text-red-600" @click="form.data.lines.splice(i, 1)">移除</button></td></tr></tbody></table></div>
          </template>
          <label v-if="form.kind === 'CONTRACT'" class="block">关联货号（每行一个）<textarea v-model="itemText" aria-label="合同关联货号" rows="4" class="mt-1 w-full rounded-lg border p-2" /></label>
          <label v-if="form.kind === 'ACCESS'" class="block">允许维护的仓库（每行一个，与仓库名称一致）<textarea v-model="warehouseText" aria-label="允许维护仓库" rows="4" class="mt-1 w-full rounded-lg border p-2" /><span class="text-slate-500">人员还须具备本厂库存业务权限；授权不会允许修改其他基础资料。</span></label>
          <template v-if="form.kind === 'RULE'">
            <section v-if="paperOnly" class="rounded-lg border border-teal-100 bg-teal-50/30 p-3" aria-label="维护纸品选项">
              <b>纸品选项</b><p class="mt-1 text-slate-500">每行一项，直接添加、修改或移除。保存订单后自动积累；移除的旧值不再推荐，旧订单和包装配置保持原样。</p>
              <div class="mt-3 grid gap-3 sm:grid-cols-3"><label v-for="(label, key) in paperOptionLabels" :key="key">{{ label }}<textarea v-model="paperOptionText[key]" :aria-label="`基础${label}选项`" rows="10" class="mt-1 w-full rounded-lg border bg-white p-2" placeholder="每行一项" /></label></div>
            </section>

            <div v-if="!paperOnly" class="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
              <div class="grid gap-3 sm:grid-cols-2">
                <label class="font-semibold">采购安全提前量 <span class="font-normal text-slate-500">（自然日）</span><input v-model="form.data.lead_days" type="number" min="0" max="365" aria-label="默认采购提前天数" :placeholder="form.customer_code ? '空白沿用本厂，未设置时为 3 天' : '默认 3 天'" class="mt-1 h-9 w-full rounded-lg border bg-white px-2"><span class="mt-1 block font-normal leading-5 text-slate-500">计划交期＝客户交期－提前天数。例如客户 20 日要货，提前 3 天，计划 17 日到货。</span></label>
                <label class="font-semibold">客户交期建议 <span class="font-normal text-slate-500">（下单后自然日）</span><input v-model="form.data.customer_days" :disabled="form.data.customer_days_disabled" type="number" min="0" max="730" aria-label="客户交期建议天数" :placeholder="form.data.customer_days_disabled ? '已关闭建议' : form.customer_code ? '空白沿用本厂，未设置则不建议' : '空白不提供建议'" class="mt-1 h-9 w-full rounded-lg border bg-white px-2 disabled:bg-slate-100 disabled:text-slate-400"><span class="mt-1 block font-normal leading-5 text-slate-500">建议客户交期＝下单日期＋建议天数。仅供人工采纳，以客户实际要求为准。</span></label>
              </div>
              <div class="mt-2 flex flex-wrap items-center justify-between gap-2 text-slate-500"><span>仅新单采用；旧单及追加保留原提前量。</span><label class="inline-flex items-center gap-1.5"><input v-model="form.data.customer_days_disabled" type="checkbox" aria-label="关闭客户交期建议"> 不提供交期建议</label></div>
            </div>
            <div v-if="form.customer_code" class="grid items-start gap-3 md:grid-cols-2" aria-label="合同与货号格式概览">
              <div v-for="key in (['contract_rule','item_rule','customer_po_rule'] as const)" :key="key" class="min-w-0 overflow-hidden rounded-lg border border-slate-200">
                <div class="flex items-center justify-between gap-2 border-b bg-slate-50 px-3 py-2"><b>{{ key === 'customer_po_rule' ? '客户 PO 格式（选填）' : key === 'contract_rule' ? '合同号格式' : '货号格式' }}</b>
                  <select v-model="form.data[key].mode" :aria-label="`${key === 'customer_po_rule' ? '客户 PO（选填）' : key === 'contract_rule' ? '合同号' : '货号'}格式检查方式`" class="h-8 max-w-[65%] rounded border bg-white px-2"><option value="AUTO">样例识别 · 软提醒</option><option value="OFF">不检查</option><option value="WARN">手动规则 · 软提醒</option><option value="BLOCK">手动规则 · 强制检查</option></select>
                </div>
                <div class="px-3 pt-2"><button type="button" :disabled="busy" :aria-label="`删除旧${key === 'customer_po_rule' ? '客户 PO（选填）' : key === 'contract_rule' ? '合同号' : '货号'}格式`" class="text-xs font-semibold text-red-600 disabled:opacity-40" @click="resetNumberRule(key)">删除旧格式</button></div>
                <p v-if="recognitionErrors[key]" role="alert" class="px-3 pt-2 text-xs text-red-600">{{ key === 'customer_po_rule' ? '客户 PO' : key === 'contract_rule' ? '合同号' : '货号' }}识别失败：{{ recognitionErrors[key] }}</p>
                <p v-if="recognitionHints[key]" class="px-3 pt-2 text-xs text-amber-700">{{ recognitionHints[key] }}</p>
                <div v-if="form.data[key].mode !== 'OFF'" class="p-3">
                  <div class="max-h-24 overflow-y-auto break-words leading-5" :aria-label="`${key === 'customer_po_rule' ? '客户 PO（选填）' : key === 'contract_rule' ? '合同号' : '货号'}当前格式`">
                    <template v-if="templateText[key]"><div v-for="(format, index) in templateText[key].split('\n').filter(Boolean)" :key="index" class="mb-1 last:mb-0"><p class="font-semibold text-teal-800">{{ describeNumberTemplate(format) }}</p><p class="font-mono text-[11px] text-slate-500">{{ format }}</p></div></template>
                    <p v-else-if="form.data[key].mode !== 'AUTO'" class="text-slate-600">前缀 {{ form.data[key].prefix || '不限' }} · {{ form.data[key].min_length }}–{{ form.data[key].max_length }} 字 · {{ form.data[key].characters === 'DIGITS' ? '纯数字' : form.data[key].characters === 'ALNUM_DASH' ? '字母数字及 -_' : '原有合法字符' }}</p>
                    <p v-else class="text-slate-500">尚未识别到格式，展开填写样例。</p>
                  </div>
                  <details class="mt-2 border-t border-slate-100 pt-2">
                    <summary class="cursor-pointer font-semibold text-teal-700">修改格式</summary>
                    <div class="mt-3 space-y-2 text-slate-600">
                      <label class="block">编号样例 <span class="text-slate-400">{{ form.data[key].reset ? '（每行一个；删除后留空不会重新读取旧订单）' : '（每行一个；留空参考历史订单）' }}</span><textarea v-model="form.data[key].sample_text" :aria-label="`${key === 'customer_po_rule' ? '客户 PO（选填）' : key === 'contract_rule' ? '合同号' : '货号'}识别样例`" rows="2" maxlength="12000" class="mt-1 w-full rounded border bg-white p-2" :placeholder="key === 'contract_rule' ? 'SC700149169/600\nSC700143393/1600' : key === 'customer_po_rule' ? '粘贴该客户的完整客户 PO' : '粘贴该客户的完整货号'" /></label>
                      <div class="flex flex-wrap items-center gap-2"><button type="button" :disabled="busy" class="rounded-lg border border-teal-200 bg-white px-3 py-1.5 text-teal-700" :aria-label="`识别${key === 'customer_po_rule' ? '客户 PO（选填）' : key === 'contract_rule' ? '合同号' : '货号'}格式`" @click="identifyNumberRule(key)">识别格式</button><span class="text-[11px] text-slate-500">识别参考：{{ form.data[key].source === 'MANUAL' ? '填写样例' : form.data[key].source === 'HISTORY' ? '历史订单' : '尚未识别' }} · {{ form.data[key].sample_count || 0 }} 个编号</span></div>
                      <label class="block">格式结果（可修改，每行一种）<textarea v-model="templateText[key]" :aria-label="`${key === 'customer_po_rule' ? '客户 PO（选填）' : key === 'contract_rule' ? '合同号' : '货号'}固定格式`" rows="2" maxlength="5200" class="mt-1 w-full rounded border bg-white p-2 font-mono" placeholder="SC{9}/{3,4}" @input="editNumberTemplate(key)" /></label>
                      <p class="text-[11px] leading-5 text-slate-500">{9} = 9 位数字；{3,4} = 3 或 4 位。文字及符号按原样匹配；留空不执行分段检查。</p>
                      <details v-if="form.data[key].mode !== 'AUTO' && !templateText[key]"><summary class="cursor-pointer">原有前缀、长度规则</summary><div class="mt-2 grid grid-cols-2 gap-2"><label>前缀<input v-model="form.data[key].prefix" class="h-9 w-full rounded border px-2"></label><label>最少长度<input v-model.number="form.data[key].min_length" type="number" min="0" max="128" class="h-9 w-full rounded border px-2"></label><label>最多长度<input v-model.number="form.data[key].max_length" type="number" min="1" max="128" class="h-9 w-full rounded border px-2"></label><label>允许字符<select v-model="form.data[key].characters" class="h-9 w-full rounded border"><option value="ANY">原有合法字符</option><option value="DIGITS">纯数字</option><option value="ALNUM_DASH">字母数字及 -_</option></select></label></div></details>
                    </div>
                  </details>
                </div>
                <p v-else class="p-3 text-slate-500">当前不检查该编号格式。</p>
              </div>
            </div>
            <p v-if="form.customer_code" class="text-[11px] text-teal-700">格式保存后固定；以后需在此修改，不随新订单改变。</p>
          </template>
          <div :class="form.kind === 'RULE' ? 'grid items-start gap-3 sm:grid-cols-2' : 'space-y-4'">
            <label v-if="!paperOnly" class="block">备注 <span v-if="form.kind === 'RULE'" class="text-slate-400">（选填）</span><textarea v-model="form.data.note" :rows="form.kind === 'RULE' ? 1 : 2" maxlength="1000" class="mt-1 w-full rounded-lg border p-2" :class="form.kind === 'RULE' ? 'h-9 min-h-9' : ''" /></label>
            <label class="block">{{ specificReason ? '具体说明（关键设置，需自行填写）' : '操作说明（默认已填写，可修改）' }}<input v-model="form.reason" required minlength="4" maxlength="500" aria-label="基础资料修改原因" class="mt-1 h-9 w-full rounded-lg border px-2"></label>
          </div>
          <p v-if="error" role="alert" class="text-red-700">{{ error }}</p>
        </div>
        <div class="flex justify-end border-t p-4"><button :disabled="busy" class="rounded-lg bg-teal-700 px-5 py-2 text-sm font-bold text-white disabled:opacity-50">{{ busy ? '保存中…' : '保存基础资料' }}</button></div>
      </form>
    </div>
    <div v-if="warehouseEditing" class="fixed inset-0 z-[65] flex items-center justify-center bg-slate-950/45 p-4">
      <form role="dialog" aria-modal="true" aria-label="维护仓库" class="w-full max-w-lg space-y-4 rounded-xl bg-white p-5 text-sm" @submit.prevent="saveWarehouse">
        <div class="flex justify-between"><b>{{ warehouseDeleting ? '删除未使用仓库' : warehouseOriginal ? '修改仓库' : '添加仓库' }}</b><button type="button" :disabled="busy" @click="warehouseEditing = false">关闭</button></div>
        <template v-if="warehouseDeleting">
          <div class="rounded-lg border border-amber-200 bg-amber-50 p-3 leading-6"><b>确认删除仓库 {{ warehouseOriginal }}？</b><p>将删除该仓库及其全部 {{ Object.keys(warehouseForm.revisions).length }} 个仓位。</p><p>仅从未使用的空仓可以删除。有库存、收料、出入库、调仓或盘点记录的仓库会保留，请改为停用仓位。</p><p>该仓库的维护授权也会移除。</p></div>
        </template>
        <template v-else>
          <label class="block">仓库名称<input v-model="warehouseForm.name" required maxlength="64" aria-label="仓库名称" class="mt-1 h-9 w-full rounded border px-2"></label>
          <label v-if="!warehouseOriginal" class="block">首个仓位<input v-model="warehouseForm.bin" required maxlength="64" aria-label="首个仓位" placeholder="例如 A01" class="mt-1 h-9 w-full rounded border px-2"></label>
          <p class="text-xs text-slate-500">{{ warehouseOriginal ? '整组仓位同步更名，保留原仓位编号、库存和历史记录；维护授权随仓库更名保留。' : '先填写一个仓位建立仓库，之后可在该仓库旁继续添加仓位。' }}</p>
        </template>
        <label class="block">{{ warehouseDeleting ? '删除原因' : '维护原因' }}<input v-model="warehouseForm.reason" required minlength="4" maxlength="500" aria-label="仓库维护原因" class="mt-1 h-9 w-full rounded border px-2"></label>
        <p v-if="error" role="alert" class="text-red-700">{{ error }}</p>
        <div class="flex justify-between gap-3">
          <button v-if="warehouseOriginal && !warehouseDeleting" type="button" :disabled="busy" class="rounded-lg border border-red-200 px-4 py-2 text-red-700" @click="warehouseDeleting = true; warehouseForm.reason = '删除未使用空仓'; error = ''">删除仓库</button>
          <button v-if="warehouseDeleting" type="button" :disabled="busy" class="rounded-lg border px-4 py-2" @click="warehouseDeleting = false; warehouseForm.reason = '修改仓库名称'; error = ''">返回修改</button>
          <button :disabled="busy" class="ml-auto rounded-lg px-4 py-2 text-white" :class="warehouseDeleting ? 'bg-red-700' : 'bg-teal-700'">{{ warehouseDeleting ? '确认删除仓库' : '保存仓库' }}</button>
        </div>
      </form>
    </div>
    <div v-if="locationRow" class="fixed inset-0 z-[65] flex items-center justify-center bg-slate-950/45 p-4"><form role="dialog" aria-modal="true" aria-label="维护仓位" class="w-full max-w-lg space-y-4 rounded-xl bg-white p-5 text-sm" @submit.prevent="saveLocation"><div class="flex justify-between"><b>仓库／仓位维护</b><button type="button" :disabled="busy" @click="locationRow = null">关闭</button></div><label class="block">仓库<input v-model="locationForm.warehouse" :readonly="locationWarehouseLocked" required maxlength="64" aria-label="维护仓库名称" class="mt-1 h-9 w-full rounded border px-2"></label><label class="block">仓位<input v-model="locationForm.bin_code" :required="!!locationRow.bin_code || !locationRow.id" maxlength="64" aria-label="维护仓位编号" class="mt-1 h-9 w-full rounded border px-2"></label><label v-if="locationRow.id" class="block">状态<select v-model="locationForm.status" aria-label="仓位状态" class="ml-2 h-9 rounded border"><option value="ACTIVE">启用</option><option value="INACTIVE">停用</option></select></label><p class="text-xs text-slate-500">更名不移动库存；停用后禁止新增入库，可继续清退及受控纠错。有库存请先核对是否需要调仓。</p><input v-model="locationForm.reason" required minlength="4" placeholder="维护原因，至少 4 个字" aria-label="仓位维护原因" class="h-9 w-full rounded border px-2"><p v-if="error" role="alert" class="text-red-700">{{ error }}</p><button :disabled="busy" class="rounded-lg bg-teal-700 px-4 py-2 text-white">保存仓位</button></form></div>
    <div v-if="sourceRow" class="fixed inset-0 z-[65] flex items-center justify-center bg-slate-950/45 p-4" @click.self="sourceRow = null"><div role="dialog" aria-modal="true" aria-label="基础资料历史来源" class="max-h-[85vh] w-full max-w-3xl overflow-auto rounded-xl bg-white p-5"><div class="flex justify-between"><b>{{ sourceRow.code }} · 历史来源</b><button type="button" @click="sourceRow = null">关闭</button></div><div v-for="(source, i) in sourceRow.sources" :key="i" class="border-b py-3 text-xs"><b>{{ source.order_date }} · {{ source.contract_no }} · {{ source.item_no }}</b><div class="mt-1 text-slate-500">{{ source.order_no }}</div><div v-for="(line, j) in source.configuration.lines" :key="j" class="mt-1">{{ line.packaging_type }} {{ line.paper_quality }} · {{ line.specification }} {{ line.dimension_unit }} · {{ line.unit }} · 每箱 {{ line.usage_quantity }} 件</div></div></div></div>
  </section>
</template>
