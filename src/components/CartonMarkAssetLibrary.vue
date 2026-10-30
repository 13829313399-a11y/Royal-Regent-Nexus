<script setup lang="ts">
import CartonFilterBar from '@/components/CartonFilterBar.vue'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Download, Eye, FileSpreadsheet, FileText, FolderOpen, Image as ImageIcon, RefreshCw, UploadCloud } from '@lucide/vue'
import { cartonSupplierPortalApi, type SupplierMarkAsset } from '@/api/cartonSupplierPortal'
import { http } from '@/lib/http'
import { cartonMarkApi, type CartonMarkAsset, type CartonMarkAssetUploadResult, type CartonMarkBindingTarget, type CartonMarkAssociationTarget } from '@/api/cartonMark'
import { createRandomUuid } from '@/lib/randomUuid'
import { getApiErrorMessage, getApiErrorMessageAsync } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'
import { factoryContexts } from '@/data/enterpriseMock'

const props = defineProps<{ factoryId: string; search?: string; assetIds?: string[]; supplierFactories?: string[]; orderId?: string; supplierIssueId?: string; readOnly?: boolean; supplier?: boolean; supplierCheckEnabled?: boolean; uploadOnly?: boolean; checkEnabled?: boolean }>()
const emit = defineEmits<{ changed: []; 'update:search': [value: string]; use: [asset: CartonMarkAsset]; useSources: [assets: CartonMarkAsset[]]; manualReview: [assets: CartonMarkAsset[]]; supplierReview: [assets: (SupplierMarkAsset & { factory_id: string })[]]; supplierExcel: [asset: SupplierMarkAsset & { factory_id: string }]; supplierGeneratePdf: [asset: SupplierMarkAsset & { factory_id: string }]; supplierSources: [assets: (SupplierMarkAsset & { factory_id: string })[]] }>()
const auth = useAuthStore()
const canRead = computed(() => props.supplier ? auth.can('carton_supplier:read') : ['pmc-warehouse', 'carton', 'qa', 'qc'].some(d => auth.can('carton_mark:read', props.factoryId, d)))
const canWrite = computed(() => !props.supplier && !props.readOnly && ['pmc-warehouse', 'carton'].some(d => auth.can('carton_mark:template_upload', props.factoryId, d)))
const entries = ref<CartonMarkAsset[]>([])
const supplierSources = ref<(SupplierMarkAsset & { factory_id: string })[]>([])
const recipients = ref<{ id: string; name: string }[]>([])
const recipientsLoading = ref(false), recipientsError = ref('')
const uploadSharing = ref<'SUPPLIER' | 'INTERNAL'>('SUPPLIER'), uploadSupplierId = ref('')
const sharingAsset = ref<CartonMarkAsset | null>(null)
const sharingPanel = ref<HTMLElement | null>(null), targetPanel = ref<HTMLElement | null>(null)
const sharingMode = ref<'SUPPLIER' | 'INTERNAL'>('SUPPLIER'), sharingSupplierId = ref('')
const targetAsset = ref<CartonMarkAsset | null>(null), bindingTargets = ref<CartonMarkBindingTarget[]>([])
const targetQuery = ref(''), targetOrderId = ref(''), targetLineId = ref(''), targetLoading = ref(false), targetError = ref('')
const targetOrder = computed(() => bindingTargets.value.find(row => row.order_id === targetOrderId.value))
const keptTargets = ref<{ order_id: string; order_kind: CartonMarkBindingTarget['order_kind']; line_id: string; label: string }[]>([])
const orderKindLabels = { REGULAR: '正单', SAMPLE: '样板', MISC: '杂单' }
const orderTypeFilter = ref('ALL')
function specialOrders(asset: CartonMarkAsset) {
  const rows = new Map<string, NonNullable<CartonMarkAsset['special_orders']>[number]>()
  for (const row of asset.special_orders ?? []) rows.set(`${row.order_id}:${row.line_id}`, row)
  return [...rows.values()]
}
function assetIsBound(asset: CartonMarkAsset) { return asset.binding_status === 'BOUND' || !!asset.special_orders?.length }
const matchingTargets = computed(() => bindingTargets.value.filter(row => [row.order_no, row.contract_no, row.customer_name, row.item_no, orderKindLabels[row.order_kind]].join(' ').toLowerCase().includes(targetQuery.value.trim().toLowerCase())))
let targetSequence = 0, targetRequestId = ''
const canBind = (asset: CartonMarkAsset) => props.supplier ? !props.orderId && auth.can('carton_supplier:edit', asset.factory_id, '*') : canWrite.value
const sharingLabel = (asset: CartonMarkAsset) => asset.sharing_mode === 'INTERNAL' ? '仅内部可见' : asset.sharing_mode === 'SUPPLIER' ? `共享给 ${asset.shared_supplier_name || '对应供应商'}` : '按订单权限共享'
async function loadRecipients() {
  const current = generation
  recipientsLoading.value = true; recipientsError.value = ''
  try {
    const rows = await cartonMarkApi.shareRecipients(props.factoryId, controller.signal)
    if (current === generation) { recipients.value = rows; uploadSupplierId.value = rows.length === 1 ? rows[0]!.id : '' }
  } catch (cause) { if (current === generation) recipientsError.value = getApiErrorMessage(cause) }
  finally { if (current === generation) recipientsLoading.value = false }
}
function editSharing(asset: CartonMarkAsset) {
  if (!canWrite.value || busy.value) return
  sharingAsset.value = asset; sharingMode.value = asset.sharing_mode === 'INTERNAL' ? 'INTERNAL' : 'SUPPLIER'
  sharingSupplierId.value = asset.shared_supplier_id || (recipients.value.length === 1 ? recipients.value[0]!.id : '')
  void nextTick(() => sharingPanel.value?.scrollIntoView?.({ behavior: 'smooth', block: 'center' }))
}
async function saveSharing() {
  const asset = sharingAsset.value
  if (!asset || !canWrite.value || busy.value) return
  if (sharingMode.value === 'SUPPLIER' && !recipients.value.some(row => row.id === sharingSupplierId.value)) { error.value = '请选择共享给哪家供应商。'; return }
  const current = generation; busy.value = true; error.value = ''
  try {
    await cartonMarkApi.setAssetSharing(props.factoryId, asset, sharingMode.value, sharingMode.value === 'SUPPLIER' ? sharingSupplierId.value : undefined, controller.signal)
    if (current === generation) { sharingAsset.value = null; await refresh() }
  } catch (cause) { if (current === generation) error.value = getApiErrorMessage(cause) }
  finally { if (current === generation) busy.value = false }
}
async function openTarget(asset: CartonMarkAsset) {
  if (!canBind(asset) || busy.value || asset.workflow?.status === 'HISTORY') return
  if (asset.photo_group_id) {
    if (canWrite.value) await editPhotoGroup(asset)
    return
  }
  closeBinding()
  const current = generation, sequence = ++targetSequence
  targetAsset.value = asset; bindingTargets.value = []; targetOrderId.value = ''; targetLineId.value = ''; targetQuery.value = ''; targetError.value = ''; targetLoading.value = true
  targetRequestId = createRandomUuid()
  keptTargets.value = asset.associations?.map(row => ({ order_id: row.order_id, order_kind: row.order_kind, line_id: row.line_id || '', label: `${orderKindLabels[row.order_kind]} · ${row.order_no || row.contract_no}` })) ?? [
    ...[...new Set([...(asset.bound_order_ids ?? []), ...(asset.bound_order_id ? [asset.bound_order_id] : []), ...asset.orders.map(row => row.id)])].map(id => {
      const order = asset.orders.find(row => row.id === id)
      return { order_id: id, order_kind: 'REGULAR' as const, line_id: '', label: `正单 · ${order?.order_no || order?.contract_no || id}` }
    }),
    ...specialOrders(asset).map(row => ({ order_id: row.order_id, order_kind: row.order_kind, line_id: row.line_id || '', label: `${orderKindLabels[row.order_kind]} · ${row.order_no}` })),
  ]
  void nextTick(() => targetPanel.value?.scrollIntoView?.({ behavior: 'smooth', block: 'center' }))
  try {
    const rows = await cartonMarkApi.bindingTargets(asset.factory_id, !!props.supplier, controller.signal)
    if (current === generation && sequence === targetSequence) bindingTargets.value = rows
  } catch (cause) { if (current === generation && sequence === targetSequence) targetError.value = getApiErrorMessage(cause) }
  finally { if (current === generation && sequence === targetSequence) targetLoading.value = false }
}
function closeTarget() { targetSequence++; targetAsset.value = null; targetLoading.value = false; bindingTargets.value = []; keptTargets.value = []; targetError.value = '' }
watch(targetOrderId, () => { targetLineId.value = ''; targetRequestId = createRandomUuid() })
watch(targetLineId, () => { targetRequestId = createRandomUuid() })
function removeTarget(index: number) { keptTargets.value.splice(index, 1); targetRequestId = createRandomUuid() }
async function saveTarget() {
  const asset = targetAsset.value, order = targetOrder.value
  if (!asset || !canBind(asset) || busy.value || targetLoading.value) return
  if (targetLineId.value && !order?.lines.some(row => row.id === targetLineId.value)) { targetError.value = '所选纸品已变化，请刷新订单。'; return }
  const chosen = [...keptTargets.value, ...(order ? [{ order_id: order.order_id, order_kind: order.order_kind, line_id: targetLineId.value, label: '' }] : [])]
  const targets: CartonMarkAssociationTarget[] = []
  for (const selected of chosen) {
    const currentTarget = bindingTargets.value.find(row => row.order_id === selected.order_id && row.order_kind === selected.order_kind)
    if (!currentTarget) { targetError.value = '原关联订单已不可选，请核实后移除该项或刷新。'; return }
    if (!targets.some(row => row.order_id === selected.order_id && row.order_kind === selected.order_kind && row.line_id === selected.line_id)) targets.push({ order_id: currentTarget.order_id, order_kind: currentTarget.order_kind, expected_revision: currentTarget.revision, issue_id: currentTarget.issue_id || '', line_id: selected.line_id })
  }
  const current = generation; busy.value = true; targetError.value = ''
  try {
    const saved = await cartonMarkApi.associateAsset(asset.factory_id, asset, targets, targetRequestId, !!props.supplier, controller.signal)
    if (current === generation) {
      results.value = results.value.map(row => row.asset?.id === asset.id ? { ...row, asset: saved } : row)
      closeTarget(); emit('changed'); await refresh()
    }
  } catch (cause) { if (current === generation) targetError.value = `资料原件已保留，仅订单关联未完成：${getApiErrorMessage(cause)}。可重试关联，无需重新上传。` }
  finally { if (current === generation) busy.value = false }
}
function chooseManualReview(asset: CartonMarkAsset) {
  if (busy.value || asset.kind === 'excel') return
  const files = asset.kind === 'image' && asset.photo_group_id ? entries.value.filter(row => row.factory_id === asset.factory_id && row.photo_group_id === asset.photo_group_id) : [asset]
  if (props.supplier) {
    if (!props.supplierCheckEnabled || !auth.can('carton_supplier:edit', asset.factory_id, '*')) return
    emit('supplierReview', files.map(file => supplierSources.value.find(row => row.id === file.id && row.factory_id === file.factory_id)!).filter(Boolean))
  } else if (canWrite.value && props.checkEnabled) emit('manualReview', files)
}
function chooseSupplierExcel(asset: CartonMarkAsset, generate = false) {
  if (!props.supplier || !props.supplierCheckEnabled || busy.value || !auth.can('carton_supplier:edit', asset.factory_id, '*')) return
  const source = supplierSources.value.find(row => row.id === asset.id && row.factory_id === asset.factory_id && row.kind === 'excel')
  if (source) {
    if (generate) emit('supplierGeneratePdf', source)
    else emit('supplierExcel', source)
  }
}
const results = ref<CartonMarkAssetUploadResult[]>([])
const pendingFiles = ref<File[]>([])
const pendingOptions = ref<import('@/api/cartonMark').CartonMarkUploadOptions[]>([])
const replacement = ref<CartonMarkAsset | null>(null)
const usageLabels = { UNCLASSIFIED: '待分类', DRAFT: '待打版', PENDING: '待确认', READY: '已确认可用', HISTORY: '历史版本' }
const usageFilter = ref('ALL')
const usageOf = (asset: CartonMarkAsset) => asset.workflow?.status || 'UNCLASSIFIED'
const statusEditing = ref<CartonMarkAsset | null>(null)
const statusValue = ref<Exclude<import('@/api/cartonMark').CartonMarkUsageStatus, 'UNCLASSIFIED'>>('DRAFT')
const statusNote = ref('')
const statusHistory = ref<{ revision: number; workflow: import('@/api/cartonMark').CartonMarkAssetWorkflow }[]>([])
const statusHistoryLoading = ref(false)
const statusError = ref('')
let statusSequence = 0
async function editStatus(asset: CartonMarkAsset) {
  if (!canWrite.value || busy.value) return
  const current = generation, sequence = ++statusSequence
  statusEditing.value = asset
  statusValue.value = usageOf(asset) === 'UNCLASSIFIED' ? 'DRAFT' : asset.workflow!.status as typeof statusValue.value
  statusNote.value = asset.workflow?.note || ''
  statusHistory.value = []; statusError.value = ''; statusHistoryLoading.value = true
  try {
    const history = await cartonMarkApi.assetClassificationHistory(props.factoryId, asset.id, controller.signal)
    if (current === generation && sequence === statusSequence) statusHistory.value = history
  } catch (cause) {
    if (current === generation && sequence === statusSequence) statusError.value = getApiErrorMessage(cause)
  } finally {
    if (current === generation && sequence === statusSequence) statusHistoryLoading.value = false
  }
}
function closeStatus() { statusSequence++; statusEditing.value = null; statusHistory.value = []; statusError.value = '' }
async function saveStatus() {
  if (!canWrite.value || busy.value || !statusEditing.value) return
  const current = generation
  busy.value = true; statusError.value = ''
  try {
    await cartonMarkApi.classifyAsset(props.factoryId, statusEditing.value, statusValue.value, statusNote.value, controller.signal)
    if (current === generation) { closeStatus(); await refresh() }
  } catch (cause) {
    if (current === generation) statusError.value = getApiErrorMessage(cause)
  } finally { if (current === generation) busy.value = false }
}
function uploadRevision(asset: CartonMarkAsset) {
  if (!canWrite.value || busy.value) return
  replacement.value = asset; pendingFiles.value = []; pendingOptions.value = []; results.value = []
  fileInput.value?.click()
}
const fileInput = ref<HTMLInputElement | null>(null)
const sourcePanel = ref<HTMLElement | null>(null)
const sourceGroup = ref(''), sourceExcelId = ref(''), sourcePdfId = ref('')
function groupKey(asset: CartonMarkAsset) {
  const customer = [...new Set(asset.orders.map(order => order.customer_name))].sort().join('、')
  return JSON.stringify(asset.photo_group_id ? [asset.factory_id, 'photos', asset.photo_group_id] : [asset.factory_id, asset.orders.length ? contractsLabel(asset) : asset.contract_number || asset.id, customer])
}
const sourceCandidates = computed(() => {
  const anchor = entries.value.find(asset => groupKey(asset) === sourceGroup.value)
  return entries.value.filter(asset => asset.kind !== 'image' && usageOf(asset) !== 'HISTORY' && anchor && asset.factory_id === anchor.factory_id
    && (groupKey(asset) === sourceGroup.value || asset.orders.some(order => anchor.orders.some(row => row.id === order.id))))
})
const sourceExcels = computed(() => sourceCandidates.value.filter(asset => asset.kind === 'excel'))
const sourcePdfs = computed(() => sourceCandidates.value.filter(asset => asset.kind === 'pdf'))
const selectedSources = computed(() => [sourceExcels.value.find(asset => asset.id === sourceExcelId.value), sourcePdfs.value.find(asset => asset.id === sourcePdfId.value)])
function chooseSources(key: string) {
  const candidate = entries.value.find(asset => groupKey(asset) === key)
  if (busy.value || !(canWrite.value && props.checkEnabled || props.supplier && props.supplierCheckEnabled && candidate && auth.can('carton_supplier:edit', candidate.factory_id, '*'))) return
  sourceGroup.value = key
  sourceExcelId.value = sourceExcels.value.length === 1 ? sourceExcels.value[0]!.id : ''
  sourcePdfId.value = sourcePdfs.value.length === 1 ? sourcePdfs.value[0]!.id : ''
  void nextTick(() => sourcePanel.value?.scrollIntoView?.({ behavior: 'smooth', block: 'center' }))
}
function useSources() {
  if (props.supplier) {
    if (!props.supplierCheckEnabled || busy.value || selectedSources.value.some(asset => !asset)) return
    const [excel, pdf] = selectedSources.value.map(asset => supplierSources.value.find(row => row.id === asset!.id && row.factory_id === asset!.factory_id))
    if (!excel || !pdf || excel.factory_id !== pdf.factory_id || !auth.can('carton_supplier:edit', excel.factory_id, '*')) return
    const orders = excel.orders.filter(order => pdf.orders.some(row => row.id === order.id && row.issue_id === order.issue_id))
    if (!orders.length) { error.value = 'Excel 与 PDF 没有共同的采购订单，请选择同一订单的文件。'; return }
    emit('supplierSources', [{ ...excel, orders }, pdf]); sourceGroup.value = ''; return
  }
  if (!canWrite.value || !props.checkEnabled || busy.value || selectedSources.value.some(asset => !asset || asset.factory_id !== props.factoryId)) return
  const [excel, pdf] = selectedSources.value
  if (excel!.orders.length && pdf!.orders.length && !excel!.orders.some(order => pdf!.orders.some(row => row.id === order.id))) {
    error.value = 'Excel 与 PDF 没有共同的关联订单，请选择同一订单的文件。'
    return
  }
  emit('useSources', selectedSources.value as CartonMarkAsset[])
  sourceGroup.value = ''
}
const localQuery = ref('')
const query = computed({
  get: () => props.search ?? localQuery.value,
  set: (value: string) => { if (props.search === undefined) localQuery.value = value; else emit('update:search', value) },
})
const onlyUnbound = ref(false)
const kindFilter = ref('ALL')
const bindingFilter = ref('ALL'), customerFilter = ref(''), sort = ref('LATEST')
const customers = computed(() => [...new Set(entries.value.flatMap(asset => asset.orders.map(order => order.customer_name)))].sort((a, b) => a.localeCompare(b, 'zh-CN')))
function resetFilters() { kindFilter.value = 'ALL'; onlyUnbound.value = false; bindingFilter.value = 'ALL'; customerFilter.value = ''; usageFilter.value = 'ALL'; orderTypeFilter.value = 'ALL' }
function clearFilters() { query.value = ''; resetFilters() }
const busy = ref(false)
const loading = ref(false)
const error = ref('')
const binding = ref<CartonMarkAsset | null>(null)
const bindingPanel = ref<HTMLDivElement | null>(null)
const bindingPhotos = ref<CartonMarkAsset[]>([])
const bindingGroupId = ref<string>()
const selectedPhotos = ref<string[]>([])
const selectedPhotoAssets = computed(() => entries.value.filter(asset => selectedPhotos.value.includes(asset.id) && asset.kind === 'image'))
const allOrders = ref<CartonMarkAsset['orders']>([])
const orderQuery = ref('')
const ordersLoading = ref(false)
const orderOptions = computed(() => {
  const options = allOrders.value.length ? allOrders.value : binding.value?.orders ?? []
  const search = orderQuery.value.trim().toLowerCase()
  return options.filter(order => (!contract.value.trim() || search || order.contract_no.toLowerCase() === contract.value.trim().toLowerCase() || order.id === boundOrderId.value)
    && (!search || [order.contract_no, order.customer_name, order.order_no, order.item_no].some(value => value.toLowerCase().includes(search))))
})
const gallery = ref<CartonMarkAsset[]>([])
let bindingSequence = 0
const contract = ref('')
const boundOrderId = ref('')
const multipleContracts = ref(false)
const boundOrderIds = ref<string[]>([])
const invalidBoundOrderIds = computed(() => boundOrderIds.value.filter(id => !allOrders.value.some(order => order.id === id)))
const multiOrderOptions = computed(() => allOrders.value.filter(order => !orderQuery.value.trim() || [order.contract_no, order.customer_name, order.order_no, order.item_no].some(value => value.toLowerCase().includes(orderQuery.value.trim().toLowerCase()))))
function contractsLabel(asset: CartonMarkAsset) { return [...new Set(asset.orders.map(order => order.contract_no))].join('、') || asset.contract_number || '未识别' }
let controller = new AbortController()
let generation = 0
let listSequence = 0
const statuses = { BOUND: '已关联订单', NO_ORDER: '等待订单', UNBOUND: '未关联订单', AMBIGUOUS: '需确认订单' }
function factoryDisplayName(id: string) { return factoryContexts.find(factory => factory.id === id)?.shortName ?? id }
const visible = computed(() => entries.value.filter(asset => {
  const key = query.value.trim().toLowerCase()
  return (!props.assetIds || props.assetIds.includes(asset.id))
    && (kindFilter.value === 'ALL' || asset.kind === kindFilter.value) && (!onlyUnbound.value || !assetIsBound(asset))
    && (orderTypeFilter.value === 'ALL' || (orderTypeFilter.value === 'REGULAR' ? asset.orders.length > 0 : asset.special_orders?.some(row => row.order_kind === orderTypeFilter.value)))
    && (usageFilter.value === 'ALL' ? usageOf(asset) !== 'HISTORY' : usageOf(asset) === usageFilter.value)
    && (bindingFilter.value === 'ALL' || (assetIsBound(asset) ? 'BOUND' : asset.binding_status) === bindingFilter.value)
    && (!customerFilter.value || asset.orders.some(order => order.customer_name === customerFilter.value)) && (!key ||
    [asset.file_name, asset.contract_number, ...asset.orders.flatMap(o => [o.contract_no, o.order_no, o.customer_name, o.item_no]), ...(asset.special_orders ?? []).map(row => row.order_no)].some(v => v.toLowerCase().includes(key)))
}))
const groups = computed(() => {
  const grouped = new Map<string, { key: string; factory: string; contract: string; customer: string; latest: string; photoGroupId: string | null; assets: CartonMarkAsset[] }>()
  for (const asset of visible.value) {
    const customer = [...new Set(asset.orders.map(order => order.customer_name))].sort().join('、')
    const key = groupKey(asset)
    const group = grouped.get(key) ?? { key, factory: asset.factory_id, contract: contractsLabel(asset), customer, latest: '', photoGroupId: asset.photo_group_id ?? null, assets: [] }
    group.assets.push(asset); if (asset.created_at > group.latest) group.latest = asset.created_at
    grouped.set(key, group)
  }
  return [...grouped.values()].sort((a, b) => (sort.value === 'CONTRACT' ? a.contract.localeCompare(b.contract, 'zh-CN', { numeric: true }) : sort.value === 'CUSTOMER' ? a.customer.localeCompare(b.customer, 'zh-CN') : b.latest.localeCompare(a.latest)) || a.key.localeCompare(b.key))
    .map(group => ({ ...group, assets: group.assets.sort((a, b) => Number(usageOf(b) === 'READY') - Number(usageOf(a) === 'READY') || a.kind.localeCompare(b.kind) || b.created_at.localeCompare(a.created_at) || a.id.localeCompare(b.id)) }))
})

async function refresh() {
  if (!canRead.value) return
  const current = generation
  const sequence = ++listSequence
  const factory = props.factoryId
  loading.value = true
  error.value = ''
  try {
    let records: CartonMarkAsset[]
    if (props.supplier) {
      const scopes = [...new Set(props.supplierFactories ?? (factory ? [factory] : []))]
      const batches = await Promise.all(scopes.map(async scope => {
        try {
          const assets = await cartonSupplierPortalApi.markAssets(scope, controller.signal)
          return { scope, assets: props.orderId ? assets.flatMap(asset => {
            const orders = asset.orders.filter(order => order.id === props.orderId && order.issue_id === props.supplierIssueId)
            const special = asset.associations?.some(order => order.order_kind !== 'REGULAR' && order.order_id === props.orderId && order.issue_id === props.supplierIssueId)
            return orders.length || special ? [{ ...asset, orders }] : []
          }) : assets }
        }
        catch (cause) { throw new Error(`${factoryDisplayName(scope)}：${getApiErrorMessage(cause)}`) }
      }))
      if (current === generation && sequence === listSequence) supplierSources.value = batches.flatMap(({ scope, assets }) => assets.map(asset => ({ ...asset, factory_id: scope })))
      records = batches.flatMap(({ scope, assets }) => assets.map(asset => ({
        ...asset, factory_id: scope, sha256: '', bound_order_id: null, recognition_source: '', candidates: [], warning: '',
        created_by_name: '', binding_status: asset.binding_status ?? (asset.orders.length ? 'BOUND' as const : 'UNBOUND' as const), orders: asset.orders.map(order => ({ ...order, order_no: '' })),
      })))
      records.sort((a, b) => b.created_at.localeCompare(a.created_at) || a.factory_id.localeCompare(b.factory_id) || b.id.localeCompare(a.id))
    } else records = await cartonMarkApi.listAssets(factory, props.orderId, controller.signal)
    if (current === generation && sequence === listSequence) {
      entries.value = records
      selectedPhotos.value = selectedPhotos.value.filter(id => records.some(asset => asset.id === id))
      const previewing = gallery.value[0]
      if (previewing) gallery.value = records.filter(asset => asset.factory_id === previewing.factory_id && asset.photo_group_id === previewing.photo_group_id)
    }
  } catch (cause) {
    if (current === generation && sequence === listSequence) {
      if (props.supplier) { entries.value = []; supplierSources.value = [] }
      gallery.value = []
      error.value = getApiErrorMessage(cause)
    }
  } finally {
    if (current === generation && sequence === listSequence) loading.value = false
  }
}

function selectFiles(files: File[]) {
  if (!canWrite.value || busy.value) return
  if (replacement.value && files.length > 1) { error.value = '每次请选择一个修改稿文件。'; return }
  pendingFiles.value = files
  pendingOptions.value = files.map(() => ({ status: replacement.value ? 'PENDING' : 'DRAFT', note: '', request_id: createRandomUuid(),
    ...(replacement.value ? { previous_asset_id: replacement.value.id, previous_revision: replacement.value.revision } : {}) }))
  results.value = []
  error.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

async function upload() {
  if (!canWrite.value || busy.value || !pendingFiles.value.length) return
  const current = generation
  const factory = props.factoryId
  const files = [...pendingFiles.value]
  const options = pendingOptions.value.map(option => ({ ...option }))
  if (!replacement.value && uploadSharing.value === 'SUPPLIER' && !recipients.value.some(row => row.id === uploadSupplierId.value)) {
    error.value = '请选择共享给哪家供应商，或选择仅内部可见。'; return
  }
  if (!replacement.value) options.forEach(option => { option.sharing_mode = uploadSharing.value; option.supplier_id = uploadSharing.value === 'SUPPLIER' ? uploadSupplierId.value : undefined })
  if (files.length > 50 || files.reduce((sum, file) => sum + file.size, 0) > 100 * 1024 * 1024 || files.some(file => file.size > 20 * 1024 * 1024)) {
    error.value = '每批最多 50 个文件、合计 100 MB，单个文件最多 20 MB。'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const outcomes = await cartonMarkApi.uploadAssets(factory, files, controller.signal, options)
    if (current !== generation) return
    results.value = outcomes
    pendingFiles.value = files.filter((_, index) => !outcomes[index] || outcomes[index]?.status === 'failed')
    pendingOptions.value = options.filter((_, index) => !outcomes[index] || outcomes[index]?.status === 'failed')
    if (!pendingFiles.value.length) replacement.value = null
    if (outcomes.some(result => result.asset && result.status !== 'failed')) emit('changed')
    await refresh()
  } catch (cause) {
    if (current === generation) error.value = `上传结果尚未确认：${getApiErrorMessage(cause)}。请先刷新核实结果；保持原文件和选项不变重试会核实原请求，选择新文件才另建副本。`
  } finally {
    if (current === generation) busy.value = false
  }
}

function photoMembers(groupId: string, factory = props.factoryId) { return entries.value.filter(asset => asset.factory_id === factory && asset.photo_group_id === groupId) }
function togglePhoto(asset: CartonMarkAsset, checked: boolean) {
  const ids = (asset.photo_group_id ? photoMembers(asset.photo_group_id, asset.factory_id) : [asset]).map(photo => photo.id)
  selectedPhotos.value = checked ? [...new Set([...selectedPhotos.value, ...ids])] : selectedPhotos.value.filter(id => !ids.includes(id))
}
async function editPhotoGroup(asset: CartonMarkAsset, photos: CartonMarkAsset[] = [], groupId?: string) {
  if (!canWrite.value || busy.value || usageOf(asset) === 'HISTORY') return
  const members = photos.length ? photos : asset.photo_group_id ? photoMembers(asset.photo_group_id, asset.factory_id) : []
  if (!members.length) return
  closeTarget()
  binding.value = asset
  bindingPhotos.value = [...members]
  bindingGroupId.value = groupId ?? (photos.length ? undefined : asset.photo_group_id ?? undefined)
  const targets = members.length ? members : [asset]
  contract.value = targets.every(photo => photo.contract_number === asset.contract_number) ? asset.contract_number : ''
  boundOrderId.value = targets.every(photo => photo.bound_order_id === asset.bound_order_id) ? asset.bound_order_id || '' : ''
  multipleContracts.value = targets.some(photo => photo.recognition_source === 'manual_orders')
  boundOrderIds.value = multipleContracts.value ? [...new Set(targets.flatMap(photo =>
    photo.bound_order_ids?.length ? photo.bound_order_ids : photo.orders.map(order => order.id)))] : []
  orderQuery.value = ''
  error.value = ''
  void nextTick(() => bindingPanel.value?.scrollIntoView?.({ behavior: 'smooth', block: 'center' }))
  const current = generation, sequence = ++bindingSequence
  ordersLoading.value = true
  try {
    const orders = await cartonMarkApi.bindingOrders(props.factoryId, controller.signal)
    if (current === generation && sequence === bindingSequence) allOrders.value = orders
  } catch (cause) {
    if (current === generation && sequence === bindingSequence) error.value = `读取可关联订单失败：${getApiErrorMessage(cause)}；仍可填写合同号。`
  } finally {
    if (current === generation && sequence === bindingSequence) ordersLoading.value = false
  }
}

function closeBinding() { bindingSequence++; binding.value = null; bindingPhotos.value = []; ordersLoading.value = false }
function createPhotoGroup() {
  const photos = selectedPhotoAssets.value
  if (photos.length >= 2 && photos.length <= 50 && photos[0]) void editPhotoGroup(photos[0], photos)
}
function chooseOrder() {
  const selected = allOrders.value.find(order => order.id === boundOrderId.value) ?? binding.value?.orders.find(order => order.id === boundOrderId.value)
  if (selected) contract.value = selected.contract_no
}

async function ungroup(groupId: string) {
  if (!canWrite.value || busy.value || !window.confirm('解除照片分组？各照片保留原文件和当前订单关联。')) return
  const current = generation
  busy.value = true
  try {
    await cartonMarkApi.ungroupPhotos(props.factoryId, groupId, photoMembers(groupId), controller.signal)
    if (current !== generation) return
    selectedPhotos.value = []; closeBinding(); await refresh()
  } catch (cause) { if (current === generation) error.value = getApiErrorMessage(cause) }
  finally { if (current === generation) busy.value = false }
}

async function saveBinding() {
  if (!binding.value || !bindingPhotos.value.length || busy.value || !canWrite.value) return
  const current = generation
  if (multipleContracts.value && !boundOrderIds.value.length) { error.value = '请勾选至少一张关联订单。'; return }
  if (multipleContracts.value && boundOrderIds.value.length > 100) { error.value = '一次最多关联 100 张订单，请减少选择。'; return }
  const orderIds = multipleContracts.value ? [...boundOrderIds.value] : undefined
  const contractNumber = multipleContracts.value ? '' : contract.value.trim()
  const orderId = multipleContracts.value ? '' : boundOrderId.value
  busy.value = true
  try {
    await cartonMarkApi.savePhotoGroup(props.factoryId, bindingPhotos.value, contractNumber, orderId, bindingGroupId.value, controller.signal, orderIds)
    if (current !== generation) return
    closeBinding(); selectedPhotos.value = []
    await refresh()
  } catch (cause) {
    if (current === generation) error.value = getApiErrorMessage(cause)
  } finally {
    if (current === generation) busy.value = false
  }
}

async function download(asset: CartonMarkAsset) {
  const current = generation
  try {
    const blob = props.supplier
      ? await cartonSupplierPortalApi.downloadMarkAsset(asset.id, asset.factory_id, controller.signal)
      : await cartonMarkApi.downloadAsset(props.factoryId, asset.id, controller.signal)
    if (current !== generation) return
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = asset.file_name
    anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (cause) {
    const detail = await getApiErrorMessageAsync(cause)
    if (current === generation) error.value = detail
  }
}

async function archive(asset: CartonMarkAsset) {
  if (busy.value || !canWrite.value || !window.confirm(`将“${asset.file_name}”移出资料仓库？原文件会保留，重新上传会另存一份新资料。`)) return
  const current = generation
  busy.value = true
  try {
    await cartonMarkApi.archiveAsset(props.factoryId, asset, controller.signal)
    if (current === generation) await refresh()
  } catch (cause) {
    if (current === generation) error.value = getApiErrorMessage(cause)
  } finally {
    if (current === generation) busy.value = false
  }
}

function previewUrl(asset: CartonMarkAsset) {
  return props.supplier ? cartonSupplierPortalApi.previewMarkAssetUrl(asset.id, asset.factory_id)
    : http.getUri({ url: `/carton-mark/assets/${encodeURIComponent(asset.id)}/document`, params: { factory_id: props.factoryId, preview: true } })
}
function chooseFiles() { if (canWrite.value && !busy.value) fileInput.value?.click() }
defineExpose({ chooseFiles, refresh })
watch([() => props.factoryId, () => props.supplierFactories?.join('\0'), () => props.orderId, () => props.supplierIssueId,
  () => props.supplier, canRead, canWrite, () => auth.currentUser?.id, () => auth.authorizationVersion], () => {
  generation++
  controller.abort()
  controller = new AbortController()
  entries.value = []
  supplierSources.value = []
  results.value = []
  pendingFiles.value = []
  pendingOptions.value = []; replacement.value = null; closeStatus()
  recipients.value = []; recipientsError.value = ''; recipientsLoading.value = false; uploadSharing.value = 'SUPPLIER'; uploadSupplierId.value = ''
  sharingAsset.value = null; closeTarget()
  closeBinding(); selectedPhotos.value = []; allOrders.value = []; gallery.value = []
  sourceGroup.value = ''; sourceExcelId.value = ''; sourcePdfId.value = ''
  contract.value = ''
  boundOrderId.value = ''
  error.value = ''
  busy.value = false
  loading.value = false
  localQuery.value = ''; resetFilters(); sort.value = 'LATEST'
  if (canRead.value) void refresh()
  if (canWrite.value) void loadRecipients()
}, { immediate: true })
onBeforeUnmount(() => { generation++; controller.abort() })
</script>

<template>
  <section v-if="canRead" class="rounded-xl border border-slate-200 bg-white p-4 sm:p-5" :style="{ '--asset-actions-width': canWrite ? '14rem' : '10rem' }" aria-label="箱唛资料仓库">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="flex items-center gap-2 text-base font-bold text-slate-900"><FolderOpen class="size-5 text-teal-700" />{{ uploadOnly ? '批量上传箱唛资料' : '箱唛资料库' }}</h2>
        <p class="mt-1 text-xs leading-5 text-slate-500">{{ orderId ? '此订单关联的箱唛原文件，可直接查看和下载。历史版本请切换分类查看。' : supplier ? '仓库与本供应商共享的箱唛原文件，未关联订单也可查看、下载；由经办人直接关联正单、样板或杂单，关联保留具体文件版本。' : 'PDF、Excel、图片上传后即可与所选供应商共享，不必先关联订单；需要时直接关联正单、样板或杂单。每次独立保存，不覆盖原资料。' }}</p>
        <p v-if="!supplier && !orderId" class="text-xs leading-5 text-slate-500">图片支持 JPG、PNG、WebP。无需改照片名：上传后可搜索订单手动关联，或勾选多张照片组成组、整组关联。同合同命名可自动识别，如 4500000123_正唛.jpg。</p>
      </div>
      <button v-if="!uploadOnly" type="button" :disabled="busy || loading" class="inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-xs disabled:opacity-50" @click="refresh"><RefreshCw class="size-3.5" />刷新</button>
    </div>
    <div v-if="canWrite" class="mt-4 rounded-lg border-2 border-dashed border-teal-200 bg-teal-50/50 p-4" @dragover.prevent @drop.prevent="selectFiles(Array.from($event.dataTransfer?.files ?? []))">
      <div v-if="replacement" class="mb-3 flex flex-wrap items-center gap-2 rounded-lg bg-white p-3 text-xs text-teal-800"><span>上传修改稿：{{ replacement.file_name }} · 新版本保留原关联，确认后原稿移入历史。</span><button type="button" :disabled="busy" class="ml-auto underline" @click="replacement = null; pendingFiles = []; pendingOptions = []">取消修改稿</button></div>
      <input ref="fileInput" type="file" multiple accept=".pdf,.xls,.xlsx,.xlsm,.jpg,.jpeg,.png,.webp" class="hidden" aria-label="批量选择箱唛原文件" @change="selectFiles(Array.from(($event.target as HTMLInputElement).files ?? []))">
      <div v-if="!replacement" class="mb-3 flex flex-wrap items-end gap-3 text-sm">
        <label>上传后谁可以查看<select v-model="uploadSharing" aria-label="上传资料共享范围" :disabled="busy" class="mt-1 block h-10 max-w-full rounded-lg border bg-white px-3"><option value="SUPPLIER">仓库与对应供应商共享</option><option value="INTERNAL">仅内部可见</option></select></label>
        <label v-if="uploadSharing === 'SUPPLIER'">对应供应商<select v-model="uploadSupplierId" aria-label="上传资料共享供应商" :disabled="busy || recipientsLoading" class="mt-1 block h-10 max-w-full rounded-lg border bg-white px-3"><option value="">请选择供应商</option><option v-for="recipient in recipients" :key="recipient.id" :value="recipient.id">{{ recipient.name }}</option></select></label>
        <p v-if="recipientsLoading" role="status" class="text-xs text-slate-500">正在读取供应商…</p>
        <p v-else-if="recipientsError" role="alert" class="text-xs text-red-700">供应商读取失败：{{ recipientsError }} <button type="button" class="underline" @click="loadRecipients">重试</button></p>
        <p v-else-if="uploadSharing === 'SUPPLIER' && !recipients.length" class="text-xs text-amber-700">当前厂区暂无可共享的供应商，可先选择仅内部可见。</p>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <button type="button" :disabled="busy" class="inline-flex items-center gap-2 rounded-lg border bg-white px-3 py-2 font-semibold disabled:opacity-50" @click="chooseFiles"><UploadCloud class="size-4" />选择多个文件</button>
        <span class="text-xs text-slate-500">或拖入文件 · 单个 20 MB · 每批最多 50 个 / 100 MB</span>
        <button type="button" :disabled="busy || !pendingFiles.length" class="rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white disabled:opacity-50" @click="upload">{{ busy ? '处理中…' : `上传入库${pendingFiles.length ? `（${pendingFiles.length}）` : ''}` }}</button>
      </div>
      <div v-if="pendingFiles.length" class="mt-3 max-h-72 space-y-3 overflow-y-auto">
        <div v-for="(file, index) in pendingFiles" :key="index" class="grid gap-2 rounded-lg border border-teal-100 bg-white p-3 sm:grid-cols-[minmax(0,1fr)_auto]">
          <p class="break-all text-xs font-semibold text-slate-700">{{ file.name }}</p>
          <select v-model="pendingOptions[index]!.status" :disabled="busy" :aria-label="`${file.name} 上传分类 ${index + 1}`" class="h-9 rounded-lg border px-2 text-xs"><option value="DRAFT">待打版</option><option value="PENDING">待确认</option><option v-if="!replacement" value="READY">已确认可用</option></select>
          <input v-model="pendingOptions[index]!.note" :disabled="busy" maxlength="500" :aria-label="`${file.name} 资料备注 ${index + 1}`" :placeholder="pendingOptions[index]!.status === 'READY' ? '确认依据（选填），如客户邮件、签样或历史确认稿' : '资料备注（选填）'" class="h-9 rounded-lg border px-3 text-xs sm:col-span-2">
        </div>
      </div>
      <p class="mt-2 text-xs text-slate-500">每份文件可单独选择分类，上传后仍可修改；已确认的历史稿可直接登记为“已确认可用”。</p>
    </div>
    <p v-if="error" role="alert" class="mt-3 rounded-lg bg-red-50 p-3 text-xs text-red-700">{{ error }}</p>
    <div v-if="results.length" class="mt-3 space-y-1 rounded-lg bg-slate-50 p-3 text-xs" role="status">
      <p v-for="(result, index) in results" :key="index" :class="result.status === 'failed' ? 'text-red-700' : 'text-teal-800'" class="break-all">{{ result.file_name }}：{{ ({ created: '已入库', duplicate: '已存在，保留原关联', restored: '已恢复', failed: '未入库' })[result.status] }}{{ result.message ? ` — ${result.message}` : '' }} <button v-if="result.asset && result.status !== 'failed'" type="button" :disabled="busy" class="ml-2 underline" @click="openTarget(result.asset)">关联订单</button></p>
    </div>
    <template v-if="!uploadOnly">
      <nav aria-label="箱唛资料分类" class="mt-4 flex flex-wrap gap-2">
        <button type="button" :aria-current="usageFilter === 'ALL' ? 'page' : undefined" class="rounded-lg border px-3 py-2 text-xs font-semibold" :class="usageFilter === 'ALL' ? 'border-teal-600 bg-teal-700 text-white' : 'bg-white text-slate-600'" @click="usageFilter = 'ALL'">全部</button>
        <button v-for="state in (['DRAFT', 'PENDING', 'READY', 'UNCLASSIFIED', 'HISTORY'] as const)" :key="state" type="button" :aria-current="usageFilter === state ? 'page' : undefined" class="rounded-lg border px-3 py-2 text-xs font-semibold" :class="usageFilter === state ? 'border-teal-600 bg-teal-700 text-white' : 'bg-white text-slate-600'" @click="usageFilter = state">{{ usageLabels[state] }} <span class="ml-1 tabular-nums">{{ entries.filter(asset => usageOf(asset) === state).length }}</span></button>
      </nav>
      <CartonFilterBar v-if="!orderId" label="箱唛资料筛选" class="mt-4 rounded-lg"><label v-if="search === undefined">关键字<input v-if="search === undefined" v-model="query" aria-label="搜索箱唛资料" placeholder="搜索合同号、客户、货号或文件名…" class="h-10 min-w-0 basis-full flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm sm:basis-auto"></label><label>文件格式<select v-model="kindFilter" aria-label="箱唛文件类型" class="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm"><option value="ALL">全部格式</option><option value="pdf">PDF</option><option value="excel">Excel</option><option value="image">图片</option></select></label><label>订单类型<select v-model="orderTypeFilter" aria-label="箱唛关联订单类型" class="h-10 rounded-lg border bg-white px-3 text-sm"><option value="ALL">全部订单类型</option><option v-for="(label, kind) in orderKindLabels" :key="kind" :value="kind">{{ label }}</option></select></label><label>客户<select v-model="customerFilter" aria-label="箱唛客户筛选" class="h-10 rounded-lg border bg-white px-3 text-sm"><option value="">全部客户</option><option v-for="customer in customers" :key="customer">{{ customer }}</option></select></label><label>关联状态<select v-model="bindingFilter" aria-label="箱唛关联状态" class="h-10 rounded-lg border bg-white px-3 text-sm"><option value="ALL">全部关联状态</option><option v-for="(label, state) in statuses" :key="state" :value="state">{{ label }}</option></select></label><label>排序<select v-model="sort" aria-label="箱唛资料排序" class="h-10 rounded-lg border bg-white px-3 text-sm"><option value="LATEST">最近上传的合同优先</option><option value="CONTRACT">合同号排序</option><option value="CUSTOMER">客户排序</option></select></label><label class="carton-filter-check"><input v-model="onlyUnbound" type="checkbox">只看待关联</label><template #actions><button type="button" class="h-10 rounded-lg border bg-white px-3 text-xs" @click="clearFilters">清除筛选</button><button type="button" class="h-10 rounded-lg border bg-white px-3 text-xs" @click="sort = 'LATEST'">恢复默认排序</button></template><template #footer><span class="whitespace-nowrap text-xs text-slate-500">{{ visible.length }} 份资料</span></template></CartonFilterBar>
      <div v-if="canWrite" class="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-600">
        <span>已选 {{ selectedPhotoAssets.length }} 张照片</span>
        <button type="button" :disabled="busy || selectedPhotoAssets.length < 2 || selectedPhotoAssets.length > 50" class="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 font-semibold text-teal-700 disabled:opacity-50" @click="createPhotoGroup">组成照片组</button>
        <button v-if="selectedPhotoAssets.length" type="button" class="text-teal-700" @click="selectedPhotos = []">清空选择</button>
        <span>每组最多 50 张；选择组内照片会选中整组，包括筛选外照片。</span>
      </div>
      <p v-if="loading" class="py-6 text-center text-sm text-slate-500">正在读取资料…</p>
      <div v-else-if="!error && !visible.length" class="mt-4 rounded-xl border border-dashed border-slate-200 px-4 py-12 text-center">
        <FolderOpen class="mx-auto size-8 text-slate-300" /><p class="mt-3 text-sm text-slate-500">{{ entries.length ? '没有符合筛选条件的箱唛资料。' : supplier ? '暂无可查看的共享资料。仓库共享给本供应商或本供应商上传后，即可在这里查看，无需先关联订单。' : orderId ? '此订单暂无已关联箱唛资料。可在订单管理的箱唛资料库上传或关联。' : '暂无资料，上传后会长期保存在当前厂区。' }}</p>
      </div>
      <div v-if="visible.length" class="mt-4 overflow-hidden rounded-xl border border-slate-200">
      <div class="mark-library-columns hidden gap-6 border-b border-slate-200 bg-slate-50 px-4 py-3 text-xs font-semibold text-slate-500 lg:grid"><span>{{ supplier && supplierFactories ? '厂区 / 合同 / 客户 / 货号' : '合同 / 客户 / 货号' }}</span><span>原文件</span><span>关联状态 / 上传日期</span><span class="text-right">操作</span></div>
      <ul class="divide-y divide-slate-100">
        <template v-for="group in groups" :key="group.key">
        <li class="flex flex-wrap items-center gap-2 bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-600" :aria-label="`箱唛合同分组 ${group.contract || '未识别'}`">
          <span v-if="supplier && supplierFactories">{{ factoryDisplayName(group.factory) }} ·</span>
          <span v-if="group.photoGroupId" class="rounded bg-blue-100 px-2 py-1 text-blue-700">照片组</span>
          <span>合同 {{ group.contract || '未识别' }}</span><span>{{ group.customer }}</span><span class="ml-auto">{{ group.assets.length }} 份原文件<span v-if="group.photoGroupId && photoMembers(group.photoGroupId, group.factory).length !== group.assets.length"> / 整组 {{ photoMembers(group.photoGroupId, group.factory).length }} 张</span></span>
          <button v-if="(canWrite && checkEnabled || supplier && supplierCheckEnabled && auth.can('carton_supplier:edit', group.factory, '*')) && group.assets.some(asset => asset.kind !== 'image' && usageOf(asset) !== 'HISTORY')" type="button" :disabled="busy" class="rounded border border-teal-200 bg-white px-3 py-1.5 text-teal-700" :aria-label="`选择合同 ${group.contract || '未识别'} 的 Excel / PDF 核对文件`" @click="chooseSources(group.key)">选择 Excel / PDF 核对</button>
          <button v-if="group.photoGroupId" type="button" class="rounded border bg-white px-2 py-1.5" @click="gallery = photoMembers(group.photoGroupId, group.factory)">查看照片组</button>
          <button v-if="canWrite && group.photoGroupId" type="button" :disabled="busy" class="rounded border bg-white px-2 py-1.5" @click="ungroup(group.photoGroupId)">解除分组</button>
        </li>
        <li v-for="asset in group.assets" :key="`${asset.factory_id}:${asset.id}`" :data-asset-id="asset.id" class="mark-library-columns grid items-start gap-4 px-4 py-4 lg:min-h-24 lg:gap-6">
          <div class="col-span-2 min-w-0 lg:col-span-1">
            <label v-if="canWrite && asset.kind === 'image'" class="mb-2 flex items-center gap-2 text-xs text-slate-500"><input type="checkbox" :aria-label="`选择照片 ${asset.file_name}`" :checked="selectedPhotos.includes(asset.id)" :disabled="busy" @change="togglePhoto(asset, ($event.target as HTMLInputElement).checked)">{{ asset.photo_group_id ? '选择整组' : '选择照片' }}</label>
            <p class="break-all text-sm font-bold leading-5 text-slate-900">合同号：{{ contractsLabel(asset) }}</p>
            <p v-if="supplier && supplierFactories" class="mt-1 text-xs font-semibold leading-5 text-teal-700">{{ factoryDisplayName(asset.factory_id) }}</p>
            <p v-for="order in asset.orders" :key="order.id" class="mt-1 break-all text-xs leading-5 text-slate-500">{{ order.customer_name }} · {{ order.contract_no }} · {{ order.item_no }}<span v-if="!supplier && order.order_no"> · {{ order.order_no }}</span></p>
            <p v-for="order in specialOrders(asset)" :key="`${order.order_id}:${order.line_id}`" class="mt-1 break-all text-xs leading-5 text-slate-500">{{ orderKindLabels[order.order_kind] }} · {{ order.order_no }} · 资料已关联<span v-if="order.confirmed"> · 历史确认记录保留</span></p>
          </div>
          <div class="col-span-2 flex min-w-0 items-start gap-2 lg:col-span-1">
            <span class="flex size-8 shrink-0 items-center justify-center rounded-lg" :class="asset.kind === 'pdf' ? 'bg-red-50 text-red-600' : asset.kind === 'image' ? 'bg-blue-50 text-blue-600' : 'bg-teal-50 text-teal-700'"><FileText v-if="asset.kind === 'pdf'" class="size-4" /><ImageIcon v-else-if="asset.kind === 'image'" class="size-4" /><FileSpreadsheet v-else class="size-4" /></span>
            <div class="min-w-0"><p class="text-sm font-semibold leading-5 text-slate-800 [overflow-wrap:anywhere]">{{ asset.file_name }}</p><p class="mt-1 text-xs leading-5 text-slate-400">{{ asset.kind === 'pdf' ? 'PDF' : asset.kind === 'image' ? '图片' : 'Excel' }} · {{ (asset.size_bytes / 1024).toFixed(0) }} KB · {{ asset.created_at.slice(0, 19).replace('T', ' ') }} · {{ asset.id.slice(-6) }}</p></div>
          </div>
          <div class="min-w-0 text-xs">
            <span class="mb-2 inline-flex rounded-full px-2 py-1 font-semibold" :class="usageOf(asset) === 'READY' ? 'bg-emerald-100 text-emerald-800' : usageOf(asset) === 'PENDING' ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-600'">{{ usageLabels[usageOf(asset)] }} · V{{ asset.workflow?.version || 1 }}</span>
            <p v-if="['DRAFT', 'PENDING', 'UNCLASSIFIED'].includes(usageOf(asset))" class="mb-2 text-amber-700">资料状态供参考，不作为订单关联或送货门槛</p>
            <p v-if="asset.workflow?.note" class="mb-2 whitespace-pre-wrap break-words leading-5 text-slate-600">{{ asset.workflow.note }}</p>
            <p v-if="asset.workflow?.confirmed_at" class="mb-2 leading-5 text-slate-500">确认记录：{{ asset.workflow.confirmed_by_name }} · {{ asset.workflow.confirmed_at.slice(0, 10) }}</p>
            <span class="inline-flex rounded-full px-2 py-1 leading-4" :class="assetIsBound(asset) ? 'bg-teal-50 text-teal-700' : 'bg-amber-50 text-amber-700'">{{ assetIsBound(asset) ? '已关联订单' : statuses[asset.binding_status] }}</span>
            <p class="mt-2 break-words leading-5 text-slate-500">{{ sharingLabel(asset) }}</p>
            <div v-for="proposal in asset.pending_bindings ?? []" :key="proposal.id" class="mt-2 rounded-lg bg-amber-50 p-2 leading-5 text-amber-800">
              <p>历史关联提议：{{ proposal.contract_no || proposal.order_no }} · {{ proposal.item_no }}</p>
              <p class="text-slate-600">可直接使用“关联订单”重新保存，无需继续旧审批。</p>

            </div>
            <p class="mt-1 leading-5 text-slate-400">{{ asset.created_at.slice(0, 10) }}</p>
            <p v-if="asset.warning || asset.binding_status === 'AMBIGUOUS'" class="mt-1 text-amber-700">{{ asset.binding_status === 'AMBIGUOUS' ? '同一合同号对应不同客户，请确认具体订单。' : asset.warning }}</p>
          </div>
          <div class="asset-actions grid min-w-0 grid-cols-2 items-start gap-2 text-xs">
            <button v-if="canBind(asset)" type="button" :disabled="busy || usageOf(asset) === 'HISTORY' || supplier && !!asset.photo_group_id" class="col-span-2 rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1.5 font-semibold text-teal-700 disabled:cursor-not-allowed disabled:opacity-50" @click="openTarget(asset)">关联订单</button>
            <p v-if="canBind(asset) && usageOf(asset) === 'HISTORY'" class="col-span-2 text-slate-500">历史版本，请选择当前原件。</p>
            <p v-else-if="canBind(asset) && asset.photo_group_id" class="col-span-2 text-slate-500">{{ supplier ? '照片组请由仓库经办人整组处理；如需单独关联，请先由仓库解除分组。' : '此入口会修改整组照片的关联；如需单独关联或选择样板、杂单，请先解除分组。' }}</p>
            <a v-if="asset.kind === 'pdf' || asset.kind === 'image'" :href="previewUrl(asset)" :aria-label="`预览 ${asset.file_name}`" target="_blank" rel="noopener" class="inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3"><Eye class="size-3.5" />预览</a>
            <span v-else aria-hidden="true" class="h-8"></span>
            <button type="button" :aria-label="`下载 ${asset.file_name}`" class="inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3" @click="download(asset)"><Download class="size-3.5" />下载</button>
            <button v-if="canWrite" type="button" :disabled="busy" class="rounded-lg border px-2.5 py-1.5" @click="editSharing(asset)">共享范围</button>
            <button v-if="canWrite" type="button" :disabled="busy" :aria-label="`修改 ${asset.file_name} 状态`" class="rounded-lg border px-2.5 py-1.5 text-teal-700" @click="editStatus(asset)">修改状态</button>
            <button v-if="canWrite && usageOf(asset) !== 'HISTORY' && !asset.photo_group_id" type="button" :disabled="busy" :aria-label="`上传 ${asset.file_name} 修改稿`" class="rounded-lg border px-2.5 py-1.5" @click="uploadRevision(asset)">上传修改稿</button>
            <button v-if="canWrite" type="button" :disabled="busy" class="rounded-lg px-2.5 py-1.5 text-slate-400" @click="archive(asset)">移出</button>
            <button v-if="usageOf(asset) !== 'HISTORY' && canWrite && checkEnabled && asset.kind !== 'image'" type="button" :disabled="busy" class="col-span-2 rounded-lg bg-teal-50 px-2.5 py-1.5 font-semibold text-teal-700" @click="emit('use', asset)">用于{{ asset.kind === 'pdf' ? 'PDF' : 'Excel' }}核对</button>
            <button v-if="usageOf(asset) !== 'HISTORY' && supplier && supplierCheckEnabled && asset.kind === 'excel' && auth.can('carton_supplier:edit', asset.factory_id, '*')" type="button" :disabled="busy" class="col-span-2 rounded-lg bg-teal-50 px-2.5 py-1.5 font-semibold text-teal-700" @click="chooseSupplierExcel(asset)">选择 Excel 并上传 PDF 核对</button>
            <button v-if="usageOf(asset) !== 'HISTORY' && supplier && supplierCheckEnabled && asset.kind === 'excel' && auth.can('carton_supplier:edit', asset.factory_id, '*')" type="button" :disabled="busy" class="col-span-2 rounded-lg bg-teal-50 px-2.5 py-1.5 font-semibold text-teal-700" :aria-label="`由 ${asset.file_name} 生成 PDF`" @click="chooseSupplierExcel(asset, true)">生成 PDF</button>
            <button v-if="usageOf(asset) !== 'HISTORY' && asset.kind !== 'excel' && (canWrite && checkEnabled || supplier && supplierCheckEnabled && auth.can('carton_supplier:edit', asset.factory_id, '*'))" type="button" :disabled="busy" class="col-span-2 rounded-lg bg-amber-50 px-2.5 py-1.5 font-semibold text-amber-800" @click="chooseManualReview(asset)">{{ asset.photo_group_id ? '整组图片提交人工审核' : '提交人工审核' }}</button>
          </div>
        </li>
        </template>
      </ul>
      </div>
      <div v-if="sourceGroup && (canWrite && checkEnabled || supplier && supplierCheckEnabled)" ref="sourcePanel" role="dialog" aria-label="选择仓库核对文件" class="mt-4 rounded-xl border border-teal-200 bg-teal-50 p-4">
        <p class="font-semibold">从同一合同的原文件选择 Excel 与打印 PDF</p>
        <p class="mt-1 text-xs text-slate-600">包含列表筛选隐藏的同合同文件；多个版本请明确选择。带入后仍需提交内容核对，通过或人工放行后才可供 QC 使用。</p>
        <div class="mt-3 grid gap-3 sm:grid-cols-2">
          <label class="text-xs">客人 Excel<select v-model="sourceExcelId" aria-label="仓库核对 Excel" class="mt-1 h-10 w-full rounded border bg-white px-2"><option value="">请选择 Excel</option><option v-for="asset in sourceExcels" :key="asset.id" :value="asset.id">{{ asset.file_name }} · {{ asset.created_at.slice(0, 19).replace('T', ' ') }} · {{ asset.id.slice(-6) }}</option></select></label>
          <label class="text-xs">打印 PDF<select v-model="sourcePdfId" aria-label="仓库核对 PDF" class="mt-1 h-10 w-full rounded border bg-white px-2"><option value="">请选择 PDF</option><option v-for="asset in sourcePdfs" :key="asset.id" :value="asset.id">{{ asset.file_name }} · {{ asset.created_at.slice(0, 19).replace('T', ' ') }} · {{ asset.id.slice(-6) }}</option></select></label>
        </div>
        <p v-if="!sourceExcels.length || !sourcePdfs.length" class="mt-2 text-xs text-amber-800">此合同缺少 {{ !sourceExcels.length ? 'Excel' : 'PDF' }}，请先上传，或用单个文件的核对入口补选另一份文件。</p>
        <div class="mt-3 flex flex-wrap gap-2"><button type="button" :disabled="busy || selectedSources.some(asset => !asset)" class="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" @click="useSources">带入 Excel / PDF 核对</button><button type="button" class="rounded-lg border bg-white px-4 py-2 text-sm" @click="sourceGroup = ''">取消</button></div>
      </div>
      <div v-if="binding" ref="bindingPanel" role="dialog" aria-label="关联箱唛资料" class="mt-4 rounded-xl border border-teal-200 bg-teal-50 p-4">
        <p class="break-all font-semibold">{{ bindingGroupId ? '关联订单 · 照片组' : '组成照片组' }}：{{ bindingPhotos.length }} 张照片</p>
        <p v-if="bindingPhotos.length" class="mt-2 break-all text-xs text-slate-600">{{ bindingPhotos.map(photo => photo.file_name).join('、') }}。保存后整组使用下面同一合同和关联范围，留空则整组待关联。</p>
        <label v-if="!multipleContracts" class="mt-3 block text-xs">合同号（可留空，保留为待关联）<input v-model="contract" maxlength="128" class="mt-1 block w-full rounded-lg border bg-white px-3 py-2 text-sm" @input="boundOrderId = ''"></label>
        <label class="mt-3 flex items-center gap-2 text-sm font-semibold"><input v-model="multipleContracts" type="checkbox" aria-label="关联多个合同">关联多个合同</label>
        <p v-if="multipleContracts" class="mt-2 text-xs text-slate-500">勾选同一客户的多张合同订单，原文件只保存一份。供应商只看到其获授权订单的关联；后续新增订单需要另行勾选。</p>
        <label class="mt-3 block text-xs">搜索本厂订单<input v-model="orderQuery" aria-label="搜索可关联订单" placeholder="合同号 / 客户 / 货号 / 订单号" class="mt-1 block w-full rounded-lg border bg-white px-3 py-2 text-sm"></label>
        <div v-if="multipleContracts" class="mt-3 max-h-64 space-y-2 overflow-y-auto rounded-lg border bg-white p-3" aria-label="多合同订单列表">
          <label v-for="order in multiOrderOptions" :key="order.id" class="flex items-start gap-2 text-xs"><input v-model="boundOrderIds" type="checkbox" :value="order.id" :aria-label="`关联订单 ${order.order_no}`">{{ order.customer_name }} · {{ order.contract_no }} · {{ order.item_no }} · {{ order.order_no }}</label>
        </div>
        <p v-if="multipleContracts" class="mt-2 text-xs">已选 {{ boundOrderIds.length }} 张订单（最多 100 张）</p>
        <p v-if="multipleContracts && !ordersLoading && !error && invalidBoundOrderIds.length" role="alert" class="mt-2 text-xs text-amber-700">{{ invalidBoundOrderIds.length }} 个原关联订单已取消或删除，请移除后保存。<button type="button" class="ml-2 underline" @click="boundOrderIds = boundOrderIds.filter(id => !invalidBoundOrderIds.includes(id))">移除失效关联</button></p>
        <label v-if="!multipleContracts" class="mt-3 block text-xs">关联范围<select v-model="boundOrderId" aria-label="选择关联订单" class="mt-1 block w-full rounded-lg border bg-white px-3 py-2 text-sm" @change="chooseOrder"><option value="">同一合同的订单共用</option><option v-for="order in orderOptions" :key="order.id" :value="order.id">{{ order.contract_no }} · {{ order.customer_name }} · {{ order.order_no }} · {{ order.item_no }}</option></select></label>
        <p v-if="ordersLoading" class="mt-2 text-xs text-slate-500">正在读取本厂订单…</p>
        <p v-else-if="!orderOptions.length" class="mt-2 text-xs text-slate-500">暂无匹配订单，可搜索其他合同或手工填写合同号，后续订单可共用。</p>
        <p v-if="binding.candidates.length > 1" class="mt-2 text-xs text-amber-700">候选合同号：{{ binding.candidates.join('、') }}</p>
        <div class="mt-3 flex gap-2"><button type="button" :disabled="busy" class="rounded-lg bg-teal-700 px-4 py-2 text-white disabled:opacity-50" @click="saveBinding">保存照片组</button><button type="button" :disabled="busy" class="rounded-lg border bg-white px-4 py-2" @click="closeBinding">取消</button></div>
      </div>
    </template>
    <div v-if="sharingAsset" ref="sharingPanel" role="dialog" aria-label="设置箱唛共享范围" class="mt-4 space-y-3 rounded-xl border border-teal-200 bg-teal-50 p-4">
      <h3 class="break-all font-semibold">共享范围：{{ sharingAsset.file_name }}</h3>
      <p class="text-sm text-slate-600">共享只决定谁可以查看，不代表已关联订单或已确认生产使用。</p>
      <select v-model="sharingMode" aria-label="资料共享范围" :disabled="busy" class="h-10 max-w-full rounded-lg border bg-white px-3"><option value="SUPPLIER">仓库与对应供应商共享</option><option value="INTERNAL">仅内部可见</option></select>
      <select v-if="sharingMode === 'SUPPLIER'" v-model="sharingSupplierId" aria-label="资料共享供应商" :disabled="busy || recipientsLoading" class="ml-2 h-10 max-w-full rounded-lg border bg-white px-3"><option value="">请选择供应商</option><option v-for="recipient in recipients" :key="recipient.id" :value="recipient.id">{{ recipient.name }}</option></select>
      <div class="flex gap-2"><button type="button" :disabled="busy" class="rounded-lg bg-teal-700 px-4 py-2 text-sm text-white" @click="saveSharing">保存共享范围</button><button type="button" :disabled="busy" class="rounded-lg border bg-white px-4 py-2 text-sm" @click="sharingAsset = null">取消</button></div>
    </div>
    <div v-if="targetAsset" ref="targetPanel" role="dialog" aria-label="选择使用箱唛的订单" class="mt-4 space-y-3 rounded-xl border border-teal-200 bg-teal-50 p-4">
      <h3 class="break-all font-semibold">关联订单：{{ targetAsset.file_name }} · V{{ targetAsset.workflow?.version || 1 }}</h3>
      <p class="text-sm leading-6 text-slate-600">核对客户、货号和文件版本后保存，由本次经办人直接关联。保留未移除的原关联；此操作不修改采购数量、单价、接单状态，也不代表资料审核通过。</p>
      <input v-model="targetQuery" aria-label="搜索箱唛绑定目标" :disabled="busy" placeholder="搜索正单、样板、杂单 / 单号 / 客户 / 货号" class="h-10 w-full rounded-lg border bg-white px-3 text-sm">
      <ul v-if="keptTargets.length" class="space-y-2 text-sm" aria-label="保留的订单关联"><li v-for="(target, index) in keptTargets" :key="`${target.order_kind}:${target.order_id}:${target.line_id}`" class="flex items-center justify-between gap-2"><span class="break-all">{{ target.label }}{{ target.line_id ? ' · 已指定纸品' : ' · 整单资料' }}</span><button type="button" :disabled="busy" class="shrink-0 underline" @click="removeTarget(index)">移除此关联</button></li></ul>
      <p v-if="targetLoading" role="status" class="text-sm text-slate-500">正在读取有权限使用的订单…</p>
      <label class="block text-sm">选择订单<select v-model="targetOrderId" aria-label="箱唛绑定订单" :disabled="busy || targetLoading" class="mt-1 h-10 w-full rounded-lg border bg-white px-3"><option value="">请选择订单</option><option v-for="order in matchingTargets" :key="order.order_id" :value="order.order_id">{{ orderKindLabels[order.order_kind] }} · {{ order.customer_name || '未关联客户' }} · {{ order.contract_no || '未填合同' }} · {{ order.order_no }} · {{ order.item_no }}</option></select></label>
      <label v-if="targetOrder && targetOrder.order_kind !== 'REGULAR'" class="block text-sm">对应纸品（选填）<select v-model="targetLineId" aria-label="箱唛绑定纸品" :disabled="busy" class="mt-1 h-10 w-full rounded-lg border bg-white px-3"><option value="">关联整张订单，不指定纸品</option><option v-for="line in targetOrder.lines" :key="line.id" :value="line.id">{{ line.label }}</option></select></label>
      <p v-if="!targetLoading && !matchingTargets.length && !targetError" class="text-sm text-slate-500">暂无匹配订单，可修改搜索；资料已保存在共享库中，无需重复上传。</p>
      <p v-if="targetError" role="alert" class="text-sm text-red-700">{{ targetError }}</p>
      <div class="flex gap-2"><button type="button" :disabled="busy || targetLoading || !!targetError && !bindingTargets.length" class="rounded-lg bg-teal-700 px-4 py-2 text-sm text-white disabled:opacity-50" @click="saveTarget">保存订单关联</button><button type="button" :disabled="busy" class="rounded-lg border bg-white px-4 py-2 text-sm" @click="closeTarget">取消</button></div>
    </div>
    <div v-if="statusEditing" role="dialog" aria-label="修改箱唛资料状态" aria-modal="true" class="fixed inset-0 z-[70] flex items-center justify-center bg-slate-900/50 p-4" @click.self="!busy && closeStatus()">
      <form class="max-h-[85vh] w-full max-w-xl space-y-4 overflow-y-auto rounded-xl bg-white p-5" @submit.prevent="saveStatus">
        <div class="flex items-center justify-between gap-3"><h3 class="font-bold">修改资料状态</h3><button type="button" :disabled="busy" aria-label="关闭资料状态" @click="closeStatus">关闭</button></div>
        <p class="break-all text-sm text-slate-600">{{ statusEditing.file_name }} · V{{ statusEditing.workflow?.version || 1 }}</p>
        <label class="block text-sm font-semibold">资料状态<select v-model="statusValue" :disabled="busy || !!statusEditing.workflow?.superseded_by_asset_id" aria-label="箱唛资料状态" class="mt-2 h-10 w-full rounded-lg border px-3"><option value="DRAFT">待打版</option><option value="PENDING">待确认</option><option value="READY">已确认可用</option><option value="HISTORY">历史版本 / 作废</option></select></label>
        <label class="block text-sm font-semibold">{{ statusValue === 'READY' ? '确认依据（选填）' : '备注（选填）' }}<textarea v-model="statusNote" :disabled="busy" aria-label="箱唛资料状态备注" maxlength="500" rows="3" class="mt-2 w-full rounded-lg border p-3 text-sm" placeholder="例如客户邮件、签样、历史确认稿，或待修改内容"></textarea></label>
        <p v-if="statusValue === 'READY' && statusEditing.workflow?.previous_asset_id" class="text-xs text-amber-700">确认此修改稿后，原稿会移入历史版本。</p>
        <p v-if="statusEditing.workflow?.superseded_by_asset_id" class="text-xs text-slate-500">此稿已被新版本替代，可查看记录或补充备注。</p>
        <p class="text-xs text-slate-500">系统记录操作人、时间和具体版本；资料分类不替代内容核对及 QC 审核。</p>
        <p v-if="statusError" role="alert" class="text-sm text-red-700">{{ statusError }}</p>
        <button type="submit" :disabled="busy" class="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{{ busy ? '正在保存…' : '保存状态' }}</button>
        <details class="border-t pt-3 text-xs"><summary class="cursor-pointer font-semibold">修改记录</summary><p v-if="statusHistoryLoading" class="mt-2">正在读取记录…</p><p v-else-if="!statusHistory.length" class="mt-2 text-slate-500">暂无分类记录</p><div v-for="entry in statusHistory" :key="entry.revision" class="mt-2 border-t pt-2 leading-5"><b>{{ usageLabels[entry.workflow.status] }}</b> · {{ entry.workflow.updated_by_name }} · {{ entry.workflow.updated_at }}<p class="whitespace-pre-wrap break-words">{{ entry.workflow.note }}</p></div></details>
      </form>
    </div>
    <div v-if="gallery.length" role="dialog" aria-label="箱唛照片组预览" aria-modal="true" class="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 p-4 sm:p-8" @click.self="gallery = []">
      <section class="mx-auto max-w-5xl rounded-xl bg-white p-4 sm:p-6">
        <div class="flex items-center justify-between gap-3"><h3 class="font-bold">箱唛照片组 · {{ gallery.length }} 张</h3><button type="button" class="rounded-lg border px-3 py-2 text-sm" @click="gallery = []">关闭预览</button></div>
        <div class="mt-4 grid gap-4 sm:grid-cols-2"><figure v-for="photo in gallery" :key="photo.id" class="min-w-0 rounded-lg border p-3"><img :src="previewUrl(photo)" :alt="photo.file_name" loading="lazy" class="h-80 w-full object-contain"><figcaption class="mt-2 flex items-center justify-between gap-2 text-xs"><span class="break-all">{{ photo.file_name }}</span><button type="button" class="shrink-0 rounded border px-2 py-1.5" @click="download(photo)">下载</button></figcaption></figure></div>
      </section>
    </div>
  </section>
  <p v-else class="rounded-xl border bg-white p-6 text-sm text-slate-500">当前账号没有箱唛资料查看权限。</p>
</template>

<style scoped>
.asset-actions > a, .asset-actions > button { height: 2rem; display: inline-flex; align-items: center; justify-content: center; white-space: nowrap; }
.mark-library-columns {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}

@media (min-width: 1024px) {
  .mark-library-columns {
    grid-template-columns: minmax(0, 1.1fr) minmax(0, 1.8fr) minmax(0, 0.9fr) var(--asset-actions-width);
  }
}
</style>
