<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, useId, watch } from 'vue'
import { DialogRoot, DialogTrigger, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { FileUp, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth'
import { cartonQuickAssetsApi, type AssetDepartment, type QuickAsset, type QuickAssetStatus, type QuickTarget, type QuickUploadBody } from '@/api/cartonQuickAssets'
import { canQuickAsset, departmentLabel, quickStatusLabel, responseStatus, suggestedContract, targetLabel, targetRef, uploadDepartments, viewerKey, type QuickAudience } from '@/features/carton-procurement/quickAssets'
import { getApiErrorMessage } from '@/lib/http'
import { factoryContexts } from '@/data/enterpriseMock'
import { createRandomUuid } from '@/lib/randomUuid'

const props = defineProps<{ factoryId: string; audience: QuickAudience; disabled?: boolean; supplierFactories?: string[] }>()
const emit = defineEmits<{ saved: [asset: QuickAsset] }>()
const auth = useAuthStore(), formId = useId()
const open = ref(false), mode = ref<'file' | 'text'>('file'), file = shallowRef<File>(), text = ref('')
const department = ref<AssetDepartment | ''>(''), contract = ref(''), status = ref<QuickAssetStatus>('PENDING')
const busy = ref(false), error = ref(''), success = ref(''), fileError = ref('')
const candidates = ref<QuickTarget[]>([]), loading = ref(false), loaded = ref(false), candidateError = ref(''), associationTouched = ref(false), orderSearch = ref('')
const frozen = shallowRef<{ factory: string; body: QuickUploadBody; file?: File } | null>(null)
const departments = computed(() => uploadDepartments(auth, props.factoryId, props.audience).filter(d => canQuickAsset(auth, props.factoryId, d, 'read')))
const canWrite = computed(() => !!department.value && departments.value.includes(department.value))
const canConfirm = computed(() => canWrite.value)
const context = computed(() => JSON.stringify([props.factoryId, props.audience, viewerKey(auth)]))
const chosenTargets = ref<string[]>([]), sharedFactories = ref<string[]>([])
const targetScope = computed(() => props.audience === 'sales' ? 'PENDING_SCHEDULE' as const : 'ALL' as const)
const visibleTargets = computed(() => candidates.value.filter(x => !orderSearch.value.trim() || [x.contract_no, x.customer_po, x.item_no, x.customer_name].join(' ').toLowerCase().includes(orderSearch.value.trim().toLowerCase())))
const shareOptions = computed(() => factoryContexts.filter(x => (props.supplierFactories || [props.factoryId]).includes(x.id)))
const validContent = computed(() => mode.value === 'file' ? !!file.value && !fileError.value : !!text.value.trim() && text.value.length <= 20000)
const canSave = computed(() => canWrite.value && !busy.value && chosenTargets.value.length <= 100 && (frozen.value || validContent.value && (
  associationTouched.value && !chosenTargets.value.length || !contract.value && !chosenTargets.value.length || loaded.value && !loading.value && !candidateError.value
)))
let generation = 0, searchGeneration = 0, timer: ReturnType<typeof setTimeout> | undefined
let searchController = new AbortController(), saveController = new AbortController()

function reset() {
  mode.value = 'file'; file.value = undefined; text.value = ''; contract.value = ''; orderSearch.value = ''
  status.value = 'PENDING'; error.value = ''; success.value = ''; fileError.value = ''
  department.value = departments.value.length === 1 ? departments.value[0]! : ''
  chosenTargets.value = []; sharedFactories.value = []
  candidates.value = []; candidateError.value = ''; loaded.value = false; associationTouched.value = false
}
function changeOpen(value: boolean) {
  if (busy.value && !value) return
  if (value && !frozen.value) reset()
  open.value = value
}
function selectFile(event: Event) {
  const input = event.target as HTMLInputElement, chosen = input.files?.[0]
  if (!chosen) return
  input.value = ''
  if (!/\.(pdf|xls|xlsx|xlsm|jpe?g|png|webp)$/i.test(chosen.name)) { fileError.value = '请选择 PDF、Excel、JPG、PNG 或 WebP 文件。'; return }
  if (!chosen.size || chosen.size > 20 * 1024 * 1024 || chosen.name.length > 255) { fileError.value = '文件须为1字节至20MB，文件名不超过255个字符。'; return }
  fileError.value = ''; file.value = chosen
}
watch([mode, file, text], () => {
  contract.value = suggestedContract(mode.value === 'file' ? file.value?.name || '' : text.value, mode.value === 'file')
  if (!associationTouched.value) orderSearch.value = contract.value
})
watch([contract, candidates], () => {
  if (associationTouched.value) return
  const matches = contract.value ? candidates.value.filter(x => x.contract_no.toUpperCase() === contract.value.toUpperCase()) : []
  const identities = matches.map(x => [x.kind, x.customer_code || x.customer_name, x.contract_no, x.item_no, x.customer_po].join('|'))
  chosenTargets.value = matches.length <= 100 && new Set(matches.map(x => x.customer_code || x.customer_name)).size === 1 && new Set(identities).size === matches.length ? matches.map(x => x.fingerprint) : []
})
function clearLinks() { associationTouched.value = true; chosenTargets.value = []; orderSearch.value = '' }
watch(canConfirm, value => { if (!value && status.value === 'READY') status.value = 'PENDING' })

async function loadCandidates(token: number) {
  const original = context.value
  loading.value = true
  try {
    const rows = await cartonQuickAssetsApi.candidates(props.factoryId, department.value as AssetDepartment, '', searchController.signal, targetScope.value)
    if (token !== searchGeneration || original !== context.value) return
    candidates.value = rows; loaded.value = true
  } catch (cause) {
    if (token === searchGeneration && original === context.value) candidateError.value = getApiErrorMessage(cause)
  } finally { if (token === searchGeneration) loading.value = false }
}
function search() {
  clearTimeout(timer); const token = ++searchGeneration
  searchController.abort(); searchController = new AbortController()
  candidates.value = []; loaded.value = false; loading.value = false; candidateError.value = ''; chosenTargets.value = []; associationTouched.value = false
  if (!open.value || !canWrite.value || frozen.value) return
  loading.value = true
  timer = setTimeout(() => { void loadCandidates(token) }, 200)
}
watch([open, department], search, { flush: 'sync' })
watch(context, () => {
  generation++; searchGeneration++; clearTimeout(timer); searchController.abort(); saveController.abort()
  busy.value = false; frozen.value = null; open.value = false; reset()
}, { flush: 'sync' })

async function submit() {
  if (!canSave.value) return
  const original = context.value, token = ++generation
  const request = frozen.value || { factory: props.factoryId, file: mode.value === 'file' ? file.value : undefined,
    body: { request_id: createRandomUuid(), owner_department: department.value as AssetDepartment,
      shared_factory_ids: props.audience === 'supplier' ? [...sharedFactories.value] : [],
      targets: candidates.value.filter(x => chosenTargets.value.includes(x.fingerprint)).map(targetRef), target_scope: targetScope.value,
      text: mode.value === 'text' ? text.value : '', contract_number: contract.value.trim(), status: status.value,
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
    if (code === undefined || code >= 500) {
      frozen.value = request; error.value = '保存结果尚未确认。请原样重试核实，系统会沿用同一次请求，避免重复上传。'
    } else if (code === 409) {
      frozen.value = null; error.value = '资料或关联目标已更新，请刷新关联后核对再保存。'; search()
    } else { frozen.value = null; error.value = getApiErrorMessage(cause) }
  } finally { if (token === generation) busy.value = false }
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
          <div class="min-w-0"><DialogTitle class="text-lg font-bold">上传资料</DialogTitle><DialogDescription class="mt-1 text-xs text-muted-foreground">选择资料、勾选对应订单，再保存。可多选，也可暂不关联。</DialogDescription></div>
          <button type="button" aria-label="关闭快速上传" :disabled="busy" class="shrink-0 rounded-lg p-2 hover:bg-muted disabled:opacity-50" @click="changeOpen(false)"><X class="size-4" /></button>
        </header>
        <div class="min-h-0 space-y-4 overflow-y-auto p-4 sm:p-5">
          <fieldset :disabled="busy || !!frozen" class="min-w-0 space-y-4 disabled:opacity-70">
            <label v-if="departments.length > 1" class="block text-sm font-semibold">归属部门<select v-model="department" aria-label="资料归属部门" class="mt-1 h-10 w-full rounded-lg border border-input bg-card px-3 font-normal"><option value="">请选择本次归属部门</option><option v-for="d in departments" :key="d" :value="d">{{ departmentLabel[d] }}</option></select><span class="mt-1 block text-xs font-normal text-muted-foreground">多部门账号需明确选择，当前页面不代替归属选择。</span></label>
            <p v-else class="text-xs text-muted-foreground">归属：{{ department ? departmentLabel[department] : '暂无资料读写权限' }}</p>
            <div class="grid grid-cols-2 gap-2" role="group" aria-label="资料输入方式"><Button type="button" :variant="mode === 'file' ? 'default' : 'outline'" :aria-pressed="mode === 'file'" @click="mode = 'file'">文件</Button><Button type="button" :variant="mode === 'text' ? 'default' : 'outline'" :aria-pressed="mode === 'text'" @click="mode = 'text'">文字</Button></div>
            <div v-if="mode === 'file'" class="min-w-0 space-y-2">
              <label class="block text-sm font-semibold">文件<input type="file" accept=".pdf,.xls,.xlsx,.xlsm,.jpg,.jpeg,.png,.webp" aria-label="选择资料文件" class="mt-1 block w-full min-w-0 rounded-lg border border-input p-2 text-xs font-normal" @change="selectFile"></label>
              <p v-if="file" class="break-all text-sm">{{ file.name }} <button type="button" class="ml-2 text-primary underline" @click="file = undefined; fileError = ''">移除</button></p>
              <p class="text-xs text-muted-foreground">单文件不超过20MB；支持 PDF、Excel、JPG、PNG、WebP。</p>
              <p v-if="fileError" role="alert" class="text-sm text-destructive">{{ fileError }}</p>
            </div>
            <label v-else class="block text-sm font-semibold">文字资料<textarea v-model="text" maxlength="20000" rows="6" aria-label="文字资料" class="mt-1 block w-full rounded-lg border border-input bg-card p-3 font-normal" placeholder="输入需要留存的文字，可包含“合同号：…”" /><span class="mt-1 block text-right text-xs font-normal text-muted-foreground">{{ text.length }}/20000</span></label>
            <section class="space-y-3 rounded-xl border border-border p-3" aria-label="选择关联订单">
              <div class="flex flex-wrap items-center justify-between gap-2"><h3 class="text-sm font-semibold">{{ audience === 'sales' ? '关联排期订单（未下单）' : '关联订单' }} <span class="font-normal text-muted-foreground">可多选</span></h3><button type="button" class="text-xs text-primary underline" @click="clearLinks">暂不关联</button></div>
              <p class="text-xs text-muted-foreground">{{ audience === 'sales' ? '勾选后，仓库能在对应排期看到资料，下单时会沿用关联。' : '勾选这份资料对应的订单，关联不会提交采购。' }}</p>
              <input v-model="orderSearch" aria-label="搜索关联订单" placeholder="搜索客户、合同 / PO、货号" class="h-10 w-full min-w-0 rounded-lg border border-input bg-card px-3 text-sm">
              <p v-if="contract && !associationTouched" class="text-xs text-muted-foreground">识别到合同 {{ contract }}；{{ chosenTargets.length ? '已勾选匹配订单，请核对下方选项。' : '请核对并勾选对应订单。' }}</p>
              <p v-if="loading" role="status" class="text-sm text-muted-foreground">正在读取可关联订单…</p>
              <p v-else-if="candidateError" role="alert" class="text-sm text-destructive">{{ candidateError }} <button type="button" class="underline" @click="search">重新查询</button></p>
              <div v-else class="max-h-56 space-y-1 overflow-y-auto">
                <label v-for="target in visibleTargets" :key="target.fingerprint" class="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5"><input v-model="chosenTargets" type="checkbox" :value="target.fingerprint" class="mt-1 shrink-0" @change="associationTouched = true"><span class="min-w-0"><span class="block break-words font-semibold">{{ target.contract_no || '未填合同' }} · {{ target.item_no || '未填货号' }}</span><span class="mt-1 block break-words text-xs text-muted-foreground">{{ target.customer_name }} · PO {{ target.customer_po || '未填写' }} · {{ target.kind === 'SCHEDULE' ? '未下单排期' : targetLabel(target) }}</span><span v-if="target.kind === 'SCHEDULE'" class="block text-xs text-muted-foreground">{{ target.sheet }} 第{{ target.row }}行</span></span></label>
                <p v-if="loaded && !visibleTargets.length" class="py-3 text-sm text-muted-foreground">{{ orderSearch ? '没有匹配结果，请换个关键词；也可以暂不关联。' : audience === 'sales' ? '暂无未下单排期。可先保存资料，再补充关联。' : '暂无可关联订单，可先保存资料。' }}</p>
              </div>
              <p class="text-sm" role="status">{{ chosenTargets.length ? `已选择 ${chosenTargets.length} 条（包含搜索后隐藏的选择）` : '未关联，保存后可在资料库补充关联。' }}</p>
              <p v-if="chosenTargets.length > 100" role="alert" class="text-sm text-destructive">一次最多关联100条，请减少选择。</p>
            </section>
            <fieldset v-if="audience === 'supplier'" class="space-y-2 rounded-lg border border-border p-3"><legend class="text-sm font-semibold">共享厂区（默认无）</legend><p class="text-xs text-muted-foreground">不选择时仅供应商可见；选择后，该厂业务和仓库可以查看并更新资料状态。</p><label v-for="option in shareOptions" :key="option.id" class="flex items-center gap-2 text-sm"><input v-model="sharedFactories" type="checkbox" :value="option.id">{{ option.shortName }}</label></fieldset>
            <label class="block text-sm font-semibold">状态<select v-model="status" aria-label="资料状态" class="mt-1 h-10 w-full rounded-lg border border-input bg-card px-3 font-normal"><option value="DRAFT">初稿</option><option value="PENDING">待确认</option><option v-if="canConfirm" value="READY">已确认</option><option value="HISTORY">历史版本</option></select></label>
          </fieldset>
          <p v-if="error" role="alert" class="rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">{{ error }}</p>
          <p v-if="busy" role="status" class="text-sm text-muted-foreground">正在保存，请勿重复提交…</p>
        </div>
        <footer class="grid shrink-0 grid-cols-1 gap-2 border-t border-border bg-muted/30 p-4 sm:flex sm:justify-end">
          <Button type="button" variant="outline" :disabled="busy" @click="changeOpen(false)">取消</Button>
          <Button type="submit" :disabled="!canSave">{{ busy ? '保存中…' : frozen ? '原样重试保存' : '保存' }}</Button>
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
