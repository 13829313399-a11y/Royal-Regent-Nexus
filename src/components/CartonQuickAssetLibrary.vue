<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import CartonQuickUploadDialog from './CartonQuickUploadDialog.vue'
import { cartonQuickAssetsApi, type AssetDepartment, type QuickAsset, type QuickAssetStatus, type QuickTarget, type QuickTargetRef } from '@/api/cartonQuickAssets'
import { useAuthStore } from '@/stores/auth'
import { canQuickAsset, departmentLabel, internalDepartments, quickStatusLabel, responseStatus, targetLabel, targetRef, viewerKey, type QuickAudience } from '@/features/carton-procurement/quickAssets'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { factoryContexts } from '@/data/enterpriseMock'

const props = defineProps<{ factoryId: string; audience: QuickAudience; refreshKey?: number; supplierFactories?: string[]; search?: string; assetIds?: string[]; readOnly?: boolean }>()
const emit = defineEmits<{ changed: []; 'update:search': [value: string] }>()
const auth = useAuthStore()
const entries = ref<QuickAsset[]>([]), loading = ref(false), error = ref(''), actionError = ref(''), notice = ref('')
const filter = ref('CURRENT'), keyword = ref(''), mine = ref(false), busy = ref(false), downloading = ref('')
const statusDrafts = ref<Record<string, QuickAssetStatus>>({})
const allSupplierFactories = computed(() => props.audience === 'supplier' && (!props.factoryId || props.factoryId === 'ALL'))
const requestedFactories = computed(() => allSupplierFactories.value ? [...new Set(props.supplierFactories || [])] : props.factoryId && props.factoryId !== 'ALL' ? [props.factoryId] : [])
function readableDepartments(factory: string): AssetDepartment[] {
  // The server filters shared files by currently issued orders and explicit
  // denies. Listing that subset does not grant own-library maintenance.
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
watch(uploadFactories, factories => {
  if (!factories.includes(selectedUploadFactory.value)) selectedUploadFactory.value = factories[0] || ''
}, { immediate: true, flush: 'sync' })
function assetFactory(asset: QuickAsset) { return allSupplierFactories.value ? asset.factory_id : props.factoryId }
function factoryName(id: string) { return factoryContexts.find(x => x.id === id)?.shortName || id }
const context = computed(() => JSON.stringify([props.factoryId, props.audience, props.assetIds, props.supplierFactories, viewerKey(auth)]))
const uploadFilterLabel = computed(() => props.audience === 'supplier' ? '只看本供应商上传' : props.audience === 'sales' ? '只看业务部上传' : '只看仓库上传')
const matchingEntries = computed(() => entries.value.filter(x => {
  const query = (props.search ?? keyword.value).trim().toLowerCase()
  return (!mine.value || x.owner_department === (props.audience === 'supplier' ? 'supplier' : props.audience === 'sales' ? 'sales-business' : 'pmc-warehouse') || props.audience === 'warehouse' && x.owner_department === 'carton')
    && (!query || [x.file_name, x.contract_number, ...x.targets.flatMap(t => [targetLabel(t), t.customer_po])].join(' ').toLowerCase().includes(query))
}))
const documentState = (asset: QuickAsset) => asset.workflow.status === 'UNCLASSIFIED' ? 'DRAFT' : asset.workflow.status
const statusFilters = computed(() => [
  { id: 'CURRENT', label: '当前资料', count: matchingEntries.value.filter(x => documentState(x) !== 'HISTORY').length },
  { id: 'ALL', label: '全部版本', count: matchingEntries.value.length },
  ...(['DRAFT', 'PENDING', 'READY', 'HISTORY'] as const).map(id => ({ id, label: quickStatusLabel[id], count: matchingEntries.value.filter(x => documentState(x) === id).length })),
])
const visible = computed(() => matchingEntries.value.filter(x => filter.value === 'ALL' || (filter.value === 'CURRENT' ? documentState(x) !== 'HISTORY' : documentState(x) === filter.value)))
const editor = shallowRef<{ asset: QuickAsset; mode: 'associate' | 'share' } | null>(null)
const candidates = ref<QuickTarget[]>([]), selected = ref<string[]>([]), sharedFactories = ref<string[]>([]), candidateLoading = ref(false), candidateError = ref('')
const orderSearch = ref('')
const targetScope = computed(() => props.audience === 'sales' ? 'PENDING_SCHEDULE' as const : 'ALL' as const)
const associationLabel = computed(() => props.audience === 'sales' ? '关联排期订单' : '关联订单')
const visibleCandidates = computed(() => candidates.value.filter(x => !orderSearch.value.trim() || [x.customer_name, x.contract_no, x.customer_po, x.item_no].join(' ').toLowerCase().includes(orderSearch.value.trim().toLowerCase())))
const shareOptions = computed(() => factoryContexts.filter(x => (props.supplierFactories || [props.factoryId]).includes(x.id)))
type Command = { factory: string; asset: Pick<QuickAsset, 'id' | 'revision'>; requestId: string } & ({ kind: 'classify'; status: QuickAssetStatus } | { kind: 'associate'; targets: QuickTargetRef[] } | { kind: 'share'; factories: string[] })
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
    entries.value = props.assetIds ? data.items.filter(x => props.assetIds!.includes(x.id)) : data.items
    statusDrafts.value = Object.fromEntries(data.items.map(x => [x.id, x.workflow.status === 'UNCLASSIFIED' ? 'DRAFT' : x.workflow.status]))
  } catch (cause) { if (token === generation && original === context.value) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
function cancelContext() {
  actionGeneration++; editorGeneration++; downloadGeneration++
  actionController.abort(); editorController.abort(); downloadController.abort()
  pending.value = null; editor.value = null; busy.value = false; downloading.value = ''; actionError.value = ''; notice.value = ''; filter.value = 'CURRENT'; keyword.value = ''; mine.value = false
}
watch(context, cancelContext, { flush: 'sync' })
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
  busy.value = true; actionError.value = ''; actionController = new AbortController()
  try {
    if (request.kind === 'classify') await cartonQuickAssetsApi.classify(request.factory, request.asset, request.status, request.requestId, actionController.signal)
    else if (request.kind === 'associate') await cartonQuickAssetsApi.associate(request.factory, request.asset, request.targets, request.requestId, actionController.signal, targetScope.value)
    else await cartonQuickAssetsApi.share(request.factory, request.asset, request.factories, request.requestId, actionController.signal)
    if (context.value !== original || token !== actionGeneration) return
    pending.value = null; editor.value = null; notice.value = '资料已更新'; saved()
  } catch (cause) {
    if (context.value !== original || token !== actionGeneration) return
    const code = responseStatus(cause)
    if (code === undefined || code >= 500) { pending.value = request; actionError.value = '保存结果尚未核实，请沿用原请求重试。' }
    else { pending.value = null; actionError.value = code === 409 ? '资料已更新，请刷新后重新核对。' : getApiErrorMessage(cause); if (code === 409) { editor.value = null; void load() } }
  } finally { if (context.value === original && token === actionGeneration) busy.value = false }
}
async function edit(asset: QuickAsset, mode: 'associate' | 'share') {
  editor.value = { asset, mode }; selected.value = []; orderSearch.value = ''; sharedFactories.value = [...(asset.shared_factory_ids || [])]; candidateError.value = ''; candidates.value = []
  if (mode === 'share') return
  const token = ++editorGeneration, original = context.value
  editorController.abort(); editorController = new AbortController(); candidateLoading.value = true
  try {
    const factory = assetFactory(asset)
    const owner: AssetDepartment = props.audience === 'supplier' ? 'supplier' : readableDepartments(factory).find(d => canQuickAsset(auth, factory, d, 'manage')) || readableDepartments(factory)[0]!
    const rows = await cartonQuickAssetsApi.candidates(factory, owner, '', editorController.signal, targetScope.value, asset.id)
    if (token !== editorGeneration || original !== context.value) return
    candidates.value = rows
    selected.value = rows.filter(x => asset.targets.some(y => y.kind === x.kind && y.id === x.id && y.sheet === x.sheet && y.row === x.row)).map(x => x.fingerprint)
  } catch (cause) { if (token === editorGeneration && original === context.value) candidateError.value = getApiErrorMessage(cause) }
  finally { if (token === editorGeneration) candidateLoading.value = false }
}
function closeEditor(open: boolean) { if (!open && !busy.value && !pending.value) { editor.value = null; editorGeneration++; editorController.abort() } }
function saveEditor() {
  if (!editor.value || candidateLoading.value || candidateError.value) return
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
onBeforeUnmount(() => { generation++; controller.abort(); cancelContext() })
</script>

<template>
  <section class="min-w-0 rounded-xl border border-border bg-card p-4 sm:p-5" data-testid="quick-department-library">
    <header class="flex flex-wrap items-start justify-between gap-3"><div><h2 class="text-base font-bold">箱唛资料库</h2><p class="mt-1 text-xs text-muted-foreground">上传、选择状态、关联订单。同厂业务与仓库共享；供应商资料按所选厂区共享。</p></div><div v-if="!readOnly" class="flex flex-wrap items-end gap-3">
      <CartonQuickUploadDialog :factory-id="uploadFactory" :audience="audience" :supplier-factories="supplierFactories" @saved="saved" />
    </div></header>
    <p v-if="!requestedFactories.length" class="mt-4 text-sm text-muted-foreground">请先选择一个厂区，再查看资料或上传。</p>
    <p v-else-if="!scopes.length" role="status" class="mt-4 text-sm text-muted-foreground">当前账号没有本厂资料读取权限。</p>
    <template v-else>
      <div class="mt-4 flex flex-wrap items-end gap-3 rounded-lg bg-muted/40 p-3">
        <div class="flex min-w-0 flex-wrap gap-2" :class="audience === 'supplier' ? 'flex-1 basis-[36rem]' : 'w-full'" role="group" aria-label="筛选资料状态"><Button v-for="option in statusFilters" :key="option.id" type="button" :variant="filter === option.id ? 'default' : 'outline'" :aria-pressed="filter === option.id" :aria-label="`${option.label} ${loading || error ? '数量未读取' : option.count}`" :data-status-filter="option.id" class="min-h-10" @click="filter = option.id">{{ option.label }}<span class="rounded bg-current/5 px-1.5 tabular-nums">{{ loading || error ? '—' : option.count }}</span></Button></div>
        <label v-if="search === undefined" class="min-w-40 flex-1 text-xs">搜索资料<input v-model="keyword" aria-label="搜索资料" placeholder="文件名、合同、货号" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3 text-sm"></label>
        <div class="flex flex-wrap items-center gap-3" :class="{ 'ml-auto': audience === 'supplier' }">
          <label class="flex min-h-10 items-center gap-2 text-sm" title="按上传部门筛选，包含该部门其他同事上传的资料；不勾选时显示全部有权查看的资料。"><input v-model="mine" type="checkbox" :aria-label="uploadFilterLabel">{{ uploadFilterLabel }}</label>
          <Button type="button" variant="outline" :disabled="loading || busy || !!pending" @click="load">刷新资料</Button>
        </div>
      </div>
      <div v-if="allSupplierFactories" class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <label v-if="!readOnly && uploadFactories.length > 1" class="flex items-center gap-2 text-xs">关联订单厂区<select v-model="selectedUploadFactory" aria-label="上传关联订单厂区" class="h-9 rounded-lg border border-input bg-card px-3 text-sm"><option v-for="id in uploadFactories" :key="id" :value="id">{{ factoryName(id) }}</option></select></label>
        <p class="text-xs text-muted-foreground">{{ uploadFactories.length ? '可直接上传。关联订单厂区只用于查找订单；共享厂区在上传窗口另选，默认无。' : '可读取已发送订单的共享资料；上传与维护需要独立授权。' }}</p>
      </div>
      <p v-if="loading" role="status" class="py-6 text-sm text-muted-foreground">正在读取资料…</p>
      <p v-else-if="error" role="alert" class="mt-3 text-sm text-destructive">{{ error }} <button type="button" class="underline" @click="load">重试读取</button></p>
      <p v-else-if="!visible.length" class="py-6 text-sm text-muted-foreground">暂无符合条件的资料。可上传文件、照片或文字。</p>
      <ul v-else class="mt-3 divide-y divide-border">
        <li v-for="asset in visible" :key="asset.id" class="min-w-0 py-4" :data-quick-asset="asset.id">
          <div class="flex min-w-0 flex-wrap items-start justify-between gap-3">
            <div class="min-w-0 flex-1 basis-56"><p class="break-all text-sm font-semibold">{{ asset.file_name }}</p><p v-if="allSupplierFactories" class="mt-1 text-xs text-muted-foreground">订单厂区：{{ factoryName(asset.factory_id) }}</p><p class="mt-1 text-xs text-muted-foreground">{{ departmentLabel[asset.owner_department] || '历史资料' }} · {{ asset.created_by_name || '原上传人' }} · {{ asset.workflow.updated_by_name ? `${asset.workflow.updated_by_name} 更新状态` : '' }}</p><p class="mt-1 break-all text-xs text-muted-foreground">{{ asset.contract_number ? `合同 ${asset.contract_number} · ` : '' }}{{ asset.targets.length ? asset.targets.map(targetLabel).join('；') : '未关联订单' }}</p><p v-if="asset.owner_department === 'supplier' && audience === 'supplier'" class="mt-1 text-xs text-muted-foreground">共享：{{ asset.shared_factory_ids?.length ? asset.shared_factory_ids.map(id => factoryContexts.find(x => x.id === id)?.shortName || id).join('、') : '无，仅供应商可见' }}</p></div>
            <div class="flex flex-wrap items-center gap-2">
              <template v-if="canClassify(asset)"><select v-model="statusDrafts[asset.id]" :aria-label="`${asset.file_name} 状态`" :disabled="busy || !!pending" class="h-9 rounded-lg border border-input bg-card px-2 text-sm"><option v-for="state in statusChoices(asset)" :key="state" :value="state">{{ quickStatusLabel[state] }}</option></select><Button type="button" size="sm" :disabled="busy || !!pending || statusDrafts[asset.id] === asset.workflow.status" @click="execute({ ...commandBase(asset), kind: 'classify', status: statusDrafts[asset.id]! })">保存状态</Button></template>
              <span v-else class="rounded-md bg-muted px-2 py-1 text-xs">{{ quickStatusLabel[asset.workflow.status] }}</span>
              <Button v-if="!readOnly && asset.can_associate" type="button" variant="outline" size="sm" :disabled="busy || !!pending" @click="edit(asset, 'associate')">{{ associationLabel }}</Button>
              <Button v-if="!readOnly && audience === 'supplier' && asset.owner_department === 'supplier' && asset.can_classify" type="button" variant="outline" size="sm" :disabled="busy || !!pending" @click="edit(asset, 'share')">共享厂区</Button>
              <Button type="button" variant="outline" size="sm" :disabled="!!downloading" @click="download(asset)">{{ downloading === asset.id ? '下载中…' : '下载' }}</Button>
            </div>
          </div>
          <details v-if="asset.kind === 'text'" class="mt-2 text-xs"><summary class="cursor-pointer text-primary">查看文字</summary><pre class="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted p-3 font-sans text-sm">{{ asset.text }}</pre></details>
        </li>
      </ul>
      <p v-if="actionError && !editor" role="alert" class="mt-3 text-sm text-destructive">{{ actionError }} <button v-if="pending" type="button" :disabled="busy" class="underline" @click="execute()">原样重试</button></p>
      <p v-if="notice" role="status" class="mt-3 text-sm text-primary">{{ notice }}</p>
    </template>
    <DialogRoot :open="!!editor" @update:open="closeEditor"><DialogPortal><DialogOverlay class="fixed inset-0 z-50 bg-slate-950/45" /><DialogContent class="fixed left-1/2 top-1/2 z-50 flex max-h-[85dvh] overflow-hidden w-[calc(100%-2rem)] max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-border bg-card p-5 shadow-xl" @escape-key-down="(busy || pending) && $event.preventDefault()" @interact-outside="(busy || pending) && $event.preventDefault()">
      <DialogTitle class="text-lg font-bold">{{ editor?.mode === 'share' ? '共享厂区' : associationLabel }}</DialogTitle><DialogDescription class="mt-1 break-all text-sm text-muted-foreground">{{ editor?.asset.file_name }} · {{ editor?.mode === 'share' ? '默认无；选择后该厂业务和仓库可见。' : '可选择多个订单；取消全部选择可解除关联。' }}</DialogDescription>
      <p v-if="editor?.mode === 'associate'" class="mt-2 text-xs text-muted-foreground">{{ audience === 'supplier' ? '可关联当前厂区已向本供应商开放的采购单、样板或杂单。关联不会提交采购。' : audience === 'sales' ? '新增关联选择未下单排期；已关联的排期下单后继续保留。仓库能在排期中查看资料。' : '业务排期可在采购前关联；采购单是已创建的纸箱采购记录。关联只绑定资料，不代表已向供应商下单。' }}</p>
      <div class="my-4 min-h-0 flex-1 overflow-y-auto overscroll-contain" data-testid="asset-association-scroll"><fieldset :disabled="busy || !!pending" class="min-w-0 space-y-3 disabled:opacity-60"><template v-if="editor?.mode === 'share'"><label v-for="option in shareOptions" :key="option.id" class="flex items-center gap-2 text-sm"><input v-model="sharedFactories" type="checkbox" :value="option.id">{{ option.shortName }}</label></template><template v-else><p v-if="candidateLoading" role="status">正在读取可关联订单…</p><p v-else-if="candidateError" role="alert">{{ candidateError }}</p><input v-model="orderSearch" aria-label="搜索关联订单" placeholder="搜索客户、合同 / PO、货号" class="h-10 w-full rounded-lg border border-input bg-card px-3 text-sm"><p class="text-xs text-muted-foreground">已选择 {{ selected.length }} 条</p><label v-for="target in visibleCandidates" :key="target.fingerprint" class="flex items-start gap-2 text-sm"><input v-model="selected" type="checkbox" :value="target.fingerprint" class="mt-1 shrink-0">{{ targetLabel(target) }}{{ target.customer_po ? ` · PO ${target.customer_po}` : '' }}{{ target.kind === 'SCHEDULE' ? target.ordered ? ' · 已下单，保留关联' : ' · 未下单' : '' }}</label><p v-if="!candidateLoading && !candidateError && !candidates.length" class="text-sm text-muted-foreground">暂无可关联订单</p></template></fieldset></div>
      <p v-if="actionError" role="alert" class="mb-3 text-sm text-destructive">{{ actionError }}</p><footer class="flex shrink-0 justify-end gap-2 border-t border-border pt-4"><Button type="button" variant="outline" :disabled="busy || !!pending" @click="closeEditor(false)">取消</Button><Button type="button" :disabled="busy || candidateLoading || !!candidateError" @click="pending ? execute() : saveEditor()">{{ busy ? '保存中…' : pending ? '原样重试' : '保存' }}</Button></footer>
    </DialogContent></DialogPortal></DialogRoot>
  </section>
</template>
