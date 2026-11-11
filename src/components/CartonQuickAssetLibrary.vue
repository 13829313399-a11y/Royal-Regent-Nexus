<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import CartonFilterBar from './CartonFilterBar.vue'
import CartonQuickUploadDialog from './CartonQuickUploadDialog.vue'
import CartonMarkAssetLibrary from './CartonMarkAssetLibrary.vue'
import { cartonQuickAssetsApi, type AssetDepartment, type QuickAsset, type QuickAssetAudience, type QuickAssetStatus, type QuickTarget, type QuickTargetRef } from '@/api/cartonQuickAssets'
import { useAuthStore } from '@/stores/auth'
import { canQuickAsset, departmentLabel, internalDepartments, quickStatusLabel, responseStatus, targetLabel, targetOrderTime, targetRef, uploadDepartments, viewerKey, type QuickAudience } from '@/features/carton-procurement/quickAssets'
import { getApiErrorMessage, http } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { factoryContexts } from '@/data/enterpriseMock'

const props = defineProps<{ factoryId: string; audience: QuickAudience; refreshKey?: number; supplierFactories?: string[]; search?: string; assetIds?: string[]; readOnly?: boolean }>()
const emit = defineEmits<{ changed: []; 'update:search': [value: string] }>()
const auth = useAuthStore()
const entries = ref<QuickAsset[]>([]), loading = ref(false), error = ref(''), actionError = ref(''), notice = ref('')
const filter = ref('CURRENT'), keyword = ref(''), mine = ref(false), busy = ref(false), downloading = ref('')
const format = ref('ALL'), customer = ref(''), binding = ref('ALL'), orderKind = ref('ALL'), sort = ref('LATEST'), page = ref(1)
const details = shallowRef<QuickAsset | null>(null)
const detailBusy = ref(false), photoSelection = ref<string[]>([])
const detailMode = ref<'details' | 'association' | 'photos'>('details')
const libraryTitle = ref<HTMLElement | null>(null)
let dialogOpener: HTMLElement | null = null
function rememberOpener(event: MouseEvent) {
  dialogOpener = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
}
function restoreDialogFocus(event: Event) {
  event.preventDefault()
  const opener = dialogOpener
  dialogOpener = null
  void nextTick(() => (opener?.isConnected ? opener : libraryTitle.value)?.focus())
}
function openDetails(asset: QuickAsset, mode: typeof detailMode.value, event: MouseEvent) {
  rememberOpener(event)
  detailMode.value = mode; details.value = asset; notice.value = ''; actionError.value = ''
}
function closeDetails() { if (detailBusy.value || busy.value || pending.value) return; details.value = null }
function completeManagement() { detailBusy.value = false; photoSelection.value = []; closeDetails(); saved() }
function canManageAssociation(asset: QuickAsset) {
  return !props.readOnly && props.audience !== 'supplier' && asset.factory_id === assetFactory(asset)
    && asset.can_manage_original && (asset.legacy_source || !!asset.photo_group_id)
    && asset.workflow.status !== 'HISTORY' && !asset.workflow.superseded_by_asset_id
}
function associate(asset: QuickAsset, event: MouseEvent) {
  if (canManageAssociation(asset)) { photoSelection.value = []; openDetails(asset, asset.photo_group_id ? 'photos' : 'association', event) }
  else if (!props.readOnly && asset.can_associate) void edit(asset, 'associate', event)
}
function associationHint(asset: QuickAsset) {
  if (canManageAssociation(asset)) return asset.photo_group_id ? '关联订单将维护整组照片；解除分组也在该入口办理。' : '旧资料沿用原匹配方式；从“关联订单”维护，未移除的原关联保留。'
  if (asset.photo_group_id && asset.association_blocker?.includes('资料详情')) return '照片组须由有原件维护权限的经办人整体维护关联。'
  if (asset.legacy_source && asset.association_blocker?.includes('资料详情')) return '旧资料沿用原匹配方式，由原上传人或有权限的管理员维护关联。'
  return asset.association_blocker
}
const detailAssociationLabels = computed(() => Object.fromEntries(entries.value.filter(asset => detailsIds.value.includes(asset.id)).map(asset => [asset.id, asset.targets.map(targetLabel)])))
function groupPhotos(event: MouseEvent) {
  const chosen = entries.value.filter(x => photoSelection.value.includes(x.id))
  const ids = new Set(chosen.map(x => x.id))
  for (const row of chosen) if (row.photo_group_id) entries.value.filter(x => x.photo_group_id === row.photo_group_id && x.factory_id === row.factory_id).forEach(x => ids.add(x.id))
  if (ids.size > 50) { actionError.value = '包含整组后超过50张，请减少选择。'; return }
  photoSelection.value = [...ids]
  if (chosen[0]) openDetails(chosen[0], 'photos', event)
}
const detailsIds = computed(() => {
  const asset = details.value
  if (!asset) return []
  const ids = new Set(detailMode.value === 'photos' && photoSelection.value.length ? photoSelection.value : [asset.id])
  if (asset.photo_group_id) entries.value.filter(x => x.photo_group_id === asset.photo_group_id && x.factory_id === asset.factory_id).forEach(x => ids.add(x.id))
  if (detailMode.value !== 'details') return [...ids]
  let expanded = true
  while (expanded && ids.size <= 100) {
    expanded = false
    for (const row of entries.value) {
      if (row.factory_id !== asset.factory_id || ids.has(row.id)) continue
      if (ids.has(row.workflow.previous_asset_id) || ids.has(row.workflow.superseded_by_asset_id)
        || [...ids].some(id => { const item = entries.value.find(x => x.id === id); return item?.workflow.previous_asset_id === row.id || item?.workflow.superseded_by_asset_id === row.id })) { ids.add(row.id); expanded = true }
    }
  }
  return [...ids]
})
const customers = computed(() => [...new Set(entries.value.flatMap(x => x.targets.map(t => t.customer_name || t.customer_code || '').filter(Boolean)))].sort())
function resetFilters() { filter.value = 'CURRENT'; keyword.value = ''; emit('update:search', ''); mine.value = false; format.value = 'ALL'; customer.value = ''; binding.value = 'ALL'; orderKind.value = 'ALL'; sort.value = 'LATEST'; page.value = 1 }
const statusDrafts = ref<Record<string, QuickAssetStatus | ''>>({})
const audienceDrafts = ref<Record<string, QuickAssetAudience>>({})
const audienceLabel = (asset: QuickAsset) => asset.purpose === 'EVIDENCE' || asset.sharing_mode === 'INTERNAL' ? '仅内部可见'
  : asset.sharing_mode === 'SUPPLIER' ? `内部与${asset.shared_supplier_name || '对应供应商'}共享` : '沿用原订单共享规则'
const allSupplierFactories = computed(() => props.audience === 'supplier' && (!props.factoryId || props.factoryId === 'ALL'))
const requestedFactories = computed(() => allSupplierFactories.value ? [...new Set(props.supplierFactories || [])] : props.factoryId && props.factoryId !== 'ALL' ? [props.factoryId] : [])
function readableDepartments(factory: string): AssetDepartment[] {
  // The server checks the named supplier audience and explicit denies.
  // Reading a shared source does not grant own-source replacement rights.
  if (props.audience === 'supplier') return auth.can('carton_supplier:read', factory, '*') ? ['supplier'] : []
  return internalDepartments.filter(d => canQuickAsset(auth, factory, d, 'read'))
}
const scopes = computed(() => requestedFactories.value.flatMap(factory => {
  const department = readableDepartments(factory)[0]
  return department ? [{ factory, department }] : []
}))
const uploadFactories = computed(() => requestedFactories.value.filter(factory => canQuickAsset(auth, factory, 'supplier', 'manage')))
const selectedUploadFactory = ref('')
const uploadFactory = computed(() => allSupplierFactories.value ? selectedUploadFactory.value : props.factoryId)
const canUpload = computed(() => !props.readOnly && uploadDepartments(auth, uploadFactory.value, props.audience)
  .some(department => canQuickAsset(auth, uploadFactory.value, department, 'read')))
watch(uploadFactories, factories => {
  if (!factories.includes(selectedUploadFactory.value)) selectedUploadFactory.value = factories[0] || ''
}, { immediate: true, flush: 'sync' })
function assetFactory(asset: QuickAsset) { return allSupplierFactories.value ? asset.factory_id : props.factoryId }
function factoryName(id: string) { return factoryContexts.find(x => x.id === id)?.shortName || id }
function previewUrl(asset: QuickAsset) { return http.getUri({ url: `/carton-mark/assets/quick/${encodeURIComponent(asset.id)}/document`, params: { factory_id: assetFactory(asset), supplier_view: props.audience === 'supplier', preview: true } }) }
const context = computed(() => JSON.stringify([props.factoryId, props.audience, props.assetIds, props.supplierFactories, viewerKey(auth)]))
const uploadFilterLabel = computed(() => props.audience === 'supplier' ? '只看本供应商上传' : props.audience === 'sales' ? '只看业务部上传' : '只看仓库上传')
const matchingEntries = computed(() => entries.value.filter(x => {
  const query = (props.search ?? keyword.value).trim().toLowerCase()
  return (!mine.value || x.owner_department === (props.audience === 'supplier' ? 'supplier' : props.audience === 'sales' ? 'sales-business' : 'pmc-warehouse') || props.audience === 'warehouse' && x.owner_department === 'carton')
    && (!props.assetIds || props.assetIds.includes(x.id))
    && (format.value === 'ALL' || x.kind === format.value)
    && (!customer.value || x.targets.some(t => (t.customer_name || t.customer_code) === customer.value))
    && (binding.value === 'ALL' || (binding.value === 'BOUND' ? x.targets.length > 0 : x.targets.length === 0))
    && (orderKind.value === 'ALL' || x.targets.some(t => t.kind === orderKind.value))
    && (!query || [x.file_name, x.contract_number, ...x.targets.flatMap(t => [targetLabel(t), t.customer_po])].join(' ').toLowerCase().includes(query))
}))
const documentState = (asset: QuickAsset) => asset.workflow.status
const statusFilters = computed(() => [
  { id: 'CURRENT', label: '当前资料', count: matchingEntries.value.filter(x => documentState(x) !== 'HISTORY').length },
  { id: 'ALL', label: '全部版本', count: matchingEntries.value.length },
  ...(['DRAFT', 'PENDING', 'READY', 'UNCLASSIFIED', 'HISTORY'] as const).map(id => ({ id, label: quickStatusLabel[id], count: matchingEntries.value.filter(x => documentState(x) === id).length })),
])
const warehouseToolbar = computed(() => props.audience === 'warehouse' && !props.assetIds)
const versionIds = ['CURRENT', 'ALL', 'HISTORY']
const versionFilters = computed(() => statusFilters.value.filter(option => versionIds.includes(option.id)))
const currentStatusFilters = computed(() => statusFilters.value.filter(option => !versionIds.includes(option.id)))
const versionScope = computed(() => versionIds.includes(filter.value) ? filter.value : 'CURRENT')
const currentStatus = computed({
  get: () => versionScope.value === 'CURRENT' ? filter.value : 'CURRENT',
  set: value => { filter.value = value },
})
const visible = computed(() => matchingEntries.value.filter(x => filter.value === 'ALL' || (filter.value === 'CURRENT' ? documentState(x) !== 'HISTORY' : documentState(x) === filter.value)))
const ordered = computed(() => [...visible.value].sort((a,b) => sort.value === 'CONTRACT' ? a.contract_number.localeCompare(b.contract_number) : (b.created_at || '').localeCompare(a.created_at || '') || a.id.localeCompare(b.id)))
const pageCount = computed(() => Math.max(1, Math.ceil(ordered.value.length / 20)))
const paged = computed(() => ordered.value.slice((page.value - 1) * 20, page.value * 20))
watch([filter, keyword, mine, format, customer, binding, orderKind, sort, () => props.search], () => { page.value = 1 })
watch(pageCount, count => { page.value = Math.min(page.value, count) })
const editor = shallowRef<{ asset: QuickAsset; mode: 'associate' | 'share' } | null>(null)
const candidates = ref<QuickTarget[]>([]), selected = ref<string[]>([]), sharedFactories = ref<string[]>([]), candidateLoading = ref(false), candidateError = ref('')
const orderSearch = ref('')
const targetScope = computed(() => props.audience === 'sales' ? 'PENDING_SCHEDULE' as const : 'ORDERS' as const)
const associationLabel = computed(() => props.audience === 'sales' ? '关联排期订单' : '关联订单')
const visibleCandidates = computed(() => candidates.value.filter(x => (props.audience === 'sales' || x.kind !== 'SCHEDULE') && (!orderSearch.value.trim() || [x.customer_name, x.contract_no, x.customer_po, x.item_no, x.order_no, targetOrderTime(x)].join(' ').toLowerCase().includes(orderSearch.value.trim().toLowerCase()))))
const shareOptions = computed(() => factoryContexts.filter(x => (props.supplierFactories || [props.factoryId]).includes(x.id)))
const requiredSharedFactories = computed(() => editor.value?.asset.required_shared_factory_ids || [])
const shareDescription = computed(() => requiredSharedFactories.value.length
  ? '来源厂区保留可见；可选择其他有权限的厂区共享给业务和仓库。'
  : '默认无；选择后该厂业务和仓库可见。')
type Command = { factory: string; asset: Pick<QuickAsset, 'id' | 'revision'>; requestId: string } & ({ kind: 'classify'; status: QuickAssetStatus } | { kind: 'associate'; targets: QuickTargetRef[] } | { kind: 'share'; factories: string[] } | { kind: 'audience'; mode: QuickAssetAudience })
const pending = shallowRef<Command | null>(null)
let generation = 0, actionGeneration = 0, editorGeneration = 0, downloadGeneration = 0
let controller = new AbortController(), actionController = new AbortController(), editorController = new AbortController(), downloadController = new AbortController()
async function load() {
  const token = ++generation, original = context.value
  controller.abort(); controller = new AbortController(); entries.value = []; error.value = ''; loading.value = false
  if (!scopes.value.length) return
  loading.value = true
  try {
    const responses = await Promise.all(scopes.value.map(scope => cartonQuickAssetsApi.list(scope.factory, scope.department, controller.signal)))
    const data = { items: responses.flatMap(response => response.items) }
    if (token !== generation || original !== context.value) return
    entries.value = data.items
    if (details.value && detailMode.value === 'details') {
      const fresh = data.items.find(asset => asset.id === details.value?.id)
      if (fresh) details.value = fresh
      else if (!detailBusy.value && !pending.value) details.value = null
    }
    statusDrafts.value = Object.fromEntries(data.items.map(x => [x.id, x.workflow.status === 'UNCLASSIFIED' ? '' : x.workflow.status]))
    audienceDrafts.value = Object.fromEntries(data.items.map(x => [x.id, x.sharing_mode === 'INTERNAL' ? 'INTERNAL' : 'SUPPLIER']))
  } catch (cause) { if (token === generation && original === context.value) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
function cancelRequests() {
  actionGeneration++; editorGeneration++; downloadGeneration++
  actionController.abort(); editorController.abort(); downloadController.abort()
}
watch(context, () => {
  cancelRequests()
  pending.value = null; editor.value = null; details.value = null; detailBusy.value = false; photoSelection.value = []; busy.value = false; downloading.value = ''; actionError.value = ''; notice.value = ''; resetFilters()
}, { flush: 'sync' })
watch([context, () => JSON.stringify(scopes.value), () => props.refreshKey], load, { immediate: true, flush: 'sync' })
function saved() { void load(); emit('changed') }
function canClassify(asset: QuickAsset) {
  return !props.readOnly && asset.purpose === 'MATERIAL' && !asset.workflow.superseded_by_asset_id && (asset.can_classify ?? readableDepartments(assetFactory(asset)).some(d => canQuickAsset(auth, assetFactory(asset), d, 'manage')))
}
function statusChoices(asset: QuickAsset) {
  return (['DRAFT','PENDING','READY','HISTORY'] as const).filter(state => !asset.allowed_statuses || asset.allowed_statuses.includes(state) || state === asset.workflow.status)
}
function commandBase(asset: QuickAsset) { return { factory: assetFactory(asset), asset: { id: asset.id, revision: asset.revision }, requestId: createRandomUuid() } }
async function execute(command?: Command) {
  if (busy.value || (!command && !pending.value)) return
  const request = pending.value || command!, original = context.value, token = ++actionGeneration
  const retryingUnknown = Boolean(pending.value)
  busy.value = true; actionError.value = ''; actionController = new AbortController()
  try {
    if (request.kind === 'classify') await cartonQuickAssetsApi.classify(request.factory, request.asset, request.status, request.requestId, actionController.signal)
    else if (request.kind === 'associate') await cartonQuickAssetsApi.associate(request.factory, request.asset, request.targets, request.requestId, actionController.signal, targetScope.value)
    else if (request.kind === 'audience') await cartonQuickAssetsApi.audience(request.factory, request.asset, request.mode, request.requestId, actionController.signal)
    else await cartonQuickAssetsApi.share(request.factory, request.asset, request.factories, request.requestId, actionController.signal)
    if (context.value !== original || token !== actionGeneration) return
    pending.value = null; editor.value = null; notice.value = '资料已更新'; saved()
  } catch (cause) {
    if (context.value !== original || token !== actionGeneration) return
    const code = responseStatus(cause)
    if (retryingUnknown || code === undefined || code >= 500) { pending.value = request; actionError.value = '保存结果尚未核实，请沿用原请求重试。' }
    else { pending.value = null; actionError.value = code === 409 ? '资料已更新，请刷新后重新核对。' : getApiErrorMessage(cause); if (code === 409) { editor.value = null; void load() } }
  } finally { if (context.value === original && token === actionGeneration) busy.value = false }
}
async function edit(asset: QuickAsset, mode: 'associate' | 'share', event: MouseEvent) {
  rememberOpener(event)
  editor.value = { asset, mode }; selected.value = []; orderSearch.value = ''; sharedFactories.value = [...(asset.shared_factory_ids || [])]; candidateError.value = ''; candidates.value = []
  if (mode === 'share') return
  const token = ++editorGeneration, original = context.value
  editorController.abort(); editorController = new AbortController(); candidateLoading.value = true
  try {
    const factory = assetFactory(asset)
    const owner: AssetDepartment = props.audience === 'supplier' ? 'supplier' : readableDepartments(factory).find(d => canQuickAsset(auth, factory, d, 'manage')) || readableDepartments(factory)[0]!
    const rows = await cartonQuickAssetsApi.candidates(factory, owner, '', editorController.signal, targetScope.value, asset.id)
    if (token !== editorGeneration || original !== context.value) return
    candidates.value = rows.filter(x => props.audience === 'sales' || x.kind !== 'SCHEDULE')
    selected.value = candidates.value.filter(x => asset.targets.some(y => y.kind === x.kind && y.id === x.id && y.sheet === x.sheet && y.row === x.row)).map(x => x.fingerprint)
  } catch (cause) { if (token === editorGeneration && original === context.value) candidateError.value = getApiErrorMessage(cause) }
  finally { if (token === editorGeneration) candidateLoading.value = false }
}
function closeEditor(open: boolean) { if (!open && !busy.value && !pending.value) { editor.value = null; editorGeneration++; editorController.abort() } }
function saveEditor() {
  if (!editor.value || candidateLoading.value || candidateError.value) return
  if (editor.value.mode === 'associate' && editor.value.asset.targets.some(t => !(targetScope.value === 'ORDERS' && t.kind === 'SCHEDULE') && !candidates.value.some(c => c.kind === t.kind && c.id === t.id && c.sheet === t.sheet && c.row === t.row))) {
    actionError.value = '原关联中有当前不可维护的订单，请刷新并核实；本次未保存，原关联保留。'; return
  }
  const base = commandBase(editor.value.asset)
  void execute(editor.value.mode === 'share' ? { ...base, kind: 'share', factories: [...sharedFactories.value] } : { ...base, kind: 'associate', targets: candidates.value.filter(x => selected.value.includes(x.fingerprint)).map(targetRef) })
}
async function download(asset: QuickAsset) {
  if (downloading.value) return
  const original = context.value, token = ++downloadGeneration
  downloadController = new AbortController(); downloading.value = asset.id
  try {
    const blob = await cartonQuickAssetsApi.document(assetFactory(asset), asset.id, props.audience === 'supplier', downloadController.signal)
    if (context.value !== original || token !== downloadGeneration) return
    const url = URL.createObjectURL(blob), anchor = document.createElement('a')
    anchor.href = url; anchor.download = asset.file_name; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (cause) { if (context.value === original && token === downloadGeneration) actionError.value = getApiErrorMessage(cause) }
  finally { if (context.value === original && token === downloadGeneration) downloading.value = '' }
}
onBeforeUnmount(() => { generation++; controller.abort(); cancelRequests() })
</script>

<template>
  <section class="min-w-0 rounded-xl border border-border bg-card p-4 sm:p-5" data-testid="quick-department-library">
    <header>
      <h2 ref="libraryTitle" tabindex="-1" class="text-base font-bold">箱唛资料库</h2>
      <p class="mt-1 text-xs text-muted-foreground">上传、选择状态、关联订单。同厂业务与仓库共享；供应商资料按所选厂区共享。</p>
    </header>
    <p v-if="!requestedFactories.length" class="mt-4 text-sm text-muted-foreground">请先选择一个厂区，再查看资料或上传。</p>
    <p v-else-if="!scopes.length" role="status" class="mt-4 text-sm text-muted-foreground">当前账号没有本厂资料读取权限。</p>
    <template v-else>
      <div class="carton-mark-tools mt-4 min-w-0 overflow-hidden rounded-xl border border-border">
        <div class="flex flex-wrap items-end gap-x-4 gap-y-2 border-b border-border p-3 sm:px-4">
          <div v-if="warehouseToolbar" class="flex min-w-0 flex-wrap gap-1 rounded-lg bg-muted/40 p-1" role="group" aria-label="资料版本范围">
            <Button v-for="option in versionFilters" :key="option.id" type="button"
              :variant="versionScope === option.id ? 'soft' : 'ghost'"
              :aria-pressed="versionScope === option.id" :aria-label="`${option.label} ${loading || error ? '数量未读取' : option.count}`"
              :data-status-filter="option.id" class="h-9 px-2.5" @click="filter = option.id">
              {{ option.label }}<span class="rounded bg-current/5 px-1.5 tabular-nums">{{ loading || error ? '—' : option.count }}</span>
            </Button>
          </div>
          <label v-if="search === undefined" class="min-w-40 flex-1 text-xs">搜索资料<input v-model="keyword" aria-label="搜索资料" placeholder="文件名、合同、货号" class="mt-1 block h-9 w-full rounded-lg border border-input bg-card px-3 text-sm"></label>
          <div class="flex min-w-0 flex-[1_1_21rem] flex-wrap items-center justify-between gap-3">
            <label class="flex min-h-9 items-center gap-2 text-xs font-semibold text-muted-foreground" title="按上传部门筛选，包含该部门其他同事上传的资料；不勾选时显示全部有权查看的资料。"><input v-model="mine" type="checkbox" :aria-label="uploadFilterLabel">{{ uploadFilterLabel }}</label>
            <div class="ml-auto flex min-w-0 max-w-full flex-wrap items-center justify-end gap-2">
              <Button type="button" variant="outline" :disabled="loading || busy || !!pending" @click="load">刷新资料</Button>
              <CartonQuickUploadDialog v-if="canUpload" :factory-id="uploadFactory" :audience="audience" :supplier-factories="supplierFactories" @saved="saved" />
            </div>
          </div>
        </div>
        <CartonFilterBar inline-actions label="资料筛选" class="carton-mark-filters">
          <label v-if="warehouseToolbar" class="min-w-0 text-xs">当前资料状态
            <select v-model="currentStatus" aria-label="当前资料状态" :disabled="versionScope !== 'CURRENT'" class="mt-1 h-9 w-full rounded-lg border border-input bg-card px-2 text-sm disabled:opacity-50">
              <option value="CURRENT">全部状态</option>
              <option v-for="option in currentStatusFilters" :key="option.id" :value="option.id">{{ option.label }} · {{ loading || error ? '—' : option.count }}</option>
            </select>
          </label>
          <label v-else class="carton-mark-filter-wide">资料状态
            <select v-model="filter" aria-label="资料状态">
              <option v-for="option in statusFilters" :key="option.id" :value="option.id">{{ option.label }} · {{ loading || error ? '—' : option.count }}</option>
            </select>
          </label>
          <label>格式<select v-model="format" aria-label="资料格式"><option value="ALL">全部格式</option><option value="pdf">PDF</option><option value="excel">Excel</option><option value="image">图片</option><option value="text">文字</option></select></label>
          <label>客户<select v-model="customer" aria-label="资料客户"><option value="">全部客户</option><option v-for="value in customers" :key="value">{{ value }}</option></select></label>
          <label>关联状态<select v-model="binding" aria-label="资料关联状态"><option value="ALL">全部</option><option value="BOUND">已关联</option><option value="UNBOUND">未关联 / 待核实</option></select></label>
          <label>订单类型<select v-model="orderKind" aria-label="资料订单类型"><option value="ALL">全部</option><option value="SCHEDULE">业务排期</option><option value="REGULAR">采购正单</option><option value="SAMPLE">样板</option><option value="MISC">杂单</option></select></label>
          <label class="carton-mark-filter-wide">排序<select v-model="sort" aria-label="资料排序"><option value="LATEST">最近上传优先</option><option value="CONTRACT">合同号</option></select></label>
          <template #actions>
            <Button type="button" variant="outline" @click="resetFilters">清除筛选</Button>
          </template>
        </CartonFilterBar>
      </div>
      <p class="mt-2 text-xs text-muted-foreground">已确认是资料状态；核对、审核和 QC 核验记录分别保留。</p>
      <div v-if="allSupplierFactories" class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <label v-if="canUpload && uploadFactories.length > 1" class="flex items-center gap-2 text-xs">关联订单厂区<select v-model="selectedUploadFactory" aria-label="上传关联订单厂区" class="h-9 rounded-lg border border-input bg-card px-3 text-sm"><option v-for="id in uploadFactories" :key="id" :value="id">{{ factoryName(id) }}</option></select></label>
        <p class="text-xs text-muted-foreground">{{ canUpload ? '可直接上传。关联订单厂区只用于查找订单；共享厂区在上传窗口另选，默认无。' : '可读取已发送订单的共享资料；上传与维护需要独立授权。' }}</p>
      </div>
      <p v-if="loading" role="status" class="py-6 text-sm text-muted-foreground">正在读取资料…</p>
      <p v-else-if="error" role="alert" class="mt-3 text-sm text-destructive">{{ error }} <button type="button" class="underline" @click="load">重试读取</button></p>
      <p v-else-if="!visible.length" class="py-6 text-sm text-muted-foreground">暂无符合条件的资料。<span v-if="canUpload">可上传文件、照片或文字。</span></p>
      <ul v-else class="mt-3 divide-y divide-border">
        <li v-for="asset in paged" :key="asset.id" class="min-w-0 py-4" :data-quick-asset="asset.id">
          <label v-if="!readOnly && audience !== 'supplier' && asset.kind === 'image' && asset.can_manage_original && asset.workflow.status !== 'HISTORY' && !asset.workflow.superseded_by_asset_id" class="mb-2 flex items-center gap-2 text-xs text-muted-foreground"><input v-model="photoSelection" type="checkbox" :value="asset.id" :aria-label="`选择分组照片 ${asset.file_name}`">选择照片{{ asset.photo_group_id ? '（包含整组）' : '' }}</label>
          <div class="grid min-w-0 grid-cols-1 items-start gap-3 xl:grid-cols-[minmax(0,1fr)_auto]">
            <div class="min-w-0 flex-1 basis-56"><p class="break-all text-sm font-semibold">{{ asset.file_name }}</p><p v-if="allSupplierFactories" class="mt-1 text-xs text-muted-foreground">订单厂区：{{ factoryName(asset.factory_id) }}</p><p class="mt-1 text-xs text-muted-foreground">{{ (asset.owner_department ? departmentLabel[asset.owner_department] : '') || '历史资料' }} · {{ asset.created_by_name || '原上传人' }} · {{ asset.workflow.updated_by_name ? `${asset.workflow.updated_by_name} 更新状态` : '' }}</p><p class="mt-1 break-all text-xs text-muted-foreground">{{ asset.contract_number ? `合同 ${asset.contract_number} · ` : '' }}{{ asset.targets.length ? asset.targets.map(targetLabel).join('；') : '未关联订单' }}</p><p v-if="asset.owner_department !== 'supplier'" class="mt-1 text-xs text-muted-foreground">可见范围：{{ audienceLabel(asset) }}</p><p v-if="audience === 'supplier'" class="mt-1 text-xs text-muted-foreground">共享：{{ asset.shared_factory_ids?.length ? asset.shared_factory_ids.map(id => factoryContexts.find(x => x.id === id)?.shortName || id).join('、') : '无，仅供应商可见' }}</p></div>
            <div class="flex min-w-0 flex-wrap items-center gap-2" data-asset-actions>
              <a v-if="asset.kind !== 'excel'" :href="previewUrl(asset)" target="_blank" rel="noopener" class="inline-flex h-9 items-center rounded-lg border border-input px-3 text-sm">预览</a>
              <Button v-if="audience !== 'supplier' && asset.factory_id === assetFactory(asset)" type="button" variant="outline" size="sm" :disabled="busy || !!pending" @click="openDetails(asset, 'details', $event)">资料详情</Button>
              <template v-if="canClassify(asset)"><select v-model="statusDrafts[asset.id]" :aria-label="`${asset.file_name} 状态`" :disabled="busy || !!pending" class="h-9 w-24 rounded-lg border border-input bg-card px-2 text-sm"><option v-if="asset.workflow.status === 'UNCLASSIFIED'" disabled value="">待分类 · 请选择</option><option v-for="state in statusChoices(asset)" :key="state" :value="state">{{ quickStatusLabel[state] }}</option></select><Button type="button" size="sm" :disabled="busy || !!pending || !statusDrafts[asset.id] || statusDrafts[asset.id] === asset.workflow.status" @click="execute({ ...commandBase(asset), kind: 'classify', status: statusDrafts[asset.id] as QuickAssetStatus })">保存状态</Button></template>
              <span v-else class="rounded-md bg-muted px-2 py-1 text-xs">{{ quickStatusLabel[asset.workflow.status] }}</span>

              <Button v-if="!readOnly && (asset.can_associate || canManageAssociation(asset))" type="button" variant="outline" size="sm" :disabled="busy || !!pending" @click="associate(asset, $event)">{{ associationLabel }}</Button>
              <Button v-if="!readOnly && audience === 'supplier' && asset.can_share" type="button" variant="outline" size="sm" :disabled="busy || !!pending" @click="edit(asset, 'share', $event)">共享厂区</Button>
              <Button type="button" variant="outline" size="sm" :disabled="!!downloading" @click="download(asset)">{{ downloading === asset.id ? '下载中…' : '下载' }}</Button>
            </div>
          </div>
          <p v-if="associationHint(asset)" class="mt-2 text-xs text-muted-foreground">{{ associationHint(asset) }}</p>
          <p v-if="asset.warning" class="mt-2 text-xs text-amber-700">{{ asset.warning }}</p>
          <details v-if="asset.kind === 'text'" class="mt-2 text-xs"><summary class="cursor-pointer text-primary">查看文字</summary><pre class="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted p-3 font-sans text-sm">{{ asset.text }}</pre></details>
        </li>
      </ul>
      <nav v-if="visible.length" aria-label="资料分页" class="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4 text-xs text-muted-foreground"><span>共 {{ visible.length }} 份 · 每页 20 份 · 第 {{ page }} / {{ pageCount }} 页</span><div class="flex gap-2"><Button type="button" variant="outline" size="sm" :disabled="page <= 1" @click="page--">上一页</Button><Button type="button" variant="outline" size="sm" :disabled="page >= pageCount" @click="page++">下一页</Button></div></nav>
      <div v-if="photoSelection.length" class="mt-3 flex flex-wrap items-center gap-3 text-xs"><span>已选 {{ photoSelection.length }} 张照片（整组成员会一起带入）</span><Button type="button" variant="outline" :disabled="photoSelection.length < 2 || busy || !!pending" @click="groupPhotos">维护照片组</Button><button type="button" class="text-primary underline" @click="photoSelection = []">清空照片选择</button></div>
      <p v-if="actionError && !editor && !details" role="alert" class="mt-3 text-sm text-destructive">{{ actionError }} <button v-if="pending" type="button" :disabled="busy" class="underline" @click="execute()">原样重试</button></p>
      <p v-if="notice && !details" role="status" class="mt-3 text-sm text-primary">{{ notice }}</p>
    </template>
    <DialogRoot :open="!!details" @update:open="value => { if (!value) closeDetails() }">
      <DialogPortal><DialogOverlay class="fixed inset-0 z-50 bg-slate-950/45" />
        <DialogContent class="fixed left-1/2 top-1/2 z-50 flex max-h-[90dvh] w-[calc(100%_-_1.5rem)] max-w-6xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl border border-border bg-card p-4 shadow-xl sm:p-5" @close-auto-focus="restoreDialogFocus" @interact-outside="$event.preventDefault()" @escape-key-down="(detailBusy || busy || pending) && $event.preventDefault()">
          <div class="flex items-center justify-between gap-3"><DialogTitle class="text-lg font-bold">{{ detailMode === 'details' ? '资料详情' : detailMode === 'photos' ? '维护照片组' : '关联订单' }}</DialogTitle><Button type="button" variant="outline" :disabled="detailBusy || busy || !!pending" @click="closeDetails">返回资料库</Button></div>
          <DialogDescription class="mt-1 text-xs leading-5 text-muted-foreground">{{ detailMode === 'details' ? '查看原件、订单关联和版本记录，在这里调整共享范围或上传修改稿。状态和订单关联在资料库列表管理。' : detailMode === 'photos' ? '整组照片一起维护，保存前请核对原有订单关联。' : '保留旧资料的原匹配方式及未移除的订单关联。这里只显示已建采购单、样板和杂单。' }}</DialogDescription>
          <div class="mt-4 min-h-0 overflow-y-auto overscroll-contain">
            <div class="grid min-w-0 gap-4" :class="detailMode === 'details' ? 'lg:grid-cols-[minmax(0,1fr)_17rem]' : ''">
            <fieldset :disabled="busy || !!pending || loading" class="min-w-0">
            <CartonMarkAssetLibrary v-if="details" :key="`${details.id}:${detailMode}`" :factory-id="details.factory_id" :asset-ids="detailsIds" details-only quick-read
              :management-mode="detailMode === 'details' ? undefined : detailMode" :initial-asset-id="details.id"
              :association-labels="detailAssociationLabels" :initial-photo-ids="detailMode === 'photos' && photoSelection.length ? photoSelection : undefined"
              :legacy-associations="details.legacy_source" :manage-original="!readOnly && details.can_manage_original" :read-only="readOnly || !details.can_manage_original"
              @busy="detailBusy = $event" @completed="completeManagement" @changed="detailMode === 'details' && saved()" />
            </fieldset>
            <aside v-if="details && detailMode === 'details'" class="min-w-0 rounded-xl border border-border bg-muted/30 p-4 lg:sticky lg:top-0 lg:self-start" aria-label="资料共享设置">
              <h2 class="text-sm font-semibold">共享范围</h2>
              <p class="mt-2 break-words text-xs leading-5 text-muted-foreground [overflow-wrap:anywhere]">{{ details.file_name }} · V{{ details.workflow.version || 1 }}</p>
              <p class="mt-3 rounded-lg border border-border bg-card p-3 text-xs leading-5">当前：{{ audienceLabel(details) }}</p>
              <div v-if="!readOnly && audience !== 'supplier' && details.can_change_audience" class="mt-4 space-y-3">
                <label class="block text-xs font-medium">谁可以查看
                  <select v-model="audienceDrafts[details.id]" :aria-label="`${details.file_name} 共享范围`" :disabled="detailBusy || busy || !!pending || loading || !!error" class="mt-2 h-10 w-full rounded-lg border border-input bg-card px-2 text-xs"><option value="SUPPLIER">内部与对应供应商共享</option><option value="INTERNAL">仅内部可见</option></select>
                </label>
                <p class="text-xs leading-5 text-muted-foreground">仅调整当前这份资料的可见范围，订单关联和资料状态保持不变。</p>
                <Button type="button" class="w-full" :disabled="detailBusy || busy || !!pending || loading || !!error || !audienceDrafts[details.id] || audienceDrafts[details.id] === details.sharing_mode" @click="execute({ ...commandBase(details), kind: 'audience', mode: audienceDrafts[details.id]! })">{{ busy ? '保存中…' : '保存范围' }}</Button>
              </div>
              <p v-else class="mt-3 text-xs leading-5 text-muted-foreground">当前账号可查看共享范围。</p>
              <p v-if="loading" role="status" class="mt-3 text-xs text-muted-foreground">正在更新资料信息…</p>
              <p v-if="error" role="alert" class="mt-3 text-xs leading-5 text-destructive">{{ error }} <button type="button" :disabled="busy || !!pending || detailBusy" class="underline" @click="load">刷新资料</button></p>
              <div v-if="actionError" role="alert" class="mt-3 space-y-2 text-xs leading-5 text-destructive"><p>{{ actionError }}</p><Button v-if="pending" type="button" variant="outline" :disabled="busy" class="w-full" @click="execute()">原样重试</Button></div>
              <p v-if="notice" role="status" class="mt-3 text-xs text-primary">{{ notice }}</p>
            </aside>
            </div>
          </div>
        </DialogContent>
      </DialogPortal>
    </DialogRoot>
    <DialogRoot :open="!!editor" @update:open="closeEditor"><DialogPortal><DialogOverlay class="fixed inset-0 z-50 bg-slate-950/45" /><DialogContent class="fixed left-1/2 top-1/2 z-50 flex max-h-[85dvh] overflow-hidden w-[calc(100%-2rem)] max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-border bg-card p-5 shadow-xl" @close-auto-focus="restoreDialogFocus" @escape-key-down="(busy || pending) && $event.preventDefault()" @interact-outside="(busy || pending) && $event.preventDefault()">
      <DialogTitle class="text-lg font-bold">{{ editor?.mode === 'share' ? '共享厂区' : associationLabel }}</DialogTitle><DialogDescription class="mt-1 break-all text-sm text-muted-foreground">{{ editor?.asset.file_name }} · {{ editor?.mode === 'share' ? shareDescription : '可选择多个订单；取消全部选择可解除本次可维护的订单关联。' }}</DialogDescription>
      <p v-if="editor?.mode === 'associate' && audience === 'supplier' && requiredSharedFactories.length" class="mt-2 text-xs text-muted-foreground">业务原有的排期关联保留；这里调整本供应商已收到的同客户订单。</p>
      <p v-if="editor?.mode === 'associate'" class="mt-2 text-xs text-muted-foreground">{{ audience === 'supplier' ? '可关联当前厂区已向本供应商开放的采购单、样板或杂单。关联不会提交采购。' : audience === 'sales' ? '新增关联选择未下单排期；已关联的排期下单后继续保留。仓库能在排期中查看资料。' : '这里只选择已建采购单、样板或杂单。已有业务排期关联由业务端维护，本次保存会保留。' }}</p>
      <div class="my-4 min-h-0 flex-1 overflow-y-auto overscroll-contain" data-testid="asset-association-scroll"><fieldset :disabled="busy || !!pending" class="min-w-0 space-y-3 disabled:opacity-60"><template v-if="editor?.mode === 'share'"><label v-for="option in shareOptions" :key="option.id" class="flex items-center gap-2 text-sm"><input v-model="sharedFactories" type="checkbox" :value="option.id" :disabled="requiredSharedFactories.includes(option.id)">{{ option.shortName }}<span v-if="requiredSharedFactories.includes(option.id)" class="text-xs text-muted-foreground">来源厂区，保留可见</span></label></template><template v-else><p v-if="candidateLoading" role="status">正在读取可关联订单…</p><p v-else-if="candidateError" role="alert">{{ candidateError }}</p><input v-model="orderSearch" aria-label="搜索关联订单" placeholder="搜索客户、合同 / PO、货号" class="h-10 w-full rounded-lg border border-input bg-card px-3 text-sm"><p class="text-xs text-muted-foreground">已选择 {{ selected.length }} 条</p><label v-for="target in visibleCandidates" :key="target.fingerprint" class="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5"><input v-model="selected" type="checkbox" :value="target.fingerprint" class="mt-1 shrink-0"><span class="min-w-0"><span class="block break-words font-medium">{{ targetLabel(target) }}</span><span v-if="target.customer_po" class="mt-1 block text-xs text-muted-foreground">PO {{ target.customer_po }}</span><span v-if="targetOrderTime(target)" class="mt-1 block text-xs tabular-nums text-muted-foreground">{{ targetOrderTime(target) }}</span><span v-if="target.kind === 'SCHEDULE'" class="mt-1 block text-xs text-muted-foreground">{{ target.ordered ? '已下单，保留关联' : '未下单' }}</span></span></label><p v-if="!candidateLoading && !candidateError && !candidates.length" class="text-sm text-muted-foreground">暂无可关联订单</p></template></fieldset></div>
      <p v-if="actionError" role="alert" class="mb-3 text-sm text-destructive">{{ actionError }}</p><footer class="flex shrink-0 justify-end gap-2 border-t border-border pt-4"><Button type="button" variant="outline" :disabled="busy || !!pending" @click="closeEditor(false)">取消</Button><Button type="button" :disabled="busy || candidateLoading || !!candidateError" @click="pending ? execute() : saveEditor()">{{ busy ? '保存中…' : pending ? '原样重试' : '保存' }}</Button></footer>
    </DialogContent></DialogPortal></DialogRoot>
  </section>
</template>

<style scoped>
.carton-mark-tools { container: carton-mark-tools / inline-size; }
.carton-mark-filters.carton-filter-bar { border-bottom: 0; }
.carton-mark-filters :deep(.carton-filter-inline > .carton-filter-fields) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.carton-mark-filters :deep(.carton-filter-inline > .carton-filter-actions) { margin-inline-start: auto; }
.carton-mark-filter-wide { grid-column: span 2; }
@container carton-mark-tools (min-width: 544px) {
  .carton-mark-filters :deep(.carton-filter-inline > .carton-filter-fields) {
    flex-basis: 420px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .carton-mark-filter-wide { grid-column: auto; }
}
@container carton-mark-tools (min-width: 1100px) {
  .carton-mark-filters :deep(.carton-filter-inline > .carton-filter-fields) { grid-template-columns: repeat(6, minmax(0, 1fr)); }
}
</style>
