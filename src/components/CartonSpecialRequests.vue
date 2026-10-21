<script setup lang="ts">
import CartonOrderPaperTable from '@/components/CartonOrderPaperTable.vue'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import CartonSpecialManualReceipt from './CartonSpecialManualReceipt.vue'
import CartonSpecialOrderActions from './CartonSpecialOrderActions.vue'
import type { CartonLocation } from '@/api/cartonPositions'
import { cartonSpecialRequestsApi as api, type SpecialRequest, type SpecialLine, type SpecialSave, type SpecialWorkspace, type SpecialAction, type AttachmentRole, type SpecialShipment, type MarkMode, type MarkOption } from '@/api/cartonSpecialRequests'
import { getApiErrorMessage } from '@/lib/http'

const props = withDefaults(defineProps<{ factoryId: string; viewerKey?: string; supplier?: boolean; mode?: 'requests' | 'receiving' | 'detail' | 'marks'; requestId?: string; lineId?: string; previewRequest?: SpecialRequest; requesterName?: string; createNew?: boolean; initialKind?: 'SAMPLE' | 'WORKSHOP_MISC'; initialAction?: 'receive' | 'edit' | 'adjust' | 'confirm' | 'cancel' | 'delete'; search?: string }>(), { mode: 'requests' })
const emit = defineEmits<{ changed: []; close: []; dispatch: []; 'open-delivery': [deliveryNoteNo: string] }>()
const workspace = ref<SpecialWorkspace>({ items: [], total: 0, can_create: false })
const selected = ref<SpecialRequest | null>(null), loading = ref(false), detailLoading = ref(false), busy = ref(false)
const error = ref(''), success = ref(''), search = ref(''), kindFilter = ref(''), statusFilter = ref('')
const editing = ref(false), editingId = ref(''), editRevision = ref(0)
const adjusting = ref(false), adjustmentReason = ref(''), confirmOpen = ref(false), receiptOpen = ref(false), manualStarted = ref(false)
let appliedInitialAction = ''
let formDraftKey = ''
const pendingShipments = computed(() => selected.value?.shipments.filter(shipment => shipment.lines.some(line => scaled(line.remaining_quantity) > 0n)) || [])
const locations = computed<CartonLocation[]>(() => (options.value.locations || []).map(location => ({ ...location, factory_id: props.factoryId, warehouse: location.warehouse || '', bin_code: location.bin_code || '', status: 'ACTIVE' })))
const shippedLine = (id?: string) => Boolean(id && selected.value?.shipments.some(shipment => shipment.lines.some(line => line.request_line_id === id)))
const blankLine = (): SpecialLine => ({ packaging_type: '', paper_quality: '', specification: '', dimension_unit: 'cm', quantity: '', unit: '个', item_no: '', mark_mode: 'PENDING' })
const form = reactive({ kind: 'SAMPLE' as SpecialSave['kind'], requester_name: '', purpose: '', workshop_id: '', customer_code: '', required_date: '', lines: [blankLine()] })
const markModes: Record<MarkMode, string> = { EXISTING: '使用已有箱唛', UPLOAD: '上传新箱唛', NONE: '无需箱唛 / 空白箱', PENDING: '资料待补' }
const markChoices = ref<MarkOption[]>([]), markAsset = ref<Record<string, string>>({}), markAttachment = ref<Record<string, string>>({})
const attachmentLine = ref('')
const markUploadLine = ref(''), markFiles = ref<Record<string, File | null>>({}), markPickerLine = ref(''), markSearch = ref('')
const previewFile = ref<{ url: string; name: string; image: boolean } | null>(null)
const filteredMarkChoices = computed(() => markChoices.value.filter(asset => `${asset.file_name} ${asset.contract_number || ''}`.toLowerCase().includes(markSearch.value.trim().toLowerCase())))
function closePreview() { if (previewFile.value) URL.revokeObjectURL(previewFile.value.url); previewFile.value = null }
const quantity = (value?: string) => value ? value.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '') : '0'
const attachmentFile = ref<File | null>(null), messageBody = ref(''), cancelConfirm = ref(false)
const deleteConfirm = ref(false), deleteReason = ref('')
let controller = new AbortController(), generation = 0, listSequence = 0, detailSequence = 0
const attempts = new Map<string, string>()
const kinds: Record<string, string> = { SAMPLE: '样板', WORKSHOP_MISC: '车间杂单', SUPPLIER_GIFT: '供应商赠送' }
const statuses: Record<string, string> = { SUBMITTED: '待确认锁单', SENT: '已确认锁定 · 待送货', QUOTED: '已确认锁定 · 待送货', READY: '已确认锁定 · 可送货', PARTIALLY_RECEIVED: '部分验收', COMPLETED: '已完成', CANCELLED: '已取消' }
const pricing: Record<string, string> = { PENDING_QUOTE: '以送货单为准', FREE: '免费', CHARGEABLE: '收费' }
const actions: Record<string, string> = { SEND: '确认并锁单', QUOTE: '供应商报价或免费确认', APPROVE: '内部确认收费报价', CANCEL: '取消需求', SUBMITTED: '提交需求', CREATED: '建立需求', UPDATED: '修改需求', SENT: '确认并锁单', QUOTED: '供应商报价', APPROVED: '内部确认报价', CANCELLED: '取消需求', SHIPPED: '登记送货', RECEIVED: '仓库验收', ATTACHMENT_UPLOADED: '上传资料', MATERIAL_CONFIRMED: '更新确认稿', MESSAGE_ADDED: '发送协作消息', MESSAGE: '发送协作消息', MATERIAL_CHANGED: '更新确认稿', ATTACHMENT_ADDED: '上传资料', RECEIPT_REVERSED: '仓库冲销验收', GIFT_CREATED: '供应商声明赠送', FREE_CONFIRMED: '供应商免费确认' }
const rows = computed(() => workspace.value.items.filter(row => (!kindFilter.value || row.kind === kindFilter.value) && (!statusFilter.value || row.status === statusFilter.value) && (!(props.search ?? search.value).trim() || [row.request_no, row.title, row.requester_name, row.customer_name, row.purpose, ...row.lines.flatMap(line => [line.packaging_type, line.paper_quality, line.specification, line.item_no])].join(' ').toLocaleLowerCase().includes((props.search ?? search.value).trim().toLocaleLowerCase())) && (props.mode !== 'receiving' || row.shipments?.some(ship => ship.lines.some(line => Number(line.remaining_quantity) > 0)))))
const can = (flag: keyof SpecialRequest['permissions']) => selected.value?.permissions?.[flag] === true
const remaining = (line: SpecialLine) => Math.max(0, Number(line.quantity) - Number(line.received_quantity || 0))
const progress = (line: SpecialLine) => Number(line.quantity) > 0 ? Math.min(100, Math.round(Number(line.received_quantity || 0) / Number(line.quantity) * 100)) : 0
const detailSummary = computed(() => {
  const units = new Map<string, { required: number; received: number; remaining: number }>()
  for (const line of selected.value?.lines || []) {
    const group = units.get(line.unit) || { required: 0, received: 0, remaining: 0 }
    group.required += Math.round(Number(line.quantity) * 10000)
    group.received += Math.round(Number(line.received_quantity || 0) * 10000)
    group.remaining += Math.round(remaining(line) * 10000)
    units.set(line.unit, group)
  }
  const text = (field: 'required' | 'received' | 'remaining') => [...units].map(([unit, totals]) => `${(totals[field] / 10000).toLocaleString('zh-CN', { maximumFractionDigits: 4 })} ${unit}`).join(' · ')
  return { required: text('required'), received: text('received'), remaining: text('remaining') }
})
const options = computed(() => workspace.value.options ?? {})
function requestKey(signature: string) { if (!attempts.has(signature)) attempts.set(signature, crypto.randomUUID()); return attempts.get(signature)! }
function reset() {
  generation++; listSequence++; detailSequence++; controller.abort(); controller = new AbortController()
  appliedInitialAction = ''; formDraftKey = ''; adjusting.value = false; adjustmentReason.value = ''; confirmOpen.value = false; receiptOpen.value = false; manualStarted.value = false
  workspace.value = { items: [], total: 0, can_create: false }; selected.value = null; editing.value = false
  loading.value = false; detailLoading.value = false; busy.value = false; error.value = ''; success.value = ''; search.value = ''; kindFilter.value = ''; statusFilter.value = ''
  messageBody.value = ''; attachmentFile.value = null; cancelConfirm.value = false; deleteConfirm.value = false; deleteReason.value = ''; attempts.clear(); markChoices.value = []; markPickerLine.value = ''; markUploadLine.value = ''; markFiles.value = {}; closePreview()
}
watch(() => [props.factoryId, props.viewerKey, props.supplier, props.mode], () => { reset(); void load() }, { immediate: true, flush: 'sync' })
watch(() => [props.requestId, busy.value] as const, ([id, pending]) => { if (!pending && id && props.factoryId && selected.value?.id !== id) void select(id) })
watch(() => props.previewRequest, row => { if (props.mode === 'detail' && row?.factory_id === props.factoryId) initDetail(row) })
watch(() => props.initialAction, () => applyInitialAction())
onBeforeUnmount(() => { generation++; controller.abort(); closePreview() })
async function load() {
  if (!props.factoryId) return
  if (props.mode === 'detail' && props.previewRequest) { if (props.previewRequest.factory_id === props.factoryId) initDetail(props.previewRequest); return }
  const token = generation, sequence = ++listSequence; loading.value = true; error.value = ''
  try { const result = await api.list(props.factoryId, props.supplier, controller.signal); if (token === generation && sequence === listSequence) { workspace.value = result; if (props.createNew && !selected.value && !editing.value) openForm(); else if (props.requestId && !selected.value && !editing.value) void select(props.requestId) } }
  catch (cause) { if (token === generation && sequence === listSequence) { workspace.value = { items: [], total: 0, can_create: false }; error.value = getApiErrorMessage(cause) } }
  finally { if (token === generation && sequence === listSequence) loading.value = false }
}
function initDetail(row: SpecialRequest) {
  if (selected.value?.id !== row.id) { manualStarted.value = false; appliedInitialAction = '' }
  confirmOpen.value = false; receiptOpen.value = false
  selected.value = row; editing.value = false; cancelConfirm.value = false; deleteConfirm.value = false; deleteReason.value = ''; messageBody.value = ''; attachmentFile.value = null
  markUploadLine.value = ''; markPickerLine.value = ''; markFiles.value = {}; closePreview(); attachmentLine.value = row.lines[0]?.id || ''; markAsset.value = {}; markAttachment.value = {}
}
async function select(id: string) {
  if (busy.value) return
  const token = generation, sequence = ++detailSequence; selected.value = null; editing.value = false; detailLoading.value = true; error.value = ''
  try { const row = await api.detail(props.factoryId, id, props.supplier, controller.signal); if (token === generation && sequence === detailSequence) { initDetail(row); applyInitialAction() } }
  catch (cause) { if (token === generation && sequence === detailSequence) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation && sequence === detailSequence) detailLoading.value = false }
}
function applyInitialAction() {
  if (!selected.value || !props.initialAction || props.supplier) return
  const key = `${selected.value.id}:${props.initialAction}`
  if (key === appliedInitialAction) return
  appliedInitialAction = key
  if (props.initialAction === 'receive') openReceipt()
  else if (props.initialAction === 'confirm' && can('can_confirm')) confirmOpen.value = true
  else if (props.initialAction === 'edit' || props.initialAction === 'adjust') openForm(true, props.initialAction === 'adjust')
  else if (props.initialAction === 'cancel' && can('can_cancel')) cancelConfirm.value = true
  else if (props.initialAction === 'delete' && can('can_delete')) deleteConfirm.value = true
}
function detailAction(action?: 'receive' | 'edit' | 'adjust' | 'confirm' | 'cancel' | 'delete') {
  if (busy.value) return
  if (action === 'receive') openReceipt()
  else if (action === 'confirm' && can('can_confirm')) confirmOpen.value = true
  else if (action === 'edit' || action === 'adjust') openForm(true, action === 'adjust')
  else if (action === 'cancel' && can('can_cancel')) cancelConfirm.value = true
  else if (action === 'delete' && can('can_delete')) deleteConfirm.value = true
}
function openReceipt() {
  if (busy.value || props.supplier) return
  receiptOpen.value = true
  if (!pendingShipments.value.length && can('can_manual_receive')) manualStarted.value = true
}
function manualSaved(row: SpecialRequest) { busy.value = false; manualStarted.value = false; initDetail(row); success.value = '实际收料已登记，供应商原价及本次记录等待供应商核实。'; emit('changed'); void load() }
function openForm(edit = false, adjust = false) {
  if (busy.value || (edit ? !can(adjust ? 'can_adjust' : 'can_edit') : props.supplier || !workspace.value.can_create)) return
  const draftKey = `${edit ? selected.value?.id : 'new'}:${edit ? selected.value?.revision : 0}:${adjust}`
  if (formDraftKey === draftKey) { editing.value = true; return }
  formDraftKey = draftKey
  detailSequence++; detailLoading.value = false
  const row = edit ? selected.value : null
  editingId.value = row?.id || ''; editRevision.value = row?.revision || 0; adjusting.value = adjust; adjustmentReason.value = ''
  Object.assign(form, { kind: row?.kind || (props.initialKind || 'SAMPLE'), requester_name: row?.requester_name || props.requesterName || '', purpose: row?.purpose || '', workshop_id: row?.workshop_id || '', customer_code: row?.customer_code || '', required_date: row?.required_date || '', lines: row ? row.lines.map(({ id, packaging_type, paper_quality, specification, dimension_unit, quantity, unit, item_no, mark_mode }) => ({ id, packaging_type, paper_quality, specification, dimension_unit, quantity, unit, item_no, mark_mode: mark_mode || 'PENDING' })) : [blankLine()] })
  editing.value = true; error.value = ''; success.value = ''
}
function validDecimal(value: string, positive = true) { return /^\d{1,14}(\.\d{1,4})?$/.test(value) && (positive ? scaled(value) > 0n : scaled(value) >= 0n) }
function scaled(value: string) { if (!/^\d{1,14}(\.\d{1,4})?$/.test(value)) return 0n; const [whole = '0', fraction = ''] = value.split('.'); return BigInt(whole) * 10000n + BigInt(fraction.padEnd(4, '0')) }

async function save() {
  if (busy.value || (editingId.value ? !can(adjusting.value ? 'can_adjust' : 'can_edit') : !workspace.value.can_create)) return
  if (adjusting.value && adjustmentReason.value.trim().length < 4) { error.value = '请填写至少四字的调整原因。'; return }
  if (!form.requester_name.trim() || !form.required_date || (form.kind === 'WORKSHOP_MISC' && !form.workshop_id)) { error.value = '请填写需求人和需求日期；车间杂单还须选择车间。'; return }
  if (!form.lines.length || form.lines.some(line => !line.packaging_type.trim() || !line.paper_quality.trim() || !line.specification.trim() || !line.dimension_unit || !line.unit.trim() || !validDecimal(String(line.quantity)))) { error.value = '每条纸品须填写类型、纸质、规格、尺寸单位、计数单位和大于零的数量（最多四位小数）。'; return }
  if (adjusting.value && form.lines.some(line => scaled(line.quantity) < scaled(selected.value?.lines.find(source => source.id === line.id)?.received_quantity || '0'))) { error.value = '调整后的需求数量不能少于累计有效入库数量。'; return }
  const payload = { factory_id: props.factoryId, ...structuredClonePlain(form), ...(editingId.value ? { expected_revision: editRevision.value } : {}), ...(adjusting.value ? { reason: adjustmentReason.value.trim() } : {}) }
  const signature = JSON.stringify(['save', editingId.value, payload]), token = generation; busy.value = true; error.value = ''
  try { const body = { ...payload, request_id: requestKey(signature) }; const row = adjusting.value ? await api.adjust(editingId.value, { ...body, reason: adjustmentReason.value.trim() }, controller.signal) : await api.save(body, props.supplier, editingId.value, controller.signal); if (token === generation) { attempts.delete(signature); formDraftKey = ''; initDetail(row); success.value = adjusting.value ? '订单调整已保存，历史订单及已收批次保留。' : editingId.value ? '订单修改已保存。' : '订单已创建，等待负责人确认并锁单。'; emit('changed'); if (props.mode === 'detail' && !props.supplier) emit('close'); else await load() } }
  catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) busy.value = false }
}
function structuredClonePlain<T>(value: T): T { return JSON.parse(JSON.stringify(value)) as T }
async function act(action: string, flag: keyof SpecialRequest['permissions'], extra: Record<string, unknown> = {}) {
  const row = selected.value; if (!row || busy.value || !can(flag)) return
  const signature = JSON.stringify([row.id, action, row.revision, extra]), token = generation
  const body: SpecialAction = { factory_id: props.factoryId, expected_revision: row.revision, request_id: requestKey(signature), ...extra }
  busy.value = true; error.value = ''
  try { const result = await api.action(row.id, action, body, props.supplier, controller.signal); if (token === generation) { attempts.delete(signature); initDetail(result); success.value = '单据已更新。'; emit('changed'); await load() } }
  catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) busy.value = false }
}
async function deleteOrder() {
  if (!can('can_delete') || deleteReason.value.trim().length < 4) return
  await act('delete', 'can_delete', { reason: deleteReason.value.trim() })
  if (selected.value?.deleted) { selected.value = null; emit('close') }
}
function openReceive(shipment: SpecialShipment) { if (can('can_receive') && !busy.value) emit('open-delivery', shipment.delivery_note_no) }
async function upload(lineId = '') {
  const role: AttachmentRole = lineId ? 'DRAFT' : 'REFERENCE'
  const row = selected.value, file = lineId ? markFiles.value[lineId] : attachmentFile.value; if (!row || !file || busy.value || !can('can_attach')) return
  if (lineId && !/\.(pdf|xlsx|png|jpe?g|webp)$/i.test(file.name)) { error.value = '箱唛制作稿请上传 PDF、XLSX 或静态图片；Word、演示文稿请放在备注附件。'; return }
  if (!file.size || file.size > 10 * 1024 * 1024) { error.value = '文件不能为空，且单个文件不能超过 10 MiB。'; return }
  const signature = JSON.stringify([row.id, 'attach', row.revision, lineId || attachmentLine.value, role, file.name, file.size, file.lastModified]), token = generation; busy.value = true; error.value = ''
  try { const result = await api.attach(row.id, { factory_id: props.factoryId, request_id: requestKey(signature), expected_revision: row.revision, line_id: lineId || attachmentLine.value }, role, file, props.supplier, controller.signal); if (token === generation) { attempts.delete(signature); initDetail(result); success.value = lineId ? '箱唛已上传，待我方确认本单使用。' : '备注附件已上传。'; emit('changed'); await load() } }
  catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) busy.value = false }
}
async function download(id: string, filename: string) {
  const row = selected.value, token = generation; if (!row || busy.value) return
  try { const blob = await api.download(props.factoryId, row.id, id, props.supplier, controller.signal); if (token !== generation) return; const url = URL.createObjectURL(blob), anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) }
  catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
}
async function loadMarkOptions(lineId: string) {
  markPickerLine.value = lineId; markSearch.value = ''; markChoices.value = []
  const token = generation, rowId = selected.value?.id; try { const result = await api.markOptions(props.factoryId, controller.signal, props.supplier, rowId); if (token === generation && selected.value?.id === rowId) markChoices.value = result } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
}
function setMark(line: SpecialLine, mode: MarkMode) {
  if (!line.id) return
  void act(`lines/${line.id}/mark`, props.supplier && mode === 'EXISTING' ? 'can_attach' : 'can_confirm_material', { mark_mode: mode, asset_id: mode === 'EXISTING' ? markAsset.value[line.id] || '' : '', asset_revision: mode === 'EXISTING' ? markChoices.value.find(asset => asset.id === markAsset.value[line.id!])?.revision || 0 : 0, attachment_id: mode === 'UPLOAD' ? markAttachment.value[line.id] || '' : '' })
}
function pendingDrafts(lineId?: string) { return selected.value?.attachments.filter(file => file.line_id === lineId && file.role === 'DRAFT' && !selected.value?.attachments.some(confirmed => confirmed.line_id === lineId && confirmed.role === 'CONFIRMED' && confirmed.sha256 && confirmed.sha256 === file.sha256 && (confirmed.version ?? 0) >= (file.version ?? 0))) || [] }
function chooseMarkFile(lineId: string, event: Event) { markFiles.value[lineId] = (event.target as HTMLInputElement).files?.[0] || null }
async function preview(id: string, filename: string) {
  const row = selected.value, token = generation; if (!row || busy.value) return
  try { const blob = await api.download(props.factoryId, row.id, id, props.supplier, controller.signal); if (token !== generation || selected.value?.id !== row.id) return; closePreview(); previewFile.value = { url: URL.createObjectURL(blob), name: filename, image: /\.(png|jpe?g|webp|gif)$/i.test(filename) } }
  catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
}
const canPreview = (filename: string) => /\.(pdf|png|jpe?g|webp|gif)$/i.test(filename)
function chooseFile(event: Event) { attachmentFile.value = (event.target as HTMLInputElement).files?.[0] || null }
async function refresh() { if (busy.value) return; const id = selected.value?.id, token = generation; await load(); if (token === generation && id && selected.value?.id === id) await select(id) }
defineExpose({ refresh })
</script>

<template>
  <section class="carton-special space-y-3" :aria-label="mode === 'marks' ? '订单箱唛确认' : '订单工作面板'" :aria-busy="loading || busy">
    <div v-if="mode !== 'detail'" class="border border-slate-200 bg-white flex flex-wrap items-center justify-between gap-3 rounded-xl p-4">
      <div><h2 class="text-base font-bold">{{ mode === 'marks' ? '订单箱唛确认' : mode === 'receiving' ? '样板与杂单 · 送货验收' : '样板与杂单订单' }}</h2><p class="mt-1 text-xs text-muted-foreground">{{ mode === 'marks' ? '选择样板或杂单，维护各纸品的箱唛要求和本单使用稿。正单沿用资料库中的订单关联。' : '创建订单 → 确认并锁单 → 供应商送货 → 仓库验收。' }}</p></div>
      <div class="flex flex-wrap gap-2"><Button variant="outline" :disabled="loading || busy" @click="load">{{ loading ? '正在刷新…' : '刷新' }}</Button><Button v-if="!supplier && workspace.can_create && mode === 'requests'" :disabled="busy" @click="openForm()">新建订单</Button></div>
    </div>
    <p v-if="!factoryId" class="rounded-xl border bg-card p-5 text-sm text-muted-foreground">请先选择服务厂区。</p>
    <p v-if="error" role="alert" class="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{{ error }}</p>
    <p v-if="success" role="status" class="rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm text-primary">{{ success }}</p>
    <div v-if="mode !== 'detail' && props.search === undefined" class="flex flex-wrap items-end gap-2 rounded-xl border bg-card p-3">
      <label class="grow">搜索<input v-model="search" aria-label="搜索特殊申请" placeholder="单号、纸品、需求人或客户"></label>
      <label>类型<select v-model="kindFilter" aria-label="特殊申请类型"><option value="">全部类型</option><option v-for="(label, key) in kinds" :key="key" :value="key">{{ label }}</option></select></label>
      <label>状态<select v-model="statusFilter" aria-label="特殊申请状态"><option value="">全部状态</option><option v-for="(label, key) in statuses" :key="key" :value="key">{{ label }}</option></select></label>
    </div>
    <form v-if="editing" class="min-w-0 space-y-5 bg-white p-1 sm:p-2" aria-label="订单表单" @submit.prevent="save">
      <div class="flex flex-wrap items-center justify-between gap-2"><h3 class="font-bold">{{ adjusting ? '调整订单' : editingId ? '修改订单' : supplier ? '供应商免费赠送声明' : `新建${kinds[form.kind]}订单` }}</h3><Button type="button" variant="ghost" :disabled="busy" @click="editing = false; if (!editingId) emit('close')">{{ editingId ? '返回订单' : '关闭表单' }}</Button></div>
      <h4 class="text-sm font-bold text-slate-950">订单资料</h4>
      <fieldset :disabled="busy" class="grid min-w-0 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <label>类型 *<select v-model="form.kind" aria-label="申请类型" :disabled="supplier || Boolean(editingId)"><option v-if="!supplier" value="SAMPLE">样板</option><option v-if="!supplier" value="WORKSHOP_MISC">车间杂单</option><option v-if="supplier" value="SUPPLIER_GIFT">供应商赠送</option></select></label>
        <label>需求人 *<input v-model="form.requester_name" aria-label="需求人" maxlength="100" required></label>
        <label>{{ supplier ? '赠送 / 预计送货日期' : '需求日期' }} *<input v-model="form.required_date" aria-label="需求日期" type="date" required></label>
        <label>客户（选填）<select v-model="form.customer_code" aria-label="申请客户" :disabled="adjusting"><option value="">不关联客户</option><option v-for="customer in options.customers || []" :key="customer.customer_code" :value="customer.customer_code">{{ customer.customer_name }} · {{ customer.customer_code }}</option></select></label>
        <label v-if="form.kind === 'WORKSHOP_MISC'">车间 *<select v-model="form.workshop_id" aria-label="需求车间" :disabled="adjusting" required><option value="">选择车间</option><option v-for="workshop in options.workshops || []" :key="workshop.id" :value="workshop.id">{{ workshop.name }}</option></select><span v-if="!options.workshops?.length" class="text-xs text-muted-foreground">暂无可用车间，请联系基础资料维护人员。</span></label>
        <label class="sm:col-span-2 lg:col-span-3">用途（选填）<textarea v-model="form.purpose" aria-label="申请用途" maxlength="2000" rows="2" /></label>
      </fieldset>
      <section class="overflow-hidden rounded-xl border border-slate-200" aria-label="纸品明细">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3"><h4 class="text-sm font-bold text-slate-950">纸品明细</h4><Button type="button" size="sm" variant="outline" :disabled="busy || form.lines.length >= 50" @click="form.lines.push(blankLine())">新增纸品</Button></div>
        <div class="space-y-3 p-4"><div v-for="(line, index) in form.lines" :key="index" class="space-y-3 rounded-xl border border-slate-200 bg-slate-50/50 p-3">
          <div class="flex items-center justify-between gap-2"><b class="text-xs text-slate-700">纸品 {{ index + 1 }}</b><Button type="button" size="sm" variant="ghost" :disabled="busy || form.lines.length <= 1 || adjusting && shippedLine(line.id)" @click="form.lines.splice(index, 1)">移除</Button></div>
          <div class="grid min-w-0 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label>纸品类型 *<input v-model="line.packaging_type" :aria-label="`纸品${index + 1}类型`" :disabled="busy || adjusting && shippedLine(line.id)" placeholder="例如 外箱、内箱、配卡" required></label>
            <label>纸质 *<input v-model="line.paper_quality" :aria-label="`纸品${index + 1}纸质`" :disabled="busy || adjusting && shippedLine(line.id)" placeholder="例如 A=B" required></label>
            <label>规格 *<input v-model="line.specification" :aria-label="`纸品${index + 1}规格`" :disabled="busy || adjusting && shippedLine(line.id)" placeholder="例如 30×20×10" required></label>
            <label>尺寸单位 *<select v-model="line.dimension_unit" :aria-label="`纸品${index + 1}尺寸单位`" :disabled="busy || adjusting && shippedLine(line.id)"><option value="cm">cm</option><option value="in">in</option></select></label>
            <label>需求数量 *<input v-model="line.quantity" :aria-label="`纸品${index + 1}数量`" :disabled="busy" inputmode="decimal" required></label>
            <label>单位 *<input v-model="line.unit" :aria-label="`纸品${index + 1}单位`" :disabled="busy || adjusting && shippedLine(line.id)" required></label>
            <label>货号（选填）<input v-model="line.item_no" :aria-label="`纸品${index + 1}货号`" :disabled="busy || adjusting && shippedLine(line.id)"></label>
          </div><p class="text-xs text-slate-500">箱唛要求及使用稿统一在箱唛资料库维护。</p>
        </div></div>
      </section>
      <label v-if="adjusting">调整原因 *<textarea v-model="adjustmentReason" aria-label="订单调整原因" rows="2" maxlength="1000" required :disabled="busy" placeholder="请说明调整内容和原因，至少四字" /></label>
      <div class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4"><p class="text-xs text-slate-500">{{ adjusting ? '调整保留原版本和已收批次；客户、类型、车间及已送货纸品身份不能改变。' : editingId ? '锁单前可以修改订单资料。' : '保存后进入待确认；核对订单和箱唛后确认并锁单。' }}</p><Button type="submit" :disabled="busy">{{ busy ? '正在保存…' : adjusting ? '保存订单调整' : editingId ? '保存订单修改' : '创建待确认订单' }}</Button></div>
    </form>
    <div v-else :class="mode === 'detail' ? 'min-w-0' : 'grid min-w-0 gap-3 xl:grid-cols-[minmax(300px,0.8fr)_minmax(0,1.4fr)]'">
      <div v-if="mode !== 'detail'" class="border border-slate-200 bg-white min-w-0 overflow-hidden rounded-xl">
        <div class="border-b px-4 py-3 text-xs text-muted-foreground">当前显示 {{ rows.length }} 条 · 共 {{ workspace.total }} 条</div>
        <p v-if="loading" role="status" class="p-6 text-sm text-muted-foreground">正在读取订单…</p>
        <p v-else-if="!rows.length && !error" class="p-6 text-sm text-muted-foreground">{{ mode === 'receiving' ? '暂无待验收的特殊送货。' : search || kindFilter || statusFilter ? '没有符合筛选条件的订单。' : '暂无订单；提交后由负责人发送给供应商。' }}</p>
        <button v-for="row in rows" v-else :key="row.id" type="button" class="special-row block w-full border-b p-4 text-left last:border-b-0 hover:bg-accent/50" :class="selected?.id === row.id ? 'bg-accent/60' : ''" :aria-pressed="selected?.id === row.id" :disabled="busy" @click="select(row.id)"><span class="flex flex-wrap items-center justify-between gap-2"><b class="text-sm">{{ row.request_no }}</b><span class="rounded-full bg-secondary px-2 py-1 text-[11px]">{{ kinds[row.kind] }}</span></span><span class="mt-2 block text-xs text-muted-foreground break-words">{{ row.request_no }} · {{ row.requester_name }}<template v-if="row.customer_name"> · {{ row.customer_name }}</template></span><span class="mt-2 flex flex-wrap gap-2 text-xs"><span>{{ statuses[row.status] || row.status }}</span></span></button>
      </div>
      <p v-if="detailLoading || loading && mode === 'detail'" role="status" class="rounded-xl border bg-card p-6 text-sm text-muted-foreground">正在读取单据详情…</p>
      <article v-else-if="selected" class="min-w-0 space-y-4 bg-white" aria-label="订单详情">
        <template v-if="mode !== 'marks'">
        <section class="grid gap-x-5 gap-y-3 rounded-xl border border-emerald-200 bg-emerald-50/60 px-4 py-3 text-[12px] sm:grid-cols-2 lg:grid-cols-4" aria-label="订单资料">
          <h3 class="sr-only">订单资料</h3>
          <div><span class="text-slate-500">客户</span><b class="ml-2 text-slate-900">{{ selected.customer_name || '未关联客户' }}</b></div>
          <div><span class="text-slate-500">订单类型</span><b class="ml-2 text-teal-700">{{ kinds[selected.kind] }}</b></div>
          <div><span class="text-slate-500">需求人</span><b class="ml-2 text-slate-900">{{ selected.requester_name }}</b></div>
          <div><span class="text-slate-500">状态</span><span class="ml-2 inline-flex rounded-full bg-white px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset" :class="selected.status === 'CANCELLED' ? 'text-red-700 ring-red-200' : selected.status === 'PARTIALLY_RECEIVED' ? 'text-sky-700 ring-sky-200' : selected.status === 'SUBMITTED' ? 'text-amber-700 ring-amber-200' : 'text-emerald-700 ring-emerald-200'">{{ statuses[selected.status] || selected.status }}</span></div>
          <div class="min-w-0"><span class="text-slate-500">订单单号</span><b class="ml-2 break-all font-mono text-slate-900">{{ selected.request_no }}</b></div>
          <div><span class="text-slate-500">下单日期</span><b class="ml-2 tabular-nums text-slate-900">{{ selected.created_at?.slice(0, 10) || '未记录' }}</b></div>
          <div><span class="text-slate-500">需用日期</span><b class="ml-2 tabular-nums text-slate-900">{{ selected.required_date }}</b></div>
          <div><span class="text-slate-500">价格</span><b class="ml-2 text-slate-900">{{ selected.kind === 'SUPPLIER_GIFT' ? '免费赠送' : '以送货单核对结果为准' }}</b></div>
          <div v-if="selected.workshop_id"><span class="text-slate-500">使用车间</span><b class="ml-2 text-slate-900">{{ options.workshops?.find(row => row.id === selected!.workshop_id)?.name || selected.workshop_id }}</b></div>
          <div class="min-w-0 sm:col-span-2 lg:col-span-4"><span class="text-slate-500">用途 / 备注</span><b class="ml-2 whitespace-pre-wrap break-words text-slate-900">{{ selected.purpose || '—' }}</b></div>
        </section>
        <CartonOrderPaperTable rule-label="计数单位" :rows="selected.lines.map((line, index) => ({ id: line.id || String(index), label: line.packaging_type, quality: line.paper_quality, specification: line.specification + ' ' + line.dimension_unit, unit: line.unit, rule: line.unit, required: Number(line.quantity), received: Number(line.received_quantity || 0), remaining: remaining(line), progress: progress(line), note: line.item_no ? '货号 ' + line.item_no : '未填写货号' }))" />
        <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-[11px] leading-5 text-slate-600" aria-label="订单纸品汇总">共 <b class="text-slate-900">{{ selected.lines.length }}</b> 项纸品；需求 <b class="text-slate-900">{{ detailSummary.required }}</b>，已入库 <b class="text-emerald-700">{{ detailSummary.received }}</b>，待入库 <b class="text-amber-700">{{ detailSummary.remaining }}</b>。入库数量来自实际收料记录，调整需求不会改写既有入库流水。</div>
        </template>
        <template v-if="supplier || mode === 'requests' || mode === 'receiving'">
        <div v-if="!supplier" class="flex justify-end"><div class="w-fit"><CartonSpecialOrderActions :request="selected" detail :disabled="busy" @action="detailAction" /></div></div>
        <section v-if="receiptOpen && pendingShipments.length" class="space-y-3 rounded-xl border border-amber-200 bg-amber-50 p-4" aria-label="已有待收送货单"><h4 class="text-sm font-bold">请先核对已有送货单</h4><p class="text-xs text-slate-600">已有待收纸品，请沿原单验收，避免重复登记收料。</p><Button v-for="shipment in pendingShipments" :key="shipment.id" variant="outline" :disabled="busy" @click="emit('open-delivery', shipment.delivery_note_no)">{{ shipment.delivery_note_no }} · 前往验收</Button></section>
        <p v-else-if="receiptOpen && !can('can_manual_receive')" role="status" class="rounded-lg border bg-slate-50 p-3 text-sm">当前订单暂不可手动收料，请核对锁单状态、权限及剩余需求。</p>
        <CartonSpecialManualReceipt v-if="manualStarted" v-show="receiptOpen && !pendingShipments.length && can('can_manual_receive')" :key="selected.id" :request="selected" :locations="locations" :viewer-key="viewerKey" :disabled="supplier" @saved="manualSaved" @busy="busy = $event" @cancel="receiptOpen = false" @open-delivery="emit('open-delivery', $event)" @locations-changed="load" />

        </template>
        <section class="space-y-3 border-t border-slate-200 pt-4" aria-label="逐纸品箱唛" v-if="supplier || mode === 'marks'">
          <h4 class="text-sm font-bold text-slate-950">箱唛资料</h4><p class="text-xs text-slate-500">按纸品确认本单使用稿。复用资料前请核对货号、PO、数量及箱数；历史送货保留当时版本。</p>
          <div v-for="line in (lineId ? selected.lines.filter(row => row.id === lineId) : selected.lines)" :key="line.id" :data-mark-line="line.id" class="space-y-3 rounded-xl border border-slate-200 p-4 text-sm">
            <div class="flex flex-wrap items-center justify-between gap-2"><b class="min-w-0 break-words">{{ line.packaging_type }}<span class="ml-2 font-normal text-slate-500">{{ line.item_no || line.specification }}</span></b><span class="rounded-full px-2.5 py-1 text-xs" :class="line.mark_ready ? 'bg-teal-50 text-teal-700' : 'bg-amber-50 text-amber-800'">{{ line.mark_mode === 'NONE' ? '无需印刷' : line.mark_ready ? '已确认使用' : '待补资料 / 待确认' }}</span></div>
            <div v-if="line.mark_attachment_id" class="flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 p-3"><span class="min-w-0 flex-1 break-all text-xs">本单使用稿：{{ selected.attachments.find(file => file.id === line.mark_attachment_id)?.filename || '箱唛资料' }}</span><Button v-if="canPreview(selected.attachments.find(file => file.id === line.mark_attachment_id)?.filename || '')" size="sm" variant="outline" @click="preview(line.mark_attachment_id, selected.attachments.find(file => file.id === line.mark_attachment_id)?.filename || '箱唛资料')">预览</Button><Button size="sm" variant="outline" :disabled="busy" @click="download(line.mark_attachment_id, selected.attachments.find(file => file.id === line.mark_attachment_id)?.filename || '箱唛资料')">下载</Button></div>
            <div class="flex flex-wrap gap-2"><Button v-if="can('can_confirm_material') || supplier && can('can_attach')" size="sm" variant="outline" :disabled="busy" @click="loadMarkOptions(line.id!)">选择已有箱唛</Button><Button v-if="can('can_attach')" size="sm" variant="outline" :disabled="busy" @click="markUploadLine = markUploadLine === line.id ? '' : line.id!">上传箱唛</Button><Button v-if="can('can_confirm_material')" size="sm" variant="outline" :disabled="busy" @click="setMark(line, 'NONE')">无需印刷</Button><Button v-if="can('can_confirm_material')" size="sm" variant="ghost" :disabled="busy" @click="setMark(line, 'PENDING')">标记待补资料</Button></div>
            <form v-if="markUploadLine === line.id && can('can_attach')" class="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3" :aria-label="`${line.id}箱唛上传`" @submit.prevent="upload(line.id)"><label>选择箱唛文件<input type="file" accept=".pdf,.xlsx,.png,.jpg,.jpeg,.webp" :aria-label="`${line.id}箱唛文件`" :disabled="busy" @change="chooseMarkFile(line.id!, $event)"></label><p class="text-xs text-slate-500">支持 PDF、XLSX、JPG、PNG、WebP，单个文件最多 10 MiB。上传后待我方确认，确认前不可按此稿生产。</p><Button size="sm" :disabled="busy || !markFiles[line.id!]">上传待确认稿</Button></form>
            <div v-if="markPickerLine === line.id" class="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3"><label>查找资料<input v-model="markSearch" aria-label="查找已有箱唛" placeholder="文件名或合同号"></label><div class="flex flex-wrap items-end gap-2"><label class="min-w-0 flex-1">已有箱唛<select v-model="markAsset[line.id!]" :aria-label="`${line.id}已有箱唛`"><option value="">选择文件及版本</option><option v-for="asset in filteredMarkChoices" :key="asset.id" :value="asset.id">{{ asset.file_name }} · {{ asset.contract_number || '未关联合同' }} · 版本 {{ asset.revision }}</option></select></label><Button size="sm" :disabled="busy || !markAsset[line.id!]" @click="setMark(line, 'EXISTING')">{{ supplier ? '绑定并提交确认' : '确认使用' }}</Button></div><p v-if="!filteredMarkChoices.length" class="text-xs text-slate-500">暂无可选资料，可上传新的箱唛。</p></div>
            <div v-if="pendingDrafts(line.id).length" class="space-y-2 border-t border-slate-100 pt-3"><p class="text-xs font-semibold text-amber-800">待我方确认</p><p v-if="line.mark_attachment_id && line.mark_ready" class="text-xs text-slate-500">当前仍使用上方确认稿；新稿确认后才替换本单后续制作资料。需暂停制作时，请标记待补资料。</p><div v-for="file in pendingDrafts(line.id)" :key="file.id" class="flex flex-wrap items-center gap-2"><span class="min-w-0 flex-1 break-all text-xs">{{ file.filename }}</span><Button v-if="canPreview(file.filename)" size="sm" variant="ghost" @click="preview(file.id, file.filename)">预览</Button><Button size="sm" variant="ghost" @click="download(file.id, file.filename)">下载</Button><Button v-if="can('can_confirm_material')" size="sm" :disabled="busy" @click="markAttachment[line.id!] = file.id; setMark(line, 'UPLOAD')">确认本单使用</Button></div></div>
            <details v-if="selected.attachments.some(file => file.line_id === line.id && file.role === 'CONFIRMED' && file.id !== line.mark_attachment_id)" class="text-xs text-slate-500"><summary class="cursor-pointer">历史版本</summary><div v-for="file in selected.attachments.filter(file => file.line_id === line.id && file.role === 'CONFIRMED' && file.id !== line.mark_attachment_id)" :key="file.id" class="mt-2 flex flex-wrap items-center justify-between gap-2"><span class="break-all">{{ file.filename }}</span><Button size="sm" variant="ghost" @click="download(file.id, file.filename)">下载历史稿</Button></div></details>
          </div>
          <div v-if="previewFile" class="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-3" aria-label="箱唛预览"><div class="flex items-center justify-between gap-2"><b class="min-w-0 break-all text-xs">{{ previewFile.name }}</b><Button size="sm" variant="outline" @click="closePreview">关闭预览</Button></div><img v-if="previewFile.image" :src="previewFile.url" :alt="previewFile.name" class="max-h-[60vh] max-w-full object-contain"><iframe v-else :src="previewFile.url" :title="previewFile.name" class="h-[60vh] w-full rounded-lg border border-slate-200 bg-white" /></div>
        </section>
        <template v-if="mode !== 'marks'">
        <details :open="mode !== 'detail'" class="space-y-2 border-t pt-4">
          <summary role="button" class="text-sm font-bold">送货与收货记录</summary>
          <p v-if="!selected.shipments?.length" class="text-xs text-muted-foreground">尚未登记送货。</p>
          <div v-for="shipment in selected.shipments" :key="shipment.id" class="space-y-3 rounded-lg border p-3 text-xs">
            <div class="flex flex-wrap items-center justify-between gap-2"><b>{{ shipment.delivery_note_no }} · {{ shipment.delivery_date }}</b><Button v-if="mode !== 'detail' && can('can_receive') && shipment.lines.some(line => Number(line.remaining_quantity) > 0)" size="sm" variant="outline" :disabled="busy" @click="openReceive(shipment)">登记仓库验收</Button></div>
            <p v-if="shipment.source_origin === 'WAREHOUSE_MANUAL'" class="text-amber-800">仓库代录实际收料 · 价格以双方核对结果为准</p>
            <details class="text-muted-foreground"><summary class="cursor-pointer">发货时确认资料 · 版本记录</summary><p class="mt-2 break-all">{{ shipment.version_id }}</p><div v-for="line in shipment.lines" :key="line.id" class="mt-2"><span>{{ line.snapshot?.packaging_type }} · {{ markModes[line.snapshot?.mark_mode || 'PENDING'] }}</span><Button v-if="line.snapshot?.mark_attachment_id" size="sm" variant="ghost" @click="download(line.snapshot.mark_attachment_id, selected.attachments.find(file => file.id === line.snapshot?.mark_attachment_id)?.filename || '发货箱唛')">下载本批箱唛</Button></div></details>
            <div v-for="line in shipment.lines" :key="line.id" class="space-y-1 rounded-lg bg-muted/30 p-2">
              <p>{{ line.snapshot?.packaging_type || '原发货纸品' }} · {{ line.snapshot?.paper_quality || '原记录未提供纸质' }} · {{ line.snapshot?.specification || '原记录未提供规格' }} {{ line.snapshot?.dimension_unit }}</p>
              <p>发货 {{ line.quantity }} {{ line.snapshot?.unit }} · 累计实收 {{ line.gross_received_quantity ?? line.received_quantity }} · 有效入库 {{ line.effective_received_quantity ?? line.received_quantity }} · 待验收 {{ line.remaining_quantity }}</p>
              <p v-if="line.snapshot && shipment.source_origin === 'WAREHOUSE_MANUAL'">仓库记录单价：{{ line.snapshot.warehouse_unit_price == null ? '未填写' : `CNY ${line.snapshot.warehouse_unit_price} / ${line.snapshot.unit}` }} · 仓库记录，不代表供应商原价</p>
              <p v-else-if="line.snapshot">送货单价：{{ pricing[line.snapshot.pricing_kind || 'PENDING_QUOTE'] }} · CNY {{ line.snapshot.unit_price ?? '待核实' }} / {{ line.snapshot.unit }}</p>
            </div>
            <details v-for="receipt in shipment.receipts" :key="receipt.id" class="rounded-lg border p-2"><summary class="cursor-pointer font-semibold text-primary">{{ receipt.receipt_no || receipt.id }} · {{ receipt.acceptance_date }} · {{ receipt.status === 'REVERSED' ? '已冲销' : '验收记录' }}</summary><p v-for="(line, index) in receipt.lines || []" :key="line.id || index" class="mt-2">{{ line.packaging_type }} · {{ line.paper_quality }} · {{ line.specification }} · 实收 {{ line.received_quantity }} · 破损 {{ line.damaged_quantity }} · 拒收 {{ line.rejected_quantity }} · 其他不可用 {{ line.unusable_quantity }} · 有效入库 {{ line.effective_quantity }} {{ line.unit }} · {{ shipment.source_origin === 'WAREHOUSE_MANUAL' ? '库存记录价' : '单价' }} CNY {{ line.unit_price }}<span v-if="shipment.source_origin === 'WAREHOUSE_MANUAL'"> · 价格以双方核对结果为准</span></p></details>
          </div>
        </details>

        <details :open="mode !== 'detail'" class="space-y-3 border-t border-slate-200 pt-4" aria-label="备注附件"><summary role="button" class="text-sm font-bold">备注附件</summary><p class="text-xs text-slate-500">说明、参考图片等放在这里；印刷箱唛统一在箱唛资料库维护。</p><p v-if="!selected.attachments.some(file => file.role === 'REFERENCE')" class="text-xs text-slate-500">暂无备注附件。</p><div v-for="attachment in selected.attachments.filter(file => file.role === 'REFERENCE')" :key="attachment.id" class="flex min-w-0 flex-wrap items-center justify-between gap-2 text-xs"><span class="min-w-0 break-all">{{ attachment.filename }}</span><Button variant="ghost" size="sm" :disabled="busy" @click="download(attachment.id, attachment.filename)">下载附件</Button></div><form v-if="can('can_attach') && (supplier || mode !== 'detail')" class="space-y-2" aria-label="备注附件上传" @submit.prevent="upload()"><div class="grid gap-3 sm:grid-cols-2"><label>对应纸品<select v-model="attachmentLine" aria-label="附件对应纸品" :disabled="busy"><option v-for="line in selected.lines" :key="line.id" :value="line.id">{{ line.packaging_type }} · {{ line.specification }}</option></select></label><label>选择文件<input type="file" aria-label="备注附件文件" :disabled="busy" @change="chooseFile"></label></div><Button variant="outline" :disabled="busy || !attachmentFile">上传备注附件</Button></form></details>
        <details :open="mode !== 'detail'" class="space-y-3 border-t pt-4"><summary role="button" class="text-sm font-bold">协作消息</summary><p v-if="!selected.messages?.length" class="text-xs text-muted-foreground">暂无消息。</p><div v-for="message in selected.messages" :key="message.id" class="rounded-lg bg-muted/40 p-3 text-xs"><p class="text-muted-foreground">{{ message.actor_name || message.author_name }} · {{ message.created_at }}</p><p class="mt-1 whitespace-pre-wrap break-words">{{ message.body }}</p></div><form v-if="can('can_message') && (supplier || mode !== 'detail')" class="space-y-2" @submit.prevent="messageBody.trim() && act('messages', 'can_message', { body: messageBody.trim() })"><label>消息<textarea v-model="messageBody" aria-label="特殊申请消息" rows="2" maxlength="4000" required :disabled="busy" /></label><Button variant="outline" :disabled="busy || !messageBody.trim()">发送消息</Button></form></details>
        <details class="border-t pt-3 text-xs"><summary class="cursor-pointer font-semibold">操作历史（{{ selected.history?.length || 0 }}）</summary><p v-for="(history, index) in selected.history" :key="history.id || index" class="mt-2 break-words text-muted-foreground">{{ history.created_at }} · {{ history.actor_name }} · {{ history.action === 'ADJUSTED' ? '调整订单' : history.action === 'MANUAL_RECEIVED' ? '仓库登记收料' : actions[history.action] || '单据变更' }}<template v-if="history.note"> · {{ history.note }}</template></p></details>
        </template>
      </article>
      <p v-else class="rounded-xl border border-dashed bg-card p-6 text-sm text-muted-foreground">选择订单以查看纸品、资料及送货进度。</p>
    </div>
    <DialogRoot :open="(cancelConfirm || deleteConfirm) && Boolean(selected)" @update:open="value => { if (!busy && !value) { cancelConfirm = false; deleteConfirm = false } }">
      <DialogPortal><DialogOverlay class="fixed inset-0 z-[80] bg-slate-950/40" /><DialogContent class="fixed left-1/2 top-1/2 z-[81] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-2xl border bg-white p-5 shadow-xl" @escape-key-down="event => { if (busy) event.preventDefault() }">
        <DialogTitle class="text-base font-bold text-slate-950">{{ deleteConfirm ? '删除订单' : '取消订单' }} {{ selected?.request_no }}</DialogTitle>
        <DialogDescription class="text-sm leading-6 text-slate-600">{{ deleteConfirm ? '删除后从订单台账移除，原订单、版本和历史证据保留。未取消且已有供应商执行、附件或收料的订单不可删除。' : '取消后不能继续送货，原订单及操作历史保留。已有送货记录时须先核实处理。' }}</DialogDescription>
        <label v-if="deleteConfirm">删除原因 *<textarea v-model="deleteReason" aria-label="样板杂单删除原因" maxlength="1000" rows="2" :disabled="busy" placeholder="请填写至少四字的删除原因" /></label>
        <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
        <div class="flex justify-end gap-2"><Button variant="outline" :disabled="busy" @click="cancelConfirm = false; deleteConfirm = false">返回</Button><Button variant="destructive" :disabled="busy || (deleteConfirm ? !can('can_delete') || deleteReason.trim().length < 4 : !can('can_cancel'))" @click="deleteConfirm ? deleteOrder() : act('cancel', 'can_cancel')">{{ busy ? '正在处理…' : deleteConfirm ? '确认删除订单' : '确认取消订单' }}</Button></div>
      </DialogContent></DialogPortal>
    </DialogRoot>
    <DialogRoot :open="confirmOpen && Boolean(selected)" @update:open="value => { if (!busy) confirmOpen = value }">
      <DialogPortal><DialogOverlay class="fixed inset-0 z-[80] bg-black/40" /><DialogContent class="fixed left-1/2 top-1/2 z-[81] max-h-[85vh] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 -translate-y-1/2 space-y-4 overflow-auto rounded-2xl bg-white p-5 shadow-xl" @interact-outside.prevent @escape-key-down="event => { if (busy) event.preventDefault() }">
        <DialogTitle class="text-base font-bold text-slate-950">确认并锁单</DialogTitle><DialogDescription class="text-sm leading-6 text-slate-600">请核对本单需求。确认后供应商可接收订单；后续修改须填写调整原因，已有送货和收料记录保留。</DialogDescription>
        <template v-if="selected"><div class="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm"><p class="font-semibold">{{ selected.request_no }} · {{ kinds[selected.kind] }}</p><p class="mt-2">客户：{{ selected.customer_name || '未关联客户' }}</p><p>需求人：{{ selected.requester_name }} · 需用日期：{{ selected.required_date }}</p><p v-for="line in selected.lines" :key="line.id" class="mt-2 break-words">{{ line.packaging_type }} · {{ line.item_no || '未填货号' }} · {{ line.specification }} {{ line.dimension_unit }} · {{ quantity(line.quantity) }} {{ line.unit }} · {{ line.mark_mode === 'NONE' ? '无需印刷' : line.mark_ready ? '箱唛已确认' : '箱唛待确认' }}</p></div><p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p><div class="flex justify-end gap-2"><Button variant="outline" :disabled="busy" @click="confirmOpen = false">返回核对</Button><Button :disabled="busy || !can('can_confirm')" @click="act('confirm', 'can_confirm')">{{ busy ? '正在确认…' : '核对无误，确认锁单' }}</Button></div></template>
      </DialogContent></DialogPortal>
    </DialogRoot>
  </section>
</template>

<style scoped>
.carton-special { color: var(--foreground); }
.carton-special label { display: block; min-width: 0; font-size: 12px; font-weight: 600; }
.carton-special input,.carton-special select,.carton-special textarea { display: block; width: 100%; min-width: 0; margin-top: 6px; border: 1px solid var(--input); border-radius: 8px; padding: 8px 10px; background: var(--card); font-size: 14px; font-weight: 400; }
.carton-special input,.carton-special select { min-height: 40px; }
.carton-special input[type='file'] { max-width: 100%; }
.carton-special .special-dimension-unit { min-width: 5rem; }
.carton-special :disabled { opacity: .55; }
.carton-special th { padding: 9px 7px; background: var(--muted); color: var(--muted-foreground); font-weight: 600; }
.carton-special td { padding: 9px 7px; border-bottom: 1px solid var(--border); vertical-align: top; }
.carton-special td input,.carton-special td select { margin-top: 0; }
.carton-special dt { color: var(--muted-foreground); }
.carton-special dd { margin: 5px 0 0; }
@media (max-width: 639px) { .carton-special button { min-height: 44px; } }
</style>
