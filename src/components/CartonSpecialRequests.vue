<script setup lang="ts">
import CartonSpecialPurchaseOrders from './CartonSpecialPurchaseOrders.vue'
import CartonOrderDetailContent from '@/components/CartonOrderDetailContent.vue'
import CartonOrderMainFields from '@/components/CartonOrderMainFields.vue'
import CartonOrderPaperSection from '@/components/CartonOrderPaperSection.vue'
import CartonOrderQuantityField from '@/components/CartonOrderQuantityField.vue'
import CartonOrderNoteField from '@/components/CartonOrderNoteField.vue'
import CartonOrderAdjustmentForm from '@/components/CartonOrderAdjustmentForm.vue'
import CartonMarkAssetLibrary from '@/components/CartonMarkAssetLibrary.vue'
import { specialSupplierAccepted, specialSupplierPromise, specialSupplierOrigin, specialSupplierStatusLabel } from '@/features/carton-procurement/supplierWork'
import CartonOrderPaperEditor from '@/components/CartonOrderPaperEditor.vue'
import CartonOrderEditorForm from '@/components/CartonOrderEditorForm.vue'
import CartonOrderActionDialog from '@/components/CartonOrderActionDialog.vue'
import CartonOrderSummary from '@/components/CartonOrderSummary.vue'
import CartonSupplierChangeTasks from './CartonSupplierChangeTasks.vue'
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { canAdjustSpecialRequest, canAppendSpecialRequest, isSpecialAdjustmentAction, specialAdjustmentCopy, type SpecialAdjustmentAction, type SpecialOrderAction } from '@/features/carton-procurement/specialOrderActions'
import { Button } from '@/components/ui/button'
import CartonSpecialManualReceipt from './CartonSpecialManualReceipt.vue'
import CartonSpecialOrderActions from './CartonSpecialOrderActions.vue'
import type { CartonLocation } from '@/api/cartonPositions'
import { cartonSpecialRequestsApi as api, type SpecialRequest, type SpecialLine, type SpecialSave, type SpecialWorkspace, type SpecialAction, type AttachmentRole, type SpecialShipment, type MarkOption } from '@/api/cartonSpecialRequests'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { cartonMarkApi } from '@/api/cartonMark'
import { cartonSupplierPortalApi } from '@/api/cartonSupplierPortal'

const props = withDefaults(defineProps<{ factoryId: string; viewerKey?: string; supplier?: boolean; supplierReadOnly?: boolean; mode?: 'requests' | 'receiving' | 'detail' | 'marks'; requestId?: string; lineId?: string; previewRequest?: SpecialRequest; requesterName?: string; createNew?: boolean; initialKind?: 'SAMPLE' | 'WORKSHOP_MISC'; initialAction?: SpecialOrderAction; search?: string }>(), { mode: 'requests' })
const emit = defineEmits<{ changed: []; close: []; 'editor-mode': [mode: '' | 'editor' | 'append' | 'reduce' | 'date']; busy: [value: boolean]; dispatch: []; 'open-delivery': [deliveryNoteNo: string]; 'stock-action': [request: SpecialRequest, action: 'return-stock' | 'replenish' | 'undo-replenish'] }>()
const workspace = ref<SpecialWorkspace>({ items: [], total: 0, can_create: false })
const selected = ref<SpecialRequest | null>(null), loading = ref(false), detailLoading = ref(false), busy = ref(false)
const error = ref(''), success = ref(''), search = ref(''), kindFilter = ref(''), statusFilter = ref('')
const editing = ref(false), editingId = ref(''), editRevision = ref(0)
const adjusting = ref(false), adjustmentReason = ref(''), confirmOpen = ref(false), receiptOpen = ref(false), manualStarted = ref(false)
const adjustmentAction = ref<SpecialAdjustmentAction>('adjust')
const focusedAdjustment = computed(() => adjusting.value && ['append', 'reduce', 'date'].includes(adjustmentAction.value) ? adjustmentAction.value as 'append' | 'reduce' | 'date' : null)
watch([editing, focusedAdjustment], ([open, action]) => emit('editor-mode', open ? action || 'editor' : ''), { immediate: true })
watch(busy, value => emit('busy', value), { immediate: true })
const adjustmentTargets = computed({ get: (): Record<string, number | string> => Object.fromEntries(form.lines.filter(line => line.id).map(line => [line.id!, line.quantity])), set: values => { for (const line of form.lines) if (line.id && values[line.id] !== undefined) line.quantity = String(values[line.id]) } })
const adjustmentPapers = computed(() => (selected.value?.lines || []).map(line => ({ id: line.id || '', label: [line.packaging_type, line.paper_quality, line.specification, line.dimension_unit].join(' · '), unit: line.unit, current: Number(line.quantity), protected: Number(line.received_quantity || 0), minimum: 0.0001 })))
function closeAdjustment() { editing.value = false; if (props.mode === 'detail') emit('close') }

const specialFormElement = ref<InstanceType<typeof CartonOrderEditorForm> | null>(null)
const copiedOrderNo = ref(''), purchaseOpen = ref(false)
let appliedInitialAction = ''
let formDraftKey = ''
const pendingShipments = computed(() => selected.value?.shipments.filter(shipment => shipment.lines.some(line => scaled(line.remaining_quantity) > 0n)) || [])
const locations = computed<CartonLocation[]>(() => (options.value.locations || []).map(location => ({ ...location, factory_id: props.factoryId, warehouse: location.warehouse || '', bin_code: location.bin_code || '', status: 'ACTIVE' })))
const shippedLine = (id?: string) => Boolean(id && selected.value?.shipments.some(shipment => shipment.lines.some(line => line.request_line_id === id)))
const completedAppend = computed(() => adjusting.value && adjustmentAction.value === 'append' && selected.value?.status === 'COMPLETED')
const paperIdentityLocked = (id?: string) => adjusting.value && (shippedLine(id) || Boolean(completedAppend.value && id && selected.value?.lines.some(line => line.id === id)))
const adjustmentPermitted = () => Boolean(selected.value && (adjustmentAction.value === 'append' ? canAppendSpecialRequest(selected.value) : canAdjustSpecialRequest(selected.value)))
const blankLine = (): SpecialLine => ({ packaging_type: '', paper_quality: '', specification: '', dimension_unit: 'cm', quantity: '', unit: '个', item_no: '' })
const markModes: Record<string, string> = { EXISTING: '当时关联已有资料', UPLOAD: '当时上传资料', NONE: '历史登记无需箱唛', PENDING: '当时未补资料' }
const form = reactive({ kind: 'SAMPLE' as SpecialSave['kind'], requester_name: '', purpose: '', workshop_id: '', customer_code: '', required_date: '', lines: [blankLine()] })
const markChoices = ref<MarkOption[]>([]), markAsset = ref<Record<string, string>>({})
const attachmentLine = ref('')
const markUploadLine = ref(''), markFiles = ref<Record<string, File | null>>({}), markPickerLine = ref(''), markSearch = ref('')
const previewFile = ref<{ url: string; name: string; image: boolean } | null>(null)
const filteredMarkChoices = computed(() => markChoices.value.filter(asset => `${asset.file_name} ${asset.contract_number || ''}`.toLowerCase().includes(markSearch.value.trim().toLowerCase())))
const hasAssociatedMark = (line: SpecialLine) => Boolean(line.mark_attachment_id || line.mark_asset_id || selected.value?.mark_assets?.some(file => !file.line_id || file.line_id === line.id))
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
const options = computed(() => workspace.value.options ?? {})
function requestKey(signature: string) { if (!attempts.has(signature)) attempts.set(signature, createRandomUuid()); return attempts.get(signature)! }
function reset() {
  purchaseOpen.value = false; generation++; listSequence++; detailSequence++; controller.abort(); controller = new AbortController()
  appliedInitialAction = ''; formDraftKey = ''; adjusting.value = false; adjustmentReason.value = ''; confirmOpen.value = false; receiptOpen.value = false; manualStarted.value = false
  adjustmentAction.value = 'adjust'; copiedOrderNo.value = ''
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
  if (selected.value?.id !== row.id) { manualStarted.value = false; appliedInitialAction = ''; copiedOrderNo.value = '' }
  confirmOpen.value = false; receiptOpen.value = false
  selected.value = row; editing.value = false; cancelConfirm.value = false; deleteConfirm.value = false; deleteReason.value = ''; messageBody.value = ''; attachmentFile.value = null
  markUploadLine.value = ''; markPickerLine.value = ''; markFiles.value = {}; closePreview(); attachmentLine.value = row.lines[0]?.id || ''; markAsset.value = {}; }
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
  detailAction(props.initialAction)
}
function detailAction(action?: SpecialOrderAction) {
  if (busy.value) return
  if (action === 'receive') openReceipt()
  else if (action === 'confirm' && can('can_confirm')) confirmOpen.value = true
  else if (isSpecialAdjustmentAction(action)) openFocusedAdjustment(action)
  else if (action === 'edit') openForm(true)
  else if (action === 'copy') copyOrder()
  else if (action === 'purchase') purchaseOpen.value = true
  else if (action === 'return-stock' || action === 'replenish' || action === 'undo-replenish') {
    const permission = { 'return-stock': 'can_return_stock', replenish: 'can_replenish', 'undo-replenish': 'can_undo_replenish' } as const
    if (selected.value && can(permission[action])) emit('stock-action', selected.value, action)
  }
  else if (action === 'cancel' && can('can_cancel')) cancelConfirm.value = true
  else if (action === 'delete' && can('can_delete')) deleteConfirm.value = true
}
function openFocusedAdjustment(action: SpecialAdjustmentAction) {
  if (!selected.value || !(action === 'append' ? canAppendSpecialRequest(selected.value) : canAdjustSpecialRequest(selected.value))) return
  const materialIndex = selected.value.lines.findIndex(line => !shippedLine(line.id))
  if (action === 'material' && materialIndex < 0) return
  adjustmentAction.value = action
  openForm(true, true)
  const label = action === 'date' ? '需求日期' : action === 'material' ? `纸品类型 ${materialIndex + 1}` : '纸品需求数量 1'
  void nextTick(() => specialFormElement.value?.focusField(label))
}
function copyOrder() {
  const source = selected.value
  if (!source || props.supplier || !workspace.value.can_create || busy.value) return
  formDraftKey = ''; openForm()
  Object.assign(form, { kind: source.kind, purpose: source.purpose, customer_code: source.customer_code, required_date: '',
    lines: source.lines.map(({ packaging_type, paper_quality, specification, dimension_unit, quantity, unit, item_no }) => ({ packaging_type, paper_quality, specification, dimension_unit, quantity, unit, item_no, mark_mode: 'PENDING' })) })
  copiedOrderNo.value = source.request_no
}
function openReceipt() {
  if (busy.value || props.supplier) return
  receiptOpen.value = true
  if (!pendingShipments.value.length && can('can_manual_receive')) manualStarted.value = true
}
function manualSaved(row: SpecialRequest) { busy.value = false; manualStarted.value = false; initDetail(row); success.value = '实际收料已登记，供应商原价及本次记录等待供应商核实。'; emit('changed'); void load() }
function openForm(edit = false, adjust = false) {
  if (busy.value || (edit && (selected.value?.origin === 'REPLENISHMENT' || selected.value?.replacement))
    || (edit ? adjust ? !adjustmentPermitted() : !can('can_edit') : props.supplier || !workspace.value.can_create)) return
  const draftKey = `${edit ? selected.value?.id : 'new'}:${edit ? selected.value?.revision : 0}:${adjust}:${adjustmentAction.value}`
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
  if (busy.value || (editingId.value ? adjusting.value ? !adjustmentPermitted() : !can('can_edit') : !workspace.value.can_create)) return
  if (adjusting.value && adjustmentReason.value.trim().length < 4) { error.value = '请填写至少四字的调整原因。'; return }
  if (!form.required_date) { error.value = '请填写计划交期。'; return }
  if (!form.lines.length || form.lines.some(line => !line.packaging_type.trim() || !line.paper_quality.trim() || !line.specification.trim() || !line.dimension_unit || !line.unit.trim() || !validDecimal(String(line.quantity)))) { error.value = '每条纸品须填写类型、纸质、规格、尺寸单位、计数单位和大于零的数量（最多四位小数）。'; return }
  if (adjusting.value && form.lines.some(line => scaled(line.quantity) < scaled(selected.value?.lines.find(source => source.id === line.id)?.received_quantity || '0'))) { error.value = '调整后的需求数量不能少于累计有效入库数量。'; return }
  if (completedAppend.value && selected.value) {
    const originals = selected.value.lines
    if (originals.some(source => { const line = form.lines.find(row => row.id === source.id); return !line || scaled(line.quantity) < scaled(source.quantity)
      || (['packaging_type', 'paper_quality', 'specification', 'dimension_unit', 'unit', 'item_no'] as const).some(field => line[field] !== source[field]) })) {
      error.value = '已完成订单追加须保留原纸品身份和原数量，只可增加需求。'; return
    }
    if (!form.lines.some(line => { const source = originals.find(row => row.id === line.id); return !source || scaled(line.quantity) > scaled(source.quantity) })) {
      error.value = '请增加原纸品总需求或新增纸品；已完成订单不能只修改交期或备注。'; return
    }
  }
  if (focusedAdjustment.value && selected.value) {
    const before = selected.value.lines
    if (focusedAdjustment.value === 'date') {
      if (form.required_date === selected.value.required_date) { error.value = '交期没有变化，请修改后保存。'; return }
      // Date-only updates must never carry quantities or paper edits from another form.
      form.lines = before.map(({ id, packaging_type, paper_quality, specification, dimension_unit, quantity, unit, item_no, mark_mode }) => ({ id, packaging_type, paper_quality, specification, dimension_unit, quantity, unit, item_no, mark_mode }))
    } else {
      const append = focusedAdjustment.value === 'append'
      if (before.some(source => { const line = form.lines.find(row => row.id === source.id); return !line || (append ? scaled(line.quantity) < scaled(source.quantity) : scaled(line.quantity) > scaled(source.quantity)) })) { error.value = append ? '追加不能减少原需求数量。' : '减单不能增加原需求数量。'; return }
      if (!form.lines.some(line => !line.id || !before.some(source => source.id === line.id)) && !before.some(source => scaled(form.lines.find(row => row.id === source.id)!.quantity) !== scaled(source.quantity))) { error.value = '数量没有变化，请修改后保存。'; return }
      if (!append) form.required_date = selected.value.required_date
    }
  }
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
  try { const result = await api.attach(row.id, { factory_id: props.factoryId, request_id: requestKey(signature), expected_revision: row.revision, line_id: lineId || attachmentLine.value }, role, file, props.supplier, controller.signal); if (token === generation) { attempts.delete(signature); initDetail(result); success.value = lineId ? '箱唛已保存并关联本单；文件版本和上传记录已保留。' : '备注附件已上传。'; emit('changed'); await load() } }
  catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) busy.value = false }
}
async function download(id: string, filename: string) {
  const row = selected.value, token = generation; if (!row || busy.value) return
  try { const blob = await api.download(props.factoryId, row.id, id, props.supplier, controller.signal); if (token !== generation) return; const url = URL.createObjectURL(blob), anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) }
  catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
}
async function openAssociatedMark(file: NonNullable<SpecialRequest['mark_assets']>[number], showPreview = false) {
  const row = selected.value, token = generation
  if (!row || busy.value) return
  try {
    const blob = props.supplier ? await cartonSupplierPortalApi.downloadMarkAsset(file.id, props.factoryId, controller.signal) : await cartonMarkApi.downloadAsset(props.factoryId, file.id, controller.signal)
    if (token !== generation || selected.value?.id !== row.id) return
    if (showPreview) { closePreview(); previewFile.value = { url: URL.createObjectURL(blob), name: file.file_name, image: file.kind === 'image' }; return }
    const url = URL.createObjectURL(blob), anchor = document.createElement('a'); anchor.href = url; anchor.download = file.file_name; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
}
async function loadMarkOptions(lineId: string) {
  markPickerLine.value = lineId; markSearch.value = ''; markChoices.value = []
  const token = generation, rowId = selected.value?.id; try { const result = await api.markOptions(props.factoryId, controller.signal, props.supplier, rowId); if (token === generation && selected.value?.id === rowId) markChoices.value = result } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
}
function setMark(line: SpecialLine) {
  if (!line.id) return
  void act(`lines/${line.id}/mark`, 'can_attach', { mark_mode: 'EXISTING', asset_id: markAsset.value[line.id] || '', asset_revision: markChoices.value.find(asset => asset.id === markAsset.value[line.id!])?.revision || 0, attachment_id: '' })
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
  <CartonSpecialPurchaseOrders v-if="purchaseOpen && selected" :factory-id="factoryId" :request-id="selected.id" :order-no="selected.request_no" :supplier="supplier" @close="purchaseOpen = false" />
  <section class="carton-special space-y-3" :aria-label="mode === 'marks' ? '订单箱唛资料' : '订单工作面板'" :aria-busy="loading || busy">
    <div v-if="mode !== 'detail'" class="border border-slate-200 bg-white flex flex-wrap items-center justify-between gap-3 rounded-xl p-4">
      <div><h2 class="text-base font-bold">{{ mode === 'marks' ? '订单箱唛资料' : mode === 'receiving' ? '样板与杂单 · 送货验收' : '样板与杂单订单' }}</h2><p class="mt-1 text-xs text-muted-foreground">{{ mode === 'marks' ? '查看样板或杂单已关联资料，也可由经办人直接上传或关联。正单、样板和杂单统一从资料库关联订单。' : '创建订单 → 确认并锁单 → 供应商送货 → 仓库验收。' }}</p></div>
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
    <CartonOrderAdjustmentForm v-if="editing && focusedAdjustment && selected" :action="focusedAdjustment" :order-no="selected.request_no" :busy="busy" :lines="adjustmentPapers" v-model:targets="adjustmentTargets" v-model:due-date="form.required_date" date-label="需用日期" v-model:reason="adjustmentReason" :reason-max="1000" :error="error" notice="保存后同步新需求版本，供应商需核对新版重新确认。" :guidance="focusedAdjustment === 'date' ? '仅修改需用日期，保留原数量和纸品。' : '按实际纸品调整需求，已收批次保留；在途或冲销待更正送货须先处理。'" @submit="save" @close="closeAdjustment" >
      <section v-if="focusedAdjustment === 'append'" class="space-y-3"><button type="button" :disabled="busy || form.lines.length >= 50" class="rounded-lg border border-teal-200 bg-white px-3 py-2 text-xs font-semibold text-teal-700" @click="form.lines.push(blankLine())">新增纸品</button><template v-for="(line, index) in form.lines" :key="index"><CartonOrderPaperEditor v-if="!line.id" :index="index" v-model:packaging="line.packaging_type" v-model:quality="line.paper_quality" v-model:specification="line.specification" v-model:dimension="line.dimension_unit" v-model:unit="line.unit" v-model:item="line.item_no" item-enabled dimension-editable :disabled="busy" @remove="form.lines.splice(index, 1)"><template #quantity><label class="block text-xs font-semibold">新增纸品需求数量<input :value="line.quantity" @input="line.quantity = ($event.target as HTMLInputElement).value" :aria-label="'纸品需求数量 ' + (index + 1)" type="number" min="0.0001" step="0.0001" required class="mt-2 h-9 w-full rounded-lg border px-2"></label></template></CartonOrderPaperEditor></template></section>
    </CartonOrderAdjustmentForm>
    <CartonOrderEditorForm ref="specialFormElement" v-else-if="editing" :title="adjusting ? specialAdjustmentCopy[adjustmentAction].title : editingId ? '修改纸箱订单' : '新建纸箱订单'" :busy="busy" :submit-label="adjusting ? '保存订单调整' : editingId ? '保存订单修改' : '创建待确认订单'" :back-label="editingId ? '返回订单' : '关闭表单'" @submit="save" @close="editing = false; if (!editingId) emit('close')">
      <p v-if="copiedOrderNo" class="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-xs text-teal-800">复制自订单 {{ copiedOrderNo }}，已带入纸品资料。请核对数量并重新选择交期；保存后生成新订单。</p>
      <div v-if="adjusting" class="space-y-1 rounded-lg border border-teal-200 bg-teal-50 p-3 text-xs leading-6 text-teal-950" aria-label="订单调整说明"><p class="font-semibold">{{ specialAdjustmentCopy[adjustmentAction].help }}</p><p v-if="completedAppend">已完成订单只办理追加：保留全部原纸品及原数量，必须实际增加需求；可为新增需求核对交期。</p><p>这是带原因的完整版本调整；保存后发布新需求版本，供应商须重新确认，原报价和承诺日期不自动沿用。在途或冲销待更正送货须先沿原送货单处理。</p></div>
      <CartonOrderMainFields :kind="form.kind" @update:kind="form.kind = $event as SpecialSave['kind']" v-model:due-date="form.required_date" :disabled="busy" :type-locked="supplier || Boolean(editingId)" />
      <p class="text-xs text-slate-500">箱唛资料选填，统一在箱唛资料库关联订单。</p>
<CartonOrderPaperSection :disabled="busy || form.lines.length >= 50" guidance="逐项填写纸品总需求和交期；无需填写来源或合同。" @add="form.lines.push(blankLine())"><CartonOrderPaperEditor v-for="(line, index) in form.lines" :key="index" :index="index" v-model:packaging="line.packaging_type" v-model:quality="line.paper_quality" v-model:specification="line.specification" v-model:dimension="line.dimension_unit" v-model:unit="line.unit" v-model:item="line.item_no" item-enabled dimension-editable :disabled="busy" :identity-locked="paperIdentityLocked(line.id)" :remove-disabled="form.lines.length <= 1" @remove="form.lines.splice(index, 1)"><template #quantity><CartonOrderQuantityField v-model="line.quantity" :index="index" :disabled="busy" /></template></CartonOrderPaperEditor></CartonOrderPaperSection>
      <label v-if="adjusting">调整原因 *<textarea v-model="adjustmentReason" aria-label="订单调整原因" rows="2" maxlength="1000" required :disabled="busy" placeholder="请说明调整内容和原因，至少四字" /></label>
      <CartonOrderNoteField v-model="form.purpose" :disabled="busy" />

      <template #feedback><p class="text-xs text-slate-500">{{ adjusting ? '调整保留原版本和已收批次；客户、类型、原车间归属及已送货纸品身份不能改变。' : editingId ? '锁单前可以修改订单资料。' : '保存后进入待确认；核对采购需求后确认并锁单；箱唛资料可随时另行关联。' }}</p></template>
    </CartonOrderEditorForm>
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
        <CartonOrderDetailContent :fields="[{ label: '客户', value: selected.customer_name || '未关联客户' }, { label: '订单类型', value: kinds[selected.kind] }, { label: '订单单号', value: selected.request_no }, { label: '状态', value: supplier ? specialSupplierStatusLabel(selected) : statuses[selected.status] || selected.status }, { label: '需求人', value: selected.requester_name }, { label: '下单日期', value: selected.created_at?.slice(0, 10) || '未记录' }, { label: '需用日期', value: selected.required_date }, ...(selected.workshop_id ? [{ label: '使用车间', value: options.workshops?.find(row => row.id === selected!.workshop_id)?.name || selected.workshop_id }] : []), { label: '用途 / 备注', value: selected.purpose || '—', wide: true }]" :rows="selected.lines.map((line, index) => ({ id: line.id || String(index), label: line.packaging_type, quality: line.paper_quality, specification: line.specification + ' ' + line.dimension_unit, unit: line.unit, rule: line.unit, required: Number(line.quantity), received: Number(line.received_quantity || 0), remaining: remaining(line), progress: progress(line), inTransit: line.remaining_to_ship == null ? undefined : Math.max(0, Number(line.quantity) - Number(line.received_quantity || 0) - Number(line.remaining_to_ship)), remainingToShip: line.remaining_to_ship == null ? undefined : Number(line.remaining_to_ship), acceptance: specialSupplierOrigin(selected!) ? '供应商原送货来源' : specialSupplierAccepted(selected!) ? '已确认' : '待确认', promised: specialSupplierPromise(selected!) || '未承诺', note: line.item_no ? '货号 ' + line.item_no : '未填写货号' }))" :supplier="supplier" rule-label="计数单位">
<template #status>
        <CartonSupplierChangeTasks v-if="supplier && !previewRequest && selected.supplier_confirmation && selected.supplier_confirmation.status !== 'SUPPLIER_ORIGIN'" :factory-id="factoryId" :viewer-key="viewerKey" :source-id="selected.current_version_id" :read-only="supplierReadOnly" @changed="select(selected!.id); emit('changed')" />
        </template>
</CartonOrderDetailContent><div v-if="!previewRequest" class="flex justify-end"><Button type="button" size="sm" @click="purchaseOpen = true">查看采购单</Button></div>
        </template>
        <template v-if="supplier || mode === 'requests' || mode === 'receiving'">
        <div v-if="!supplier" class="flex justify-end"><div class="w-fit"><CartonSpecialOrderActions :can-copy="workspace.can_create" :request="selected" detail :disabled="busy" @action="detailAction" /></div></div>
        <section v-if="receiptOpen && pendingShipments.length" class="space-y-3 rounded-xl border border-amber-200 bg-amber-50 p-4" aria-label="已有待收送货单"><h4 class="text-sm font-bold">请先核对已有送货单</h4><p class="text-xs text-slate-600">已有待收纸品，请沿原单验收，避免重复登记收料。</p><Button v-for="shipment in pendingShipments" :key="shipment.id" variant="outline" :disabled="busy" @click="emit('open-delivery', shipment.delivery_note_no)">{{ shipment.delivery_note_no }} · 前往验收</Button></section>
        <p v-else-if="receiptOpen && !can('can_manual_receive')" role="status" class="rounded-lg border bg-slate-50 p-3 text-sm">当前订单暂不可手动收料，请核对锁单状态、权限及剩余需求。</p>
        <CartonSpecialManualReceipt v-if="manualStarted" v-show="receiptOpen && !pendingShipments.length && can('can_manual_receive')" :key="selected.id" :request="selected" :locations="locations" :viewer-key="viewerKey" :disabled="supplier" @saved="manualSaved" @busy="busy = $event" @cancel="receiptOpen = false" @open-delivery="emit('open-delivery', $event)" @locations-changed="load" />

        </template>
        <CartonMarkAssetLibrary v-if="supplier && supplierReadOnly && !previewRequest" :factory-id="factoryId" :order-id="selected.id" :supplier-issue-id="selected.current_version_id" supplier read-only />
        <section class="space-y-3 border-t border-slate-200 pt-4" aria-label="逐纸品箱唛" v-if="!previewRequest && (!supplier || !supplierReadOnly) && (supplier || mode === 'marks' || selected.mark_assets?.length || selected.attachments.some(file => file.role !== 'REFERENCE'))">
          <h4 class="text-sm font-bold text-slate-950">箱唛资料</h4><p class="text-xs text-slate-500">箱唛可选，不必声明是否需要。经办人可直接上传或关联资料，无需关联审批；资料不改变采购数量、价格、接单或送货资格，历史送货保留当时版本。</p>
          <div v-if="selected.mark_assets?.length" class="space-y-2 rounded-lg border bg-slate-50 p-3" aria-label="本单关联箱唛原件"><div v-for="file in selected.mark_assets" :key="`${file.id}:${file.line_id || ''}`" class="flex flex-wrap items-center gap-2 text-xs"><span class="min-w-0 flex-1 break-all">{{ file.file_name }} · 版本 {{ file.revision }} · {{ file.line_id ? selected.lines.find(line => line.id === file.line_id)?.packaging_type || '指定纸品' : '整单资料' }}</span><Button v-if="file.kind !== 'excel'" size="sm" variant="outline" :disabled="busy" @click="openAssociatedMark(file, true)">预览原件</Button><Button size="sm" variant="outline" :disabled="busy" @click="openAssociatedMark(file)">下载原件</Button></div></div>
          <div v-for="line in (lineId ? selected.lines.filter(row => row.id === lineId) : selected.lines)" :key="line.id" :data-mark-line="line.id" class="space-y-3 rounded-xl border border-slate-200 p-4 text-sm">
            <div class="flex flex-wrap items-center justify-between gap-2"><b class="min-w-0 break-words">{{ line.packaging_type }}<span class="ml-2 font-normal text-slate-500">{{ line.item_no || line.specification }}</span></b><span class="rounded-full px-2.5 py-1 text-xs" :class="hasAssociatedMark(line) ? 'bg-slate-100 text-slate-700' : 'bg-slate-50 text-slate-500'">{{ hasAssociatedMark(line) ? '已有资料关联' : '尚未关联资料（选填）' }}</span></div>
            <div v-if="line.mark_attachment_id" class="flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 p-3"><span class="min-w-0 flex-1 break-all text-xs">本单已关联资料：{{ selected.attachments.find(file => file.id === line.mark_attachment_id)?.filename || '箱唛资料' }}</span><Button v-if="canPreview(selected.attachments.find(file => file.id === line.mark_attachment_id)?.filename || '')" size="sm" variant="outline" @click="preview(line.mark_attachment_id, selected.attachments.find(file => file.id === line.mark_attachment_id)?.filename || '箱唛资料')">预览</Button><Button size="sm" variant="outline" :disabled="busy" @click="download(line.mark_attachment_id, selected.attachments.find(file => file.id === line.mark_attachment_id)?.filename || '箱唛资料')">下载</Button></div>
            <div class="flex flex-wrap gap-2"><Button v-if="can('can_attach')" size="sm" variant="outline" :disabled="busy" @click="loadMarkOptions(line.id!)">选择已有箱唛</Button><Button v-if="can('can_attach')" size="sm" variant="outline" :disabled="busy" @click="markUploadLine = markUploadLine === line.id ? '' : line.id!">上传箱唛</Button></div>
            <form v-if="markUploadLine === line.id && can('can_attach')" class="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3" :aria-label="`${line.id}箱唛上传`" @submit.prevent="upload(line.id)"><label>选择箱唛文件<input type="file" accept=".pdf,.xlsx,.png,.jpg,.jpeg,.webp" :aria-label="`${line.id}箱唛文件`" :disabled="busy" @change="chooseMarkFile(line.id!, $event)"></label><p class="text-xs text-slate-500">支持 PDF、XLSX、JPG、PNG、WebP，单个文件最多 10 MiB。上传后由本次经办人直接关联本单，保留原文件及历史。</p><Button size="sm" :disabled="busy || !markFiles[line.id!]">上传并关联资料</Button></form>
            <div v-if="markPickerLine === line.id" class="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3"><label>查找资料<input v-model="markSearch" aria-label="查找已有箱唛" placeholder="文件名或合同号"></label><div class="flex flex-wrap items-end gap-2"><label class="min-w-0 flex-1">已有箱唛<select v-model="markAsset[line.id!]" :aria-label="`${line.id}已有箱唛`"><option value="">选择文件及版本</option><option v-for="asset in filteredMarkChoices" :key="asset.id" :value="asset.id">{{ asset.file_name }} · {{ asset.contract_number || '未关联合同' }} · 版本 {{ asset.revision }}</option></select></label><Button size="sm" :disabled="busy || !markAsset[line.id!]" @click="setMark(line)">关联此资料</Button></div><p v-if="!filteredMarkChoices.length" class="text-xs text-slate-500">暂无可选资料，可上传新的箱唛。</p></div>
            <div v-if="pendingDrafts(line.id).length" class="space-y-2 border-t border-slate-100 pt-3"><p class="text-xs font-semibold text-amber-800">已关联文件与历史</p><p v-if="line.mark_attachment_id && line.mark_ready" class="text-xs text-slate-500">原有关联和确认历史继续保留；新增资料仅记录本次关联，不自动视为审核通过。</p><div v-for="file in pendingDrafts(line.id)" :key="file.id" class="flex flex-wrap items-center gap-2"><span class="min-w-0 flex-1 break-all text-xs">{{ file.filename }}</span><Button v-if="canPreview(file.filename)" size="sm" variant="ghost" @click="preview(file.id, file.filename)">预览</Button><Button size="sm" variant="ghost" @click="download(file.id, file.filename)">下载</Button></div></div>
            <details v-if="selected.attachments.some(file => file.line_id === line.id && file.role === 'CONFIRMED' && file.id !== line.mark_attachment_id)" class="text-xs text-slate-500"><summary class="cursor-pointer">历史版本</summary><div v-for="file in selected.attachments.filter(file => file.line_id === line.id && file.role === 'CONFIRMED' && file.id !== line.mark_attachment_id)" :key="file.id" class="mt-2 flex flex-wrap items-center justify-between gap-2"><span class="break-all">{{ file.filename }}</span><Button size="sm" variant="ghost" @click="download(file.id, file.filename)">下载历史稿</Button></div></details>
          </div>
          <div v-if="previewFile" class="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-3" aria-label="箱唛预览"><div class="flex items-center justify-between gap-2"><b class="min-w-0 break-all text-xs">{{ previewFile.name }}</b><Button size="sm" variant="outline" @click="closePreview">关闭预览</Button></div><img v-if="previewFile.image" :src="previewFile.url" :alt="previewFile.name" class="max-h-[60vh] max-w-full object-contain"><iframe v-else :src="previewFile.url" :title="previewFile.name" class="h-[60vh] w-full rounded-lg border border-slate-200 bg-white" /></div>
        </section>
        <template v-if="mode !== 'marks' && mode !== 'detail'">
        <details :open="!supplier" class="space-y-2 border-t pt-4" aria-label="送货与收货记录">
          <summary role="button" class="text-sm font-bold">送货与收货记录</summary>
          <p v-if="!selected.shipments?.length" class="text-xs text-muted-foreground">尚未登记送货。</p>
          <div v-for="shipment in selected.shipments" :key="shipment.id" class="space-y-3 rounded-lg border p-3 text-xs">
            <div class="flex flex-wrap items-center justify-between gap-2"><b>{{ shipment.delivery_note_no }} · {{ shipment.delivery_date }}</b><Button v-if="can('can_receive') && shipment.lines.some(line => Number(line.remaining_quantity) > 0)" size="sm" variant="outline" :disabled="busy" @click="openReceive(shipment)">登记仓库验收</Button></div>
            <p v-if="shipment.source_origin === 'WAREHOUSE_MANUAL'" class="text-amber-800">仓库代录实际收料 · 价格以双方核对结果为准</p>
            <details class="text-muted-foreground"><summary class="cursor-pointer">发货时资料 · 版本记录</summary><p class="mt-2 break-all">{{ shipment.version_id }}</p><div v-for="line in shipment.lines" :key="line.id" class="mt-2"><span>{{ line.snapshot?.packaging_type }} · {{ markModes[line.snapshot?.mark_mode || 'PENDING'] }}</span><Button v-if="line.snapshot?.mark_attachment_id" size="sm" variant="ghost" @click="download(line.snapshot.mark_attachment_id, selected.attachments.find(file => file.id === line.snapshot?.mark_attachment_id)?.filename || '发货箱唛')">下载本批箱唛</Button></div></details>
            <div v-for="line in shipment.lines" :key="line.id" class="space-y-1 rounded-lg bg-muted/30 p-2">
              <p>{{ line.snapshot?.packaging_type || '原发货纸品' }} · {{ line.snapshot?.paper_quality || '原记录未提供纸质' }} · {{ line.snapshot?.specification || '原记录未提供规格' }} {{ line.snapshot?.dimension_unit }}</p>
              <p>发货 {{ line.quantity }} {{ line.snapshot?.unit }} · 累计实收 {{ line.gross_received_quantity ?? line.received_quantity }} · 有效入库 {{ line.effective_received_quantity ?? line.received_quantity }} · 待验收 {{ line.remaining_quantity }}</p>
              <p v-if="line.snapshot && shipment.source_origin === 'WAREHOUSE_MANUAL'">仓库记录单价：{{ line.snapshot.warehouse_unit_price == null ? '未填写' : `CNY ${line.snapshot.warehouse_unit_price} / ${line.snapshot.unit}` }} · 仓库记录，不代表供应商原价</p>
              <p v-else-if="line.snapshot">送货单价：{{ pricing[line.snapshot.pricing_kind || 'PENDING_QUOTE'] }} · CNY {{ line.snapshot.unit_price ?? '待核实' }} / {{ line.snapshot.unit }}</p>
            </div>
            <details v-for="receipt in shipment.receipts" :key="receipt.id" class="rounded-lg border p-2"><summary class="cursor-pointer font-semibold text-primary">{{ receipt.receipt_no || receipt.id }} · {{ receipt.acceptance_date }} · {{ receipt.status === 'REVERSED' ? '已冲销' : '验收记录' }}</summary><p v-for="(line, index) in receipt.lines || []" :key="line.id || index" class="mt-2">{{ line.packaging_type }} · {{ line.paper_quality }} · {{ line.specification }} · 实收 {{ line.received_quantity }} · 破损 {{ line.damaged_quantity }} · 拒收 {{ line.rejected_quantity }} · 其他不可用 {{ line.unusable_quantity }} · 有效入库 {{ line.effective_quantity }} {{ line.unit }} · {{ shipment.source_origin === 'WAREHOUSE_MANUAL' ? '库存记录价' : '单价' }} CNY {{ line.unit_price }}<span v-if="shipment.source_origin === 'WAREHOUSE_MANUAL'"> · 价格以双方核对结果为准</span></p></details>
          </div>
        </details>

        <details :open="!supplier" class="space-y-3 border-t border-slate-200 pt-4" aria-label="备注附件"><summary role="button" class="text-sm font-bold">备注附件</summary><p class="text-xs text-slate-500">说明、参考图片等放在这里；印刷箱唛统一在箱唛资料库维护。</p><p v-if="!selected.attachments.some(file => file.role === 'REFERENCE')" class="text-xs text-slate-500">暂无备注附件。</p><div v-for="attachment in selected.attachments.filter(file => file.role === 'REFERENCE')" :key="attachment.id" class="flex min-w-0 flex-wrap items-center justify-between gap-2 text-xs"><span class="min-w-0 break-all">{{ attachment.filename }}</span><Button variant="ghost" size="sm" :disabled="busy" @click="download(attachment.id, attachment.filename)">下载附件</Button></div><form v-if="can('can_attach') && (supplier || mode === 'requests' || mode === 'receiving')" class="space-y-2" aria-label="备注附件上传" @submit.prevent="upload()"><div class="grid gap-3 sm:grid-cols-2"><label>对应纸品<select v-model="attachmentLine" aria-label="附件对应纸品" :disabled="busy"><option v-for="line in selected.lines" :key="line.id" :value="line.id">{{ line.packaging_type }} · {{ line.specification }}</option></select></label><label>选择文件<input type="file" aria-label="备注附件文件" :disabled="busy" @change="chooseFile"></label></div><Button variant="outline" :disabled="busy || !attachmentFile">上传备注附件</Button></form></details>
        <details :open="!supplier" class="space-y-3 border-t pt-4"><summary role="button" class="text-sm font-bold">协作消息</summary><p v-if="!selected.messages?.length" class="text-xs text-muted-foreground">暂无消息。</p><div v-for="message in selected.messages" :key="message.id" class="rounded-lg bg-muted/40 p-3 text-xs"><p class="text-muted-foreground">{{ message.actor_name || message.author_name }} · {{ message.created_at }}</p><p class="mt-1 whitespace-pre-wrap break-words">{{ message.body }}</p></div><form v-if="can('can_message') && (supplier || mode === 'requests' || mode === 'receiving')" class="space-y-2" @submit.prevent="messageBody.trim() && act('messages', 'can_message', { body: messageBody.trim() })"><label>消息<textarea v-model="messageBody" aria-label="特殊申请消息" rows="2" maxlength="4000" required :disabled="busy" /></label><Button variant="outline" :disabled="busy || !messageBody.trim()">发送消息</Button></form></details>
        <details class="border-t pt-3 text-xs" aria-label="操作历史"><summary class="cursor-pointer font-semibold">操作历史（{{ selected.history?.length || 0 }}）</summary><p v-for="(history, index) in selected.history" :key="history.id || index" class="mt-2 break-words text-muted-foreground">{{ history.created_at }} · {{ history.actor_name }} · {{ history.action === 'ADJUSTED' ? '调整订单' : history.action === 'MANUAL_RECEIVED' ? '仓库登记收料' : actions[history.action] || '单据变更' }}<template v-if="history.note"> · {{ history.note }}</template></p></details>
        </template>
      </article>
      <p v-else class="rounded-xl border border-dashed bg-card p-6 text-sm text-muted-foreground">选择订单以查看纸品、资料及送货进度。</p>
    </div>
    <CartonOrderActionDialog teleport v-if="(cancelConfirm || deleteConfirm) && selected" :title="(deleteConfirm ? '删除订单 ' : '取消订单 ') + selected.request_no" :description="deleteConfirm ? '删除后从订单台账移除，原订单、版本和历史证据保留。未取消且已有供应商执行、附件或收料的订单不可删除。' : '取消后不能继续送货，原订单及操作历史保留。已有送货记录时须先核实处理。'" :busy="busy" :disabled="deleteConfirm ? !can('can_delete') : !can('can_cancel')" danger :reason-label="deleteConfirm ? '删除原因' : undefined" reason-aria="订单删除原因" :reason-max="1000" v-model:reason="deleteReason" :error="error" :submit-label="deleteConfirm ? '确认删除订单' : '确认取消订单'" @close="cancelConfirm = false; deleteConfirm = false" @submit="deleteConfirm ? deleteOrder() : act('cancel', 'can_cancel')" />
    <CartonOrderActionDialog teleport v-if="confirmOpen && selected" title="确认并锁单" description="请核对本单需求。确认后供应商可接收订单；后续修改须填写调整原因，已有送货和收料记录保留。" :busy="busy" :disabled="!can('can_confirm')" :error="error" back-label="返回核对" submit-label="核对无误，确认锁单" @close="confirmOpen = false" @submit="act('confirm', 'can_confirm')"><CartonOrderSummary :fields="[{ label: '单号', value: selected.request_no }, { label: '类型', value: kinds[selected.kind] }, { label: '客户', value: selected.customer_name || '未关联客户' }, { label: '需求人', value: selected.requester_name }, { label: '需用日期', value: selected.required_date }]" /><p v-for="line in selected.lines" :key="line.id" class="text-xs">{{ line.packaging_type }} · {{ line.item_no || '未填货号' }} · {{ line.specification }} {{ line.dimension_unit }} · {{ quantity(line.quantity) }} {{ line.unit }} · {{ hasAssociatedMark(line) ? '有箱唛资料关联' : '箱唛资料选填' }}</p></CartonOrderActionDialog>
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
