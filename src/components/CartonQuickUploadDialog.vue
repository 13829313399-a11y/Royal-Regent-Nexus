<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, shallowRef, useId, watch } from 'vue'
import { DialogRoot, DialogTrigger, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { FileUp, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth'
import { cartonQuickAssetsApi, type AssetDepartment, type QuickAsset, type QuickAssetStatus, type QuickTarget, type QuickUploadBody } from '@/api/cartonQuickAssets'
import { canQuickAsset, departmentLabel, quickStatusLabel, responseStatus, suggestedContract, targetLabel, targetRef, uploadDepartments, viewerKey, type QuickAudience } from '@/features/carton-procurement/quickAssets'
import { getApiErrorMessage } from '@/lib/http'
import { factoryContexts } from '@/data/enterpriseMock'
import { createRandomUuid } from '@/lib/randomUuid'
import { saveUploadQueue, uploadSelection, validateUploadFiles, type QueuedUpload } from '@/features/carton-procurement/quickUploadQueue'

const props = defineProps<{ factoryId: string; audience: QuickAudience; disabled?: boolean; supplierFactories?: string[] }>()
const emit = defineEmits<{ saved: [asset: QuickAsset] }>()
const auth = useAuthStore(), formId = useId()
const open = ref(false), mode = ref<'file' | 'text'>('file'), text = ref('')
const queue = ref<QueuedUpload[]>([]), activeId = ref(''), textSelection = reactive(uploadSelection())
const activeFile = computed(() => queue.value.find(row => row.id === activeId.value))
const file = computed(() => activeFile.value?.file)
const selection = computed(() => mode.value === 'file' && activeFile.value ? activeFile.value : textSelection)
const contract = computed({ get: () => selection.value.contract, set: value => { selection.value.contract = value } })
const chosenTargets = computed({ get: () => selection.value.chosenTargets, set: value => { selection.value.chosenTargets = value } })
const associationTouched = computed({ get: () => selection.value.associationTouched, set: value => { selection.value.associationTouched = value } })
const orderSearch = computed({ get: () => selection.value.orderSearch, set: value => { selection.value.orderSearch = value } })
const department = ref<AssetDepartment | ''>(''), status = ref<QuickAssetStatus>('PENDING')
const busy = ref(false), error = ref(''), success = ref(''), fileError = ref('')
const candidates = ref<QuickTarget[]>([]), loading = ref(false), loaded = ref(false), candidateError = ref('')
const frozen = shallowRef<{ factory: string; body: QuickUploadBody; file?: File } | null>(null)
const departments = computed(() => uploadDepartments(auth, props.factoryId, props.audience).filter(d => canQuickAsset(auth, props.factoryId, d, 'read')))
const canWrite = computed(() => !!department.value && departments.value.includes(department.value))
const canConfirm = computed(() => canWrite.value)
const context = computed(() => JSON.stringify([props.factoryId, props.audience, viewerKey(auth)]))
const sharedFactories = ref<string[]>([])
const sharingMode = ref<'SUPPLIER' | 'INTERNAL'>('SUPPLIER')
const hasUnknown = computed(() => queue.value.some(row => row.state === 'unknown'))
const batchStarted = computed(() => queue.value.some(row => row.state !== 'pending'))
const activeLocked = computed(() => activeFile.value?.state === 'saved' || activeFile.value?.state === 'unknown')
const savedCount = computed(() => queue.value.filter(row => row.state === 'saved').length)
const pendingCount = computed(() => queue.value.length - savedCount.value)
const rowState = { pending: '待保存', saving: '保存中', saved: '已保存', failed: '保存失败', unknown: '结果待核实' }
const targetScope = computed(() => props.audience === 'sales' ? 'PENDING_SCHEDULE' as const : 'ALL' as const)
const visibleTargets = computed(() => candidates.value.filter(x => !orderSearch.value.trim() || [x.contract_no, x.customer_po, x.item_no, x.customer_name].join(' ').toLowerCase().includes(orderSearch.value.trim().toLowerCase())))
const contractMatches = computed(() => contract.value ? candidates.value.filter(x => x.contract_no.trim().toUpperCase() === contract.value.trim().toUpperCase()) : [])
const shareOptions = computed(() => factoryContexts.filter(x => (props.supplierFactories || [props.factoryId]).includes(x.id)))
const validContent = computed(() => !!text.value.trim() && text.value.length <= 20000)
const canSave = computed(() => {
  if (!canWrite.value || busy.value) return false
  if (mode.value === 'file') return pendingCount.value > 0 && queue.value.every(row => row.state === 'saved' || row.request
    || !row.needsReview && row.chosenTargets.length <= 100 && (row.associationTouched && !row.chosenTargets.length || !row.contract && !row.chosenTargets.length
      || loaded.value && !loading.value && !candidateError.value))
  return chosenTargets.value.length <= 100 && Boolean(frozen.value || !textSelection.needsReview && validContent.value && (
    associationTouched.value && !chosenTargets.value.length || !contract.value && !chosenTargets.value.length || loaded.value && !loading.value && !candidateError.value))
})
let generation = 0, searchGeneration = 0, timer: ReturnType<typeof setTimeout> | undefined
let searchController = new AbortController(), saveController = new AbortController()

function reset() {
  mode.value = 'file'; queue.value = []; activeId.value = ''; text.value = ''; Object.assign(textSelection, uploadSelection())
  status.value = 'PENDING'; error.value = ''; success.value = ''; fileError.value = ''
  department.value = departments.value.length === 1 ? departments.value[0]! : ''
  chosenTargets.value = []; sharedFactories.value = []; sharingMode.value = 'SUPPLIER'
  candidates.value = []; candidateError.value = ''; loaded.value = false; associationTouched.value = false
}
function changeOpen(value: boolean) {
  if (busy.value && !value) return
  if (value && !frozen.value && !queue.value.some(row => row.request || row.state === 'failed')) reset()
  open.value = value
}
function selectFile(event: Event) {
  const input = event.target as HTMLInputElement, chosen = Array.from(input.files ?? [])
  input.value = ''
  addFiles(chosen)
}
function addFiles(files: File[]) {
  if (!files.length || busy.value || hasUnknown.value || frozen.value) return
  const problem = validateUploadFiles([...queue.value.map(row => row.file), ...files])
  if (problem) { fileError.value = problem; return }
  const added = files.map(file => {
    const contract = suggestedContract(file.name, true)
    return { ...uploadSelection(), id: createRandomUuid(), file, contract, orderSearch: contract, state: 'pending' as const, error: '' }
  })
  queue.value.push(...added); activeId.value = added[0]!.id; fileError.value = ''; error.value = ''
  suggestSingleTarget()
}
function removeFile(id: string) {
  const row = queue.value.find(row => row.id === id)
  if (busy.value || row?.request || row?.state === 'saved') return
  queue.value = queue.value.filter(row => row.id !== id)
  if (activeId.value === id) activeId.value = queue.value[0]?.id || ''
  fileError.value = ''
}
watch([mode, text], () => {
  if (mode.value !== 'text') return
  Object.assign(textSelection, uploadSelection(), { contract: suggestedContract(text.value, false) })
  textSelection.orderSearch = textSelection.contract
  suggestSingleTarget()
})
function suggestSingleTarget() {
  if (!loaded.value || loading.value) return
  for (const row of [...queue.value, textSelection]) {
    if (row.needsReview || row.associationTouched || 'request' in row && row.request || 'state' in row && row.state === 'saved') continue
    const matches = row.contract ? candidates.value.filter(target => target.contract_no.trim().toUpperCase() === row.contract.trim().toUpperCase()) : []
    row.chosenTargets = matches.length === 1 ? [matches[0]!.fingerprint] : []
  }
}
watch([contract, candidates, loaded, loading], suggestSingleTarget)
function clearLinks() { selection.value.needsReview = false; associationTouched.value = true; chosenTargets.value = []; orderSearch.value = '' }
function confirmSelection() { selection.value.needsReview = false; associationTouched.value = true }
function applyLinksToOthers() {
  if (busy.value || hasUnknown.value || !activeFile.value || selection.value.needsReview || !loaded.value || loading.value || candidateError.value) return
  for (const row of queue.value) if (!row.request && row.state !== 'saved') {
    row.chosenTargets = [...chosenTargets.value]; row.associationTouched = true; row.needsReview = false
  }
}
watch(canConfirm, value => { if (!value && status.value === 'READY') status.value = 'PENDING' })

async function loadCandidates(token: number) {
  const original = context.value
  loading.value = true
  try {
    const rows = await cartonQuickAssetsApi.candidates(props.factoryId, department.value as AssetDepartment, '', searchController.signal, targetScope.value)
    if (token !== searchGeneration || original !== context.value) return
    const available = new Set(rows.map(row => row.fingerprint))
    for (const row of [...queue.value, textSelection]) {
      if ('request' in row && row.request || 'state' in row && row.state === 'saved') continue
      if (row.needsReview || row.chosenTargets.some(key => !available.has(key))) {
        row.chosenTargets = []; row.associationTouched = true; row.needsReview = true
        if ('error' in row) row.error = '关联订单已更新，请重新勾选对应订单或明确选择暂不关联。'
      }
    }
    candidates.value = rows; loaded.value = true
  } catch (cause) {
    if (token === searchGeneration && original === context.value) candidateError.value = getApiErrorMessage(cause)
  } finally { if (token === searchGeneration) loading.value = false }
}
function search(resetSelections = false) {
  clearTimeout(timer); const token = ++searchGeneration
  searchController.abort(); searchController = new AbortController()
  if (hasUnknown.value || frozen.value) return
  candidates.value = []; loaded.value = false; loading.value = false; candidateError.value = ''
  if (resetSelections) for (const row of [...queue.value, textSelection]) if (!('request' in row && row.request) && !('state' in row && row.state === 'saved')) {
    row.needsReview = row.needsReview || row.chosenTargets.length > 0
    row.chosenTargets = []; row.associationTouched = row.needsReview
  }
  if (!open.value || !canWrite.value) return
  loading.value = true
  timer = setTimeout(() => { void loadCandidates(token) }, 200)
}
watch(open, () => search(), { flush: 'sync' })
watch(department, () => search(true), { flush: 'sync' })
watch(context, () => {
  generation++; searchGeneration++; clearTimeout(timer); searchController.abort(); saveController.abort()
  busy.value = false; frozen.value = null; open.value = false; reset()
}, { flush: 'sync' })

async function submit() {
  if (!canSave.value) return
  if (mode.value === 'file') { await submitFiles(); return }
  const original = context.value, token = ++generation
  const retryingUnknown = Boolean(frozen.value)
  const request = frozen.value || { factory: props.factoryId, file: undefined,
    body: { request_id: createRandomUuid(), owner_department: department.value as AssetDepartment,
      shared_factory_ids: props.audience === 'supplier' ? [...sharedFactories.value] : [],
      ...(props.audience !== 'supplier' ? { sharing_mode: sharingMode.value } : {}),
      targets: candidates.value.filter(x => chosenTargets.value.includes(x.fingerprint)).map(targetRef), target_scope: targetScope.value,
      text: text.value, contract_number: contract.value.trim(), status: status.value,
      association: chosenTargets.value.length ? 'MANUAL' as const : 'NONE' as const,
    } }
  // Save exactly the checked rows. Server rechecks current scope and fingerprints.
  busy.value = true; error.value = ''; saveController = new AbortController()
  try {
    const asset = await cartonQuickAssetsApi.upload(request.factory, request.body, request.file, saveController.signal)
    if (token !== generation || original !== context.value) return
    frozen.value = null; success.value = `已保存 ${asset.file_name} · ${quickStatusLabel[asset.workflow.status] || asset.workflow.status}${asset.targets.length ? ' · 已关联' : ' · 未关联'}`
    open.value = false; emit('saved', asset)
  } catch (cause) {
    if (token !== generation || original !== context.value) return
    const code = responseStatus(cause)
    if (retryingUnknown || code === undefined || code >= 500) {
      frozen.value = request; error.value = '保存结果尚未确认。请原样重试核实，系统会沿用同一次请求，避免重复上传。'
    } else if (code === 409) {
      frozen.value = null; textSelection.needsReview = true; error.value = '资料或关联目标已更新，请刷新关联后核对再保存。'; search()
    } else { frozen.value = null; error.value = getApiErrorMessage(cause) }
  } finally { if (token === generation) busy.value = false }
}
async function submitFiles() {
  const original = context.value, token = ++generation
  const current = () => token === generation && original === context.value
  busy.value = true; error.value = ''; saveController = new AbortController()
  try {
    const latest = await saveUploadQueue(queue.value, {
      current,
      request: row => ({ factory: props.factoryId, file: row.file, body: {
        request_id: createRandomUuid(), owner_department: department.value as AssetDepartment,
        shared_factory_ids: props.audience === 'supplier' ? [...sharedFactories.value] : [],
        ...(props.audience !== 'supplier' ? { sharing_mode: sharingMode.value } : {}),
        targets: candidates.value.filter(target => row.chosenTargets.includes(target.fingerprint)).map(targetRef), target_scope: targetScope.value,
        text: '', contract_number: row.contract, status: status.value, association: row.chosenTargets.length ? 'MANUAL' : 'NONE',
      } }),
      upload: request => cartonQuickAssetsApi.upload(request.factory, request.body, request.file, saveController.signal),
    })
    if (!current()) return
    success.value = `已保存 ${savedCount.value} 个文件${pendingCount.value ? `，还有 ${pendingCount.value} 个待处理` : ''}`
    if (latest) emit('saved', latest)
    if (!pendingCount.value) open.value = false
    else {
      activeId.value = queue.value.find(row => row.state !== 'saved')?.id || ''
      error.value = hasUnknown.value ? '部分文件保存结果尚未确认。成功文件不会重传，请原样重试核实其余文件。' : '部分文件未保存，请按文件旁的提示处理后重试。'
      if (!hasUnknown.value && queue.value.some(row => row.needsReview)) search()
    }
  } finally { if (current()) busy.value = false }
}
onBeforeUnmount(() => { generation++; searchGeneration++; clearTimeout(timer); searchController.abort(); saveController.abort() })
</script>

<template>
  <DialogRoot :open="open" @update:open="changeOpen">
    <DialogTrigger as-child><Button type="button" :disabled="disabled || !departments.length"><FileUp class="size-4" />快速上传</Button></DialogTrigger>
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/45" />
      <DialogContent as="form" :id="formId" class="quick-upload fixed left-1/2 top-1/2 z-[71] flex max-h-[calc(100dvh-1.5rem)] w-[calc(100%_-_1.5rem)] max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-border bg-card text-foreground shadow-2xl" @submit.prevent="submit" @escape-key-down="event => { if (busy) event.preventDefault() }" @interact-outside="event => event.preventDefault()">
        <header class="flex shrink-0 items-start justify-between gap-3 border-b border-border p-4 sm:px-5">
          <div class="min-w-0"><DialogTitle class="text-lg font-bold">上传资料</DialogTitle><DialogDescription class="mt-1 text-xs text-muted-foreground">可多选文件，逐个核对关联后一起保存；也可暂不关联。</DialogDescription></div>
          <button type="button" aria-label="关闭快速上传" :disabled="busy" class="shrink-0 rounded-lg p-2 hover:bg-muted disabled:opacity-50" @click="changeOpen(false)"><X class="size-4" /></button>
        </header>
        <div class="min-h-0 space-y-4 overflow-y-auto p-4 sm:p-5">
          <section v-if="mode === 'file' && (queue.length > 1 || queue.some(row => row.error))" aria-label="本批文件" class="space-y-2">
            <p class="text-sm font-semibold" role="status">共 {{ queue.length }} 个文件 · 已保存 {{ savedCount }} 个 · 待处理 {{ pendingCount }} 个</p>
            <ul class="max-h-48 space-y-2 overflow-y-auto">
              <li v-for="(row, index) in queue" :key="row.id" class="rounded-lg border p-2" :class="row.id === activeId ? 'border-primary bg-primary/5' : 'border-border'">
                <div class="flex items-start gap-2"><button type="button" :disabled="busy" :aria-label="`查看文件 ${index + 1} ${row.file.name}`" :aria-pressed="row.id === activeId" class="min-w-0 flex-1 break-all text-left text-sm font-semibold underline-offset-2 hover:underline" @click="activeId = row.id">{{ index + 1 }}. {{ row.file.name }}<span class="mt-1 block text-xs font-normal text-muted-foreground">{{ rowState[row.state] }} · {{ row.chosenTargets.length ? `关联 ${row.chosenTargets.length} 条` : '暂不关联' }}</span></button><button v-if="!row.request && row.state !== 'saved'" type="button" :disabled="busy || hasUnknown" :aria-label="`移除文件 ${index + 1} ${row.file.name}`" class="shrink-0 text-xs text-primary underline" @click="removeFile(row.id)">移除</button></div>
                <p v-if="row.error" role="alert" class="mt-2 break-words text-xs text-destructive">{{ row.error }}</p>
              </li>
            </ul>
          </section>
          <fieldset :disabled="busy || !!frozen || mode === 'file' && activeLocked" class="min-w-0 space-y-4 disabled:opacity-70">
            <p v-if="mode === 'file' && queue.length > 1" class="text-xs text-muted-foreground">归属部门、状态和共享范围用于本批待保存文件；关联订单只用于当前选中的文件。</p>
            <label v-if="departments.length > 1" class="block text-sm font-semibold">归属部门<select v-model="department" :disabled="hasUnknown" aria-label="资料归属部门" class="mt-1 h-10 w-full rounded-lg border border-input bg-card px-3 font-normal"><option value="">请选择本次归属部门</option><option v-for="d in departments" :key="d" :value="d">{{ departmentLabel[d] }}</option></select><span class="mt-1 block text-xs font-normal text-muted-foreground">多部门账号需明确选择，当前页面不代替归属选择。</span></label>
            <p v-else class="text-xs text-muted-foreground">归属：{{ department ? departmentLabel[department] : '暂无资料读写权限' }}</p>
            <label v-if="audience !== 'supplier'" class="block text-sm font-semibold">共享范围<select v-model="sharingMode" :disabled="hasUnknown" aria-label="上传共享范围" class="mt-1 h-10 w-full rounded-lg border border-input bg-card px-3 font-normal"><option value="SUPPLIER">内部与对应供应商共享</option><option value="INTERNAL">仅内部可见</option></select><span class="mt-1 block text-xs font-normal text-muted-foreground">同厂有权限的业务与仓库可查看；共享给供应商不要求关联订单。</span></label>
            <div class="grid grid-cols-2 gap-2" role="group" aria-label="资料输入方式"><Button type="button" :disabled="hasUnknown || mode === 'file' && batchStarted" :variant="mode === 'file' ? 'default' : 'outline'" :aria-pressed="mode === 'file'" @click="mode = 'file'">文件</Button><Button type="button" :disabled="hasUnknown || mode === 'file' && batchStarted" :variant="mode === 'text' ? 'default' : 'outline'" :aria-pressed="mode === 'text'" @click="mode = 'text'">文字</Button></div>
            <div v-if="mode === 'file'" class="min-w-0 space-y-2 rounded-lg border border-dashed border-border p-3" @dragover.prevent @drop.prevent="addFiles(Array.from($event.dataTransfer?.files ?? []))">
              <label class="block text-sm font-semibold">{{ queue.length ? '继续添加文件' : '文件' }}<input type="file" multiple :disabled="hasUnknown" accept=".pdf,.xls,.xlsx,.xlsm,.jpg,.jpeg,.png,.webp" aria-label="选择资料文件" class="mt-1 block w-full min-w-0 rounded-lg border border-input p-2 text-xs font-normal" @change="selectFile"></label>
              <p v-if="file" class="break-all text-sm">当前文件：{{ file.name }} <button v-if="queue.length === 1" type="button" :disabled="hasUnknown" class="ml-2 text-primary underline" @click="removeFile(activeId)">移除</button></p>
              <p class="text-xs text-muted-foreground">支持多选或拖入，可继续添加；每批最多50个 / 100MB，单文件不超过20MB。支持 PDF、Excel、JPG、PNG、WebP。</p>
              <p v-if="fileError" role="alert" class="text-sm text-destructive">{{ fileError }}</p>
            </div>
            <label v-else class="block text-sm font-semibold">文字资料<textarea v-model="text" maxlength="20000" rows="6" aria-label="文字资料" class="mt-1 block w-full rounded-lg border border-input bg-card p-3 font-normal" placeholder="输入需要留存的文字，可包含“合同号：…”" /><span class="mt-1 block text-right text-xs font-normal text-muted-foreground">{{ text.length }}/20000</span></label>
            <section class="space-y-3 rounded-xl border border-border p-3" aria-label="选择关联订单">
              <p v-if="mode === 'file' && file" class="break-all text-xs font-semibold text-primary">正在核对：{{ file.name }}</p>
              <div class="flex flex-wrap items-center justify-between gap-2"><h3 class="text-sm font-semibold">{{ audience === 'sales' ? '关联排期订单（未下单）' : '关联订单' }} <span class="font-normal text-muted-foreground">可多选</span></h3><button type="button" class="text-xs text-primary underline" @click="clearLinks">暂不关联</button></div>
              <p class="text-xs text-muted-foreground">选择这份资料适用的订单，货号和 PO 从订单带出，不用重复填写。同合同的资料不一定通用。</p>
              <p class="text-xs text-muted-foreground">{{ audience === 'sales' ? '勾选后，仓库能在对应排期看到资料，下单时会沿用关联。' : '勾选这份资料对应的订单，关联不会提交采购。' }}</p>
              <input v-model="orderSearch" aria-label="搜索关联订单" placeholder="搜索客户、合同 / PO、货号" class="h-10 w-full min-w-0 rounded-lg border border-input bg-card px-3 text-sm">
              <p v-if="contract && loaded && !associationTouched" class="text-xs text-muted-foreground">识别到合同 {{ contract }}；{{ contractMatches.length > 1 ? `找到 ${contractMatches.length} 条订单，请按货号、PO 勾选适用订单，不会自动全选。` : chosenTargets.length ? '仅找到一条匹配订单，已推荐勾选，请核对后保存。' : '请核对并勾选对应订单，也可暂不关联。' }}</p>
              <p v-if="loading" role="status" class="text-sm text-muted-foreground">正在读取可关联订单…</p>
              <div v-else-if="candidateError" role="alert" class="space-y-2 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm" data-testid="association-load-error">
                <p class="font-semibold text-destructive">未能读取可关联订单。</p>
                <p class="break-words text-muted-foreground">具体提示：{{ candidateError }}</p>
                <p v-if="frozen">保存结果尚未确认，请按下方提示原样重试核实。</p>
                <p v-else-if="associationTouched && !chosenTargets.length">已选择暂不关联。点击下方“保存”可先保存资料，之后在资料库补充关联。</p>
                <p v-else>可重新查询；也可选择暂不关联，再点击下方“保存”。暂不关联的资料不会自动挂到订单上。</p>
                <div class="flex flex-wrap gap-2">
                  <Button type="button" variant="outline" size="sm" @click="search()">重新查询</Button>
                  <Button v-if="!associationTouched || chosenTargets.length" type="button" variant="outline" size="sm" @click="clearLinks">暂不关联，继续保存</Button>
                </div>
              </div>
              <div v-else class="max-h-56 space-y-1 overflow-y-auto">
                <label v-for="target in visibleTargets" :key="target.fingerprint" class="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5"><input v-model="chosenTargets" type="checkbox" :value="target.fingerprint" class="mt-1 shrink-0" @change="confirmSelection"><span class="min-w-0"><span class="block break-words font-semibold">{{ target.contract_no || '未填合同' }} · {{ target.item_no || '未填货号' }}</span><span class="mt-1 block break-words text-xs text-muted-foreground">{{ target.customer_name }} · PO {{ target.customer_po || '未填写' }} · {{ target.kind === 'SCHEDULE' ? '未下单排期' : targetLabel(target) }}</span><span v-if="target.kind === 'SCHEDULE'" class="block text-xs text-muted-foreground">{{ target.sheet }} 第{{ target.row }}行</span></span></label>
                <p v-if="loaded && !visibleTargets.length" class="py-3 text-sm text-muted-foreground">{{ orderSearch ? '没有匹配结果，请换个关键词；也可以暂不关联。' : audience === 'sales' ? '暂无未下单排期。可先保存资料，再补充关联。' : '暂无可关联订单，可先保存资料。' }}</p>
              </div>
              <p class="text-sm" role="status">{{ chosenTargets.length ? `已选择 ${chosenTargets.length} 条（包含搜索后隐藏的选择）` : '未关联，保存后可在资料库补充关联。' }}</p>
              <p v-if="chosenTargets.length > 100" role="alert" class="text-sm text-destructive">一次最多关联100条，请减少选择。</p>
              <Button v-if="mode === 'file' && queue.length > 1" type="button" variant="outline" size="sm" class="h-auto max-w-full whitespace-normal text-left" :disabled="hasUnknown || selection.needsReview || !loaded || loading || !!candidateError" @click="applyLinksToOthers">将当前关联应用到其他未保存文件</Button>
            </section>
            <fieldset v-if="audience === 'supplier'" :disabled="hasUnknown" class="space-y-2 rounded-lg border border-border p-3"><legend class="text-sm font-semibold">共享厂区（默认无）</legend><p class="text-xs text-muted-foreground">不选择时仅供应商可见；选择后，该厂业务和仓库可以查看并更新资料状态。</p><label v-for="option in shareOptions" :key="option.id" class="flex items-center gap-2 text-sm"><input v-model="sharedFactories" type="checkbox" :value="option.id">{{ option.shortName }}</label></fieldset>
            <label class="block text-sm font-semibold">状态<select v-model="status" :disabled="hasUnknown" aria-label="资料状态" class="mt-1 h-10 w-full rounded-lg border border-input bg-card px-3 font-normal"><option value="DRAFT">初稿</option><option value="PENDING">待确认</option><option v-if="canConfirm" value="READY">已确认</option><option value="HISTORY">历史版本</option></select></label>
          </fieldset>
          <p v-if="error" role="alert" class="rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">{{ error }}</p>
          <p v-if="busy" role="status" class="text-sm text-muted-foreground">正在保存，请勿重复提交…</p>
        </div>
        <footer class="grid shrink-0 grid-cols-1 gap-2 border-t border-border bg-muted/30 p-4 sm:flex sm:justify-end">
          <Button type="button" variant="outline" :disabled="busy" @click="changeOpen(false)">取消</Button>
          <Button type="submit" :disabled="!canSave">{{ busy ? '保存中…' : frozen || hasUnknown ? '原样重试保存' : mode === 'file' && queue.length > 1 ? savedCount ? `重试剩余 ${pendingCount} 个文件` : `保存 ${pendingCount} 个文件` : '保存' }}</Button>
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
  <p v-if="success" role="status" class="mt-2 break-words text-sm text-primary">{{ success }}</p>
</template>

<style scoped>
.quick-upload { overflow-wrap:anywhere; }
@media(max-width:360px) { .quick-upload [role="group"] { grid-template-columns:minmax(0,1fr); } }
</style>
