<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import WarehouseLocationPicker from '../warehouse-operations/WarehouseLocationPicker.vue'
import MaterialHandoverMonthly from './MaterialHandoverMonthly.vue'
import { handoverReviewIssues } from './handoverReview'
const HandoverOriginalPrint = defineAsyncComponent(() => import('./HandoverOriginalPrint.vue').then(module => module.default))
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, RouterLink } from 'vue-router'
import axios from 'axios'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'
import { handoverApi, HANDOVER_FACTORY, type HandoverAction, type HandoverData, type HandoverDocument, type HandoverIssuer, type HandoverLine, type HandoverPosting, type HandoverSave, type HandoverSummary, type HandoverWorkspace, type HandoverLinkInput, type HandoverLinkAction, type HandoverPurchaseSources, type HandoverListFilters } from '@/api/materialHandover'

const props = defineProps<{ external?: boolean }>()
const route = useRoute(), auth = useAuthStore()
const key = computed(() => props.external ? new URLSearchParams(route.hash.replace(/^#/, '')).get('key') || '' : '')
const api = computed(() => handoverApi(key.value))
const tab = ref<'documents' | 'scan' | 'issuers' | 'monthly'>('documents')
const workspace = ref<HandoverWorkspace | null>(null), issuer = ref<HandoverIssuer | null>(null)
const summaries = ref<HandoverSummary[]>([]), issuers = ref<HandoverIssuer[]>([])
const moreAvailable = ref(false)
const emptyFilters = (): HandoverListFilters => ({ search: '', supplier_id: '', kind: 'ALL', status: 'ALL' })
const filters = ref(emptyFilters()), appliedFilters = ref(emptyFilters()), total = ref(0)
const hasFilters = computed(() => Object.entries(appliedFilters.value).some(([key, value]) => value !== emptyFilters()[key as keyof HandoverListFilters]))
const pendingDeliveriesOnly = computed(() => !props.external && route.query.deliveries === 'pending')
const selected = ref<HandoverDocument | null>(null), draft = ref<HandoverData | null>(null)
const error = ref(''), notice = ref(''), busy = ref(false), loading = ref(false)
const showOptional = ref(false)
const reviewIssues = computed(() => draft.value ? handoverReviewIssues(draft.value) : [])
const invalidFields = computed(() => new Set(reviewIssues.value.flatMap(issue => issue.fields)))
const compactSupplierForm = computed(() => props.external && !showOptional.value)
const sourceUrl = ref(''), qrUrl = ref(''), scanCode = ref(''), fileInput = ref<HTMLInputElement | null>(null)
const scanInput = ref<HTMLInputElement | null>(null)
const printBlob = shallowRef<Blob>(), printUrl = ref(''), printCorner = ref<'left'|'right'>('right')
const printPreparing = ref(false), printRendering = ref(false), printReady = ref(false), printWanted = ref(false), printToken = ref('')
const printMode = ref<'original'|'summary'>('original')
let printSequence = 0
const posting = ref<Record<string, { selected: boolean; quantity: string; batch_id: string; location_id: string; lot: string; roll_no: string; purchase_source_id: string; difference_reason: string }>>({})
const purchaseSources = ref<HandoverPurchaseSources | null>(null), purchaseLoading = ref(false), purchaseReady = ref(false), purchaseError = ref('')
let purchaseSequence = 0
const businessDate = ref(new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date()))
const issuerName = ref(''), issuerSupplier = ref(''), issuerKind = ref<HandoverIssuer['kind']>('SUPPLIER'), issuerDays = ref(365), newLink = ref('')
const bindSupplier = ref<Record<string,string>>({})
type Management = { kind: 'create' | 'renew' | 'bind' | 'revoke'; id: string; body: HandoverLinkInput | HandoverLinkAction }
const managementPending = ref<Management | null>(null)
const statusLabels = { DRAFT: '待核对', CONFIRMED: '已确认', VOID: '已作废' }
const progressLabels = { PENDING: '未收发', PARTIAL: '部分完成', COMPLETE: '全部完成' }
const dirty = computed(() => Boolean(selected.value?.status === 'DRAFT' && draft.value && JSON.stringify(draft.value) !== JSON.stringify(selected.value.data)))
const canEdit = computed(() => Boolean(props.external ? issuer.value : workspace.value?.can_operate))
const locked = computed(() => busy.value || loading.value || purchaseLoading.value || printPreparing.value || printRendering.value || Boolean(pending.value) || Boolean(managementPending.value))
const suppliers = computed(() => workspace.value?.suppliers || [])
const activeSuppliers = computed(() => suppliers.value.filter(row => row.status === 'ACTIVE'))
const canMonthly = computed(() => props.external && Boolean(issuer.value?.kind === 'SUPPLIER' && issuer.value.supplier_id))
type Pending = { kind: 'save' | 'confirm' | 'void' | 'post'; id: string; body: HandoverSave | HandoverAction | HandoverPosting; print_after?: boolean }
const pending = ref<Pending | null>(null)
let generation = 0
const uploadRequests = new WeakMap<File, string>()
const failedFiles = ref<File[]>([])
function clone<T>(value: T): T { return JSON.parse(JSON.stringify(value)) as T }
function uuid() { return crypto.randomUUID?.() || 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => { const n = Math.floor(Math.random() * 16); return (c === 'x' ? n : (n & 3) | 8).toString(16) }) }
function releasePrint() { printSequence++; if(printUrl.value)URL.revokeObjectURL(printUrl.value); printUrl.value='';printBlob.value=undefined;printPreparing.value=false;printRendering.value=false;printReady.value=false;printWanted.value=false;printToken.value='' }
function releaseUrls() { for (const value of [sourceUrl.value, qrUrl.value]) if (value) URL.revokeObjectURL(value); sourceUrl.value = ''; qrUrl.value = ''; releasePrint(); printMode.value='original' }
function clear() { generation++; purchaseSequence++; purchaseSources.value = null; purchaseLoading.value = false; purchaseReady.value = false; purchaseError.value = ''; workspace.value = null; issuer.value = null; summaries.value = []; moreAvailable.value = false; total.value = 0; filters.value = emptyFilters(); appliedFilters.value = emptyFilters(); selected.value = null; draft.value = null; posting.value = {}; issuers.value = []; pending.value = null; managementPending.value = null; bindSupplier.value = {}; failedFiles.value = []; newLink.value = ''; scanCode.value = ''; releaseUrls(); error.value = ''; notice.value = ''; busy.value = false; loading.value = false }
function showError(e: unknown) { if (axios.isAxiosError(e) && [401, 403].includes(e.response?.status || 0)) clear(); error.value = getApiErrorMessage(e) }
function scopeValid() { return props.external ? Boolean(key.value) : route.query.factory === HANDOVER_FACTORY }
function readList(offset = 0) { return pendingDeliveriesOnly.value ? api.value.pendingDeliveries(offset) : api.value.list(offset, appliedFilters.value) }
async function reloadList() { const epoch = generation; const result = await readList(); if (epoch === generation) { summaries.value = result.items; total.value = result.total ?? result.items.length; moreAvailable.value = typeof result.total === 'number' ? result.offset + result.items.length < result.total : result.items.length === result.limit } }
async function loadMore() { if (locked.value) return; const epoch = generation; loading.value = true; try { const result = await readList(summaries.value.length); if (epoch === generation) { summaries.value.push(...result.items.filter(row => !summaries.value.some(old => old.id === row.id))); total.value = result.total ?? summaries.value.length; moreAvailable.value = typeof result.total === 'number' ? result.offset + result.items.length < result.total : result.items.length === result.limit } } catch (e) { if (epoch === generation) showError(e) } finally { if (epoch === generation) loading.value = false } }
async function searchDocuments(reset = false) {
  if (locked.value || dirty.value || !scopeValid()) return
  if (reset) filters.value = emptyFilters()
  appliedFilters.value = { ...filters.value, search: filters.value.search.trim() }
  const epoch = generation
  loading.value = true; error.value = ''; summaries.value = []; total.value = 0; moreAvailable.value = false
  try { await reloadList() } catch (e) { if (epoch === generation) showError(e) }
  finally { if (epoch === generation) loading.value = false }
}
watch([tab, locked, selected], async () => {
  if (tab.value === 'scan' && !locked.value && !selected.value) { await nextTick(); scanInput.value?.focus() }
})
async function initialize() {
  clear(); const epoch = generation
  tab.value = !props.external && route.query.tab === 'scan' ? 'scan' : 'documents'
  if (!scopeValid()) { error.value = props.external ? '请使用仓库发放的完整专用制单链接。' : '请从华康C布料仓进入制单扫码。'; return }
  loading.value = true
  try {
    const client = api.value
    if (props.external) { const context = await client.context(); if (epoch !== generation) return; issuer.value = context }
    else { const result = await client.workspace(); if (epoch !== generation) return; workspace.value = result }
    await reloadList()
    if (epoch !== generation) return
    if (workspace.value?.can_manage) { const result = await client.issuers(); if (epoch === generation) issuers.value = result }
    if (epoch === generation && !props.external && typeof route.query.document === 'string') {
      loading.value = false
      await open(route.query.document)
    }
  } catch (e) { if (epoch === generation) showError(e) }
  finally { if (epoch === generation) loading.value = false }
}
watch(() => [props.external, key.value, route.query.factory, route.query.document, route.query.deliveries, route.query.tab, auth.currentUser?.id, auth.authorizationVersion], initialize, { immediate: true })
function accept(row: HandoverDocument) {
  purchaseSequence++; purchaseSources.value = null; purchaseLoading.value = false; purchaseReady.value = false; purchaseError.value = ''
  selected.value = row; draft.value = clone(row.data); showOptional.value = false
  posting.value = Object.fromEntries(row.data.lines.map(line => [line.id, { selected: false, quantity: row.progress[line.id]?.remaining || line.quantity, batch_id: '', location_id: '', lot: line.lot, roll_no: line.roll_no, purchase_source_id: '', difference_reason: '' }]))
}
async function loadPurchaseSources() {
  const doc = selected.value
  if (props.external || !doc || doc.status !== 'CONFIRMED' || doc.data.kind !== 'DELIVERY') return
  if (workspace.value?.can_read_purchase === false) { purchaseReady.value = true; return }
  const epoch = generation, ticket = ++purchaseSequence, client = api.value
  purchaseLoading.value = true; purchaseReady.value = false; purchaseError.value = ''
  try {
    const result = await client.purchaseSources(doc.id)
    if (epoch !== generation || ticket !== purchaseSequence || selected.value?.id !== doc.id) return
    if (result.document_revision !== selected.value.revision) { purchaseError.value = '单据已变化，请重新打开后核对采购实收进度。'; return }
    purchaseSources.value = result
    for (const [lineId, values] of Object.entries(result.lines)) {
      const state = posting.value[lineId]; if (!state) continue
      const old = values.find(value => value.id === state.purchase_source_id && value.can_receive)
      const recommended = values.filter(value => value.suggested && value.can_receive)
      state.purchase_source_id = old?.id || (recommended.length === 1 ? recommended[0]!.id : '')
    }
    purchaseReady.value = true
  } catch (e) { if (epoch === generation && ticket === purchaseSequence) { if (axios.isAxiosError(e) && [401,403].includes(e.response?.status || 0)) showError(e); else purchaseError.value = getApiErrorMessage(e) } }
  finally { if (epoch === generation && ticket === purchaseSequence) purchaseLoading.value = false }
}
function purchaseChoice(line: HandoverLine) { return purchaseSources.value?.lines[line.id]?.find(value => value.id === posting.value[line.id]?.purchase_source_id) }
function purchaseOverage(line: HandoverLine) {
  const choice = purchaseChoice(line); if (!choice || choice.remaining == null) return false
  return Object.values(posting.value).filter(value => value.selected && value.purchase_source_id === choice.id).reduce((total,value) => total + Number(value.quantity || 0), 0) > Number(choice.remaining)
}
async function open(id: string, force = false) {
  if (locked.value || (dirty.value && !force)) { error.value = dirty.value ? '请先保存当前核对内容，再切换单据。' : '请先核对未确认的提交结果。'; return }
  const epoch = generation, client = api.value; loading.value = true; error.value = ''
  try {
    const row = await client.detail(id); if (epoch !== generation) return
    releaseUrls(); accept(row)
    if (!props.external) { const latest = await client.workspace(); if (epoch !== generation) return; workspace.value = latest }
    await loadPurchaseSources()
  }
  catch (e) { if (epoch === generation) showError(e) }
  finally { if (epoch === generation) loading.value = false }
}
async function upload(files: File[]) {
  if (!canEdit.value || locked.value || dirty.value) { error.value = '请先保存当前草稿或核对未确认的提交结果。'; return }
  const epoch = generation, client = api.value; busy.value = true; error.value = ''; failedFiles.value = []
  let first: HandoverDocument | null = null
  for (const file of files) {
    if (epoch !== generation) break
    const requestId = uploadRequests.get(file) || uuid(); uploadRequests.set(file, requestId)
    try { const row = await client.upload(file, requestId); if (epoch !== generation) break; first ||= row; uploadRequests.delete(file) }
    catch (e) { if (epoch !== generation) break; failedFiles.value.push(file); showError(e); if (epoch !== generation) break; error.value = `${file.name}：${getApiErrorMessage(e)}` }
  }
  if (epoch !== generation) return
  if (first) { releaseUrls(); accept(first); notice.value = '原件已保存，请核对识别明细。' }
  try { await reloadList() } catch (e) { error.value = `已完成的上传保留；列表刷新失败：${getApiErrorMessage(e)}` }
  busy.value = false
}
function picked(event: Event) { const input = event.target as HTMLInputElement; const files = Array.from(input.files || []); input.value = ''; void upload(files) }
function dropped(event: DragEvent) { void upload(Array.from(event.dataTransfer?.files || [])) }
function addLine() { if (!draft.value) return; draft.value.lines.push({ id: 'L-' + uuid(), source_line: '', item_code: '', item_name: '', specification: '', color: '', quantity: '', unit: '', material_category: 'FABRIC', lot: '', roll_no: '', roll_quantities: '', contract_no: '', production_no: '', product_no: '', note: '' }) }
function unsure(e: unknown) { return axios.isAxiosError(e) && (!e.response || [408, 500, 502, 503, 504].includes(e.response.status)) }
async function mutate(value: Pending) {
  if (busy.value) return
  const epoch = generation, client = api.value; pending.value ||= clone(value); const frozen = pending.value
  busy.value = true; error.value = ''; notice.value = ''
  try {
    let result: HandoverDocument
    if (frozen.kind === 'save') result = await client.save(frozen.id, frozen.body as HandoverSave)
    else if (frozen.kind === 'post') result = await client.post(frozen.id, frozen.body as HandoverPosting)
    else result = await client.action(frozen.id, frozen.kind, frozen.body as HandoverAction)
    if (epoch !== generation) return
    pending.value = null; accept(result); notice.value = frozen.kind === 'post' ? (frozen.body as HandoverPosting).lines.some(line => line.purchase_source_id) ? '本次实收已保存，库存、单据剩余数量和采购待收进度已同步更新。' : '本次实际收发已保存，库存和剩余数量已更新。' : frozen.kind === 'save' && props.external ? '已保存为待核对单据。仓库可在单据管理中查看原件并补全；补齐并确认后才能打印交接二维码。' : '单据已保存。'
    if (frozen.print_after) { try { await printConfirmed() } catch (e) { if (epoch === generation) error.value = `单据已确认保存；原单加码准备失败，可重试：${getApiErrorMessage(e)}` } }
    // Refresh failures must never change a completed write into a failed write.
    try { await reloadList(); if (!props.external) { const inventory = await client.workspace(); if (epoch === generation) { workspace.value = inventory; await loadPurchaseSources() } } }
    catch (e) { if (epoch === generation) error.value = `操作已保存；刷新失败，请重新打开单据核对：${getApiErrorMessage(e)}` }
  } catch (e) { if (epoch === generation) { if (!unsure(e)) pending.value = null; showError(e) } }
  finally { if (epoch === generation) busy.value = false }
}
function draftSnapshot() { const data = clone(draft.value!); data.document_date = data.document_date || null; return data }
function save() { if (selected.value && draft.value) void mutate({ kind: 'save', id: selected.value.id, body: { request_id: uuid(), expected_revision: selected.value.revision, data: draftSnapshot() } }) }
function confirm() { if (!selected.value || !draft.value || locked.value || reviewIssues.value.length) return; void mutate({ kind: 'confirm', id: selected.value.id, print_after: true, body: { request_id: uuid(), expected_revision: selected.value.revision, acknowledge_warnings: true, reason: '', data: draftSnapshot() } }) }
const voidReason = ref(''), showVoid = ref(false)
function voidDocument() { if (!selected.value) return; void mutate({ kind: 'void', id: selected.value.id, body: { request_id: uuid(), expected_revision: selected.value.revision, acknowledge_warnings: false, reason: voidReason.value } }); showVoid.value = false }
async function scan() {
  if (locked.value || dirty.value) return
  const epoch = generation; loading.value = true; error.value = ''
  try { const row = await api.value.scan(scanCode.value.trim()); if (epoch !== generation) return; releaseUrls(); accept(row); tab.value = 'scan'; const latest = await api.value.workspace(); if (epoch === generation) { workspace.value = latest; await loadPurchaseSources() } }
  catch (e) { if (epoch === generation) showError(e) }
  finally { if (epoch === generation) loading.value = false }
}
function post() {
  if (!selected.value || !workspace.value || locked.value) return
  if (selected.value.data.kind === 'DELIVERY' && !purchaseReady.value) { error.value = '请先加载并核对采购待收明细。'; return }
  const selectedRows = Object.entries(posting.value).filter(([, row]) => row.selected)
  if (selectedRows.some(([id,row]) => (purchaseSources.value?.lines[id]?.length || 0) > 0 && !row.purchase_source_id)) { error.value = '请为本次实收选择对应采购待收明细。'; return }
  const lines = selectedRows.map(([line_id, row]) => {
    const choice = purchaseSources.value?.lines[line_id]?.find(value => value.id === row.purchase_source_id)
    return { line_id, quantity: row.quantity, batch_id: row.batch_id, location_id: row.location_id, lot: row.lot, roll_no: row.roll_no,
      ...(choice ? { purchase_source_id: choice.id, expected_source_revision: choice.revision, expected_receipt_count: choice.receipt_count, difference_reason: row.difference_reason } : {}) }
  })
  if (!lines.length) { error.value = '请勾选本次实际收到或发出的明细。'; return }
  void mutate({ kind: 'post', id: selected.value.id, body: { factory_id: HANDOVER_FACTORY, request_id: uuid(), expected_revision: selected.value.revision, expected_inventory_revision: workspace.value.inventory.revision, code_version: selected.value.code_version, business_date: businessDate.value, lines } })
}
function batches(line: HandoverLine) { return (workspace.value?.inventory.stock || []).filter(b => b.item_code === line.item_code && b.unit === line.unit && Number(b.available_quantity) > 0 && (!line.lot || b.lot === line.lot)) }
async function preview(kind: 'source' | 'qr') {
  if (!selected.value) return
  const epoch = generation, identifier = selected.value.id
  try { const blob = await api.value.file(identifier, kind); if (epoch !== generation || selected.value?.id !== identifier) return; const target = kind === 'source' ? sourceUrl : qrUrl; if (target.value) URL.revokeObjectURL(target.value); target.value = URL.createObjectURL(blob) }
  catch (e) { if (epoch === generation) showError(e) }
}
function createIssuer() { void manage({ kind: 'create', id: '', body: { request_id: uuid(), name: issuerKind.value === 'REQUESTOR' ? issuerName.value : '', kind: issuerKind.value, supplier_id: issuerKind.value === 'SUPPLIER' ? issuerSupplier.value : '', valid_days: issuerDays.value } }) }
async function manage(value: Management) {
  if (busy.value) return; const epoch=generation,client=api.value;managementPending.value ||= clone(value);const frozen=managementPending.value;busy.value=true;error.value='';newLink.value=''
  try { const result=frozen.kind==='create' ? await client.createIssuer(frozen.body as HandoverLinkInput) : await client.linkAction(frozen.id,frozen.kind,frozen.body as HandoverLinkAction);if(epoch!==generation)return;managementPending.value=null
    if(result.token)newLink.value=`${location.origin}/material-handover/prepare#key=${result.token}`
    notice.value=result.replayed && !result.token && ['create','renew'].includes(frozen.kind) ? '链接操作已保存；密钥仅生成时返回。请更新原入口链接领取新密钥，历史单据不会丢失。' : '入口操作已保存。'
    try { const rows=await client.issuers();if(epoch===generation)issuers.value=rows } catch(e){if(epoch===generation)error.value=`操作已保存；列表刷新失败：${getApiErrorMessage(e)}`}
  } catch(e){if(epoch===generation){if(!unsure(e))managementPending.value=null;showError(e)}}finally{if(epoch===generation)busy.value=false}
}
function linkAction(value: HandoverIssuer, kind: 'renew'|'bind'|'revoke') { void manage({ kind, id: value.id, body: { request_id: uuid(), expected_revision: value.revision, ...(kind==='renew'?{valid_days:issuerDays.value}:{}), ...(kind==='bind'?{supplier_id:bindSupplier.value[value.id] || ''}:{}) } }) }
function chooseSupplier() { const supplier=activeSuppliers.value.find(row=>row.id===draft.value?.supplier_id);if(draft.value)draft.value.counterparty=supplier?.name || '' }
async function printConfirmed() {
  if(!selected.value || selected.value.status!=='CONFIRMED' || printPreparing.value)return
  releasePrint();printMode.value='original';const epoch=generation,id=selected.value.id,ticket=printSequence,client=api.value
  printPreparing.value=true;error.value=''
  try{const blob=await client.printFile(id,selected.value.revision,printCorner.value)
    if(epoch!==generation || ticket!==printSequence || selected.value?.id!==id)return
    printUrl.value=URL.createObjectURL(blob);printToken.value=`${epoch}:${ticket}:${id}`;printWanted.value=true;printRendering.value=true;printBlob.value=blob
  }catch(e){if(axios.isAxiosError(e) && e.response?.data instanceof Blob){try{e.response.data=JSON.parse(await e.response.data.text())}catch{}}
    if(epoch===generation && ticket===printSequence){showError(e);if(scopeValid())error.value=`原单加码准备失败，单据仍已保存：${getApiErrorMessage(e)}`}}
  finally{if(epoch===generation && ticket===printSequence)printPreparing.value=false}
}
async function originalReady(token:string){if(token!==printToken.value || !scopeValid())return;printRendering.value=false;printReady.value=true;await nextTick();if(token===printToken.value && printWanted.value){printWanted.value=false;window.print()}}
function originalFailed(token:string,message:string){if(token!==printToken.value)return;printRendering.value=false;printWanted.value=false;error.value=`原单已准备，浏览器预览失败：${message}。可下载加码 PDF 打印。`}
function reprintPrepared(){if(printReady.value && scopeValid()){printMode.value='original';window.print()}}
watch(printCorner,releasePrint)
async function print() {
  if(!selected.value)return
  const epoch=generation,id=selected.value.id
  releasePrint();printMode.value='summary'
  if(selected.value.status==='CONFIRMED'){await preview('qr');await nextTick();const picture=document.querySelector<HTMLImageElement>('.print-qr');if(picture?.decode)await picture.decode();if(!qrUrl.value)return}
  if(epoch===generation && selected.value?.id===id && scopeValid())window.print()
}
function preventUnload(event: BeforeUnloadEvent) { if (dirty.value || pending.value || managementPending.value) { event.preventDefault(); event.returnValue = '' } }
function refreshAuthorization() { void initialize() }
window.addEventListener('authorization-context-changed', refreshAuthorization)
window.addEventListener('beforeunload', preventUnload)
onBeforeRouteLeave(() => { if (dirty.value || pending.value || managementPending.value) { error.value = '请先保存核对内容或确认提交结果，再离开。'; return false }; return true })
onBeforeRouteUpdate(() => { if (dirty.value || pending.value || managementPending.value) { error.value = '请先保存核对内容或确认提交结果，再切换单据。'; return false }; return true })
onBeforeUnmount(() => { generation++; releaseUrls(); window.removeEventListener('authorization-context-changed', refreshAuthorization); window.removeEventListener('beforeunload', preventUnload) })
</script>

<template>
  <main class="handover" :class="{ 'original-print-active': printMode==='original' && printReady }">
    <header class="handover-header">
      <RouterLink v-if="!external" class="handover-back" to="/modules/pmc-warehouse/fabric-warehouse/receipts?factory=huakang-c&view=pending"><span aria-hidden="true">←</span> 返回待收料</RouterLink>
      <div><p class="eyebrow">{{ external ? '专用制单入口' : '华康C · 布料仓' }}</p><h1>制单与扫码交接</h1><p>{{ external ? `${issuer?.name || '制单方'} · 上传原单，核对明细后生成交接二维码` : '统一整理送货与领料单据，按实际数量分批收发' }}</p></div>
      <span class="scope-badge">{{ external ? (issuer?.name || '专用制单入口') : '仓库端 · 全部制单方' }}</span>
    </header>
    <nav class="handover-tabs" aria-label="单据交接功能"><button :class="{ active: tab === 'documents' }" :aria-current="tab === 'documents' ? 'page' : undefined" @click="tab = 'documents'">{{ external ? '上传与打印' : '单据管理' }}</button><button v-if="!external" :class="{ active: tab === 'scan' }" :aria-current="tab === 'scan' ? 'page' : undefined" @click="tab = 'scan'">扫码收发</button><button v-if="canMonthly" :class="{ active: tab === 'monthly' }" @click="tab = 'monthly'">本供应商数量记录</button><button v-if="!external && workspace?.can_manage" :class="{ active: tab === 'issuers' }" @click="tab = 'issuers'">制单方与链接</button></nav>
    <p v-if="error" class="handover-message error" role="alert">{{ error }}</p><p v-if="notice" class="handover-message success" role="status">{{ notice }}</p>
    <p v-if="loading || busy" class="handover-message" role="status">{{ busy ? '正在处理，请稍候…' : '正在加载…' }}</p>
    <aside v-if="pending && !busy" class="handover-message warning"><p>提交结果尚未确认，已保留原提交内容。可重试原提交；请勿另建一笔重复收发。</p><button @click="mutate(pending)">重试原提交</button></aside>
    <aside v-if="managementPending && !busy" class="handover-message warning"><p>链接操作结果待确认，已保留原请求。</p><button @click="manage(managementPending)">重试原链接操作</button></aside>
    <p v-if="printPreparing" class="handover-message" role="status">正在按原单版式准备加码打印，请稍候…</p>
    <div v-if="printUrl" class="actions"><button :disabled="!printReady || locked" @click="reprintPrepared">打印已准备原单</button><a :href="printUrl" :download="`${selected?.data.source_no || '交接单'}-原单加码.pdf`">下载加码原单 PDF</a></div>
    <HandoverOriginalPrint v-if="printBlob" :file="printBlob" :token="printToken" @ready="originalReady" @failed="originalFailed" />
    <MaterialHandoverMonthly v-if="tab === 'monthly' && canMonthly" :client="api" :external="external" :suppliers="suppliers" />
    <section v-else-if="tab === 'issuers' && !external && workspace?.can_manage" class="card">
      <h2>发放专用制单链接</h2><p>每家供应商使用固定入口，只能查看本供应商通过专用入口提交的单据；领用方只能查看本入口单据。仓库内部上传的原件不会自动对外开放，实物收发由仓库确认。</p>
      <p v-if="!activeSuppliers.length" class="review-warning">请先在布料仓「基础资料 → 往来单位」维护并启用供应商，再回到这里发放链接。</p>
      <form class="fields" @submit.prevent="createIssuer"><label>用途<select v-model="issuerKind" :disabled="locked"><option value="SUPPLIER">供应商送货</option><option value="REQUESTOR">裁床 / 车间领料</option></select></label><label v-if="issuerKind==='SUPPLIER'">供应商基础资料<select v-model="issuerSupplier" required :disabled="locked" aria-label="入口供应商"><option value="">请选择已启用供应商</option><option v-for="party in activeSuppliers" :key="party.id" :value="party.id">{{ party.code }} · {{ party.name }}</option></select></label><label v-else>领用方名称<input v-model="issuerName" required maxlength="255" :disabled="locked" /></label><label>有效天数<input v-model.number="issuerDays" type="number" min="1" max="365" :disabled="locked" /></label><button :disabled="locked">生成专用链接</button></form>
      <label v-if="newLink" class="link-result">请保存并发给对应制单方<input :value="newLink" readonly aria-label="专用制单链接" /></label>
      <p>更新链接会让旧密钥失效，原单据和月度记录仍归同一供应商。旧入口必须先关联基础资料，不能凭名称自动合并。</p><div class="table-scroll"><table><thead><tr><th>制单方 / 编号</th><th>用途</th><th>有效期</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="value in issuers" :key="value.id"><td>{{ value.name }}<small>{{ value.supplier_code || (value.kind==='SUPPLIER'?'基础资料待关联':'领用方') }}</small></td><td>{{ value.kind === 'SUPPLIER' ? '送货' : '领料' }}</td><td>{{ value.expires_at.slice(0, 10) }}</td><td>{{ value.active ? '可用' : '已停用' }}</td><td><template v-if="value.kind==='SUPPLIER' && !value.supplier_id"><select v-model="bindSupplier[value.id]" :disabled="locked" :aria-label="`${value.name}关联供应商`"><option value="">选择同名基础资料</option><option v-for="party in activeSuppliers.filter(p=>p.name===value.name)" :key="party.id" :value="party.id">{{ party.code }} · {{ party.name }}</option></select><button :disabled="locked || !bindSupplier[value.id]" @click="linkAction(value,'bind')">关联原入口</button></template><button v-else :disabled="locked" @click="linkAction(value,'renew')">续期并更新链接</button><button v-if="value.active" :disabled="locked" @click="linkAction(value,'revoke')">停用链接</button></td></tr></tbody></table></div>
    </section>
    <template v-else>
      <section v-if="tab === 'scan' && !external" class="card scan-card">
        <div class="scan-heading"><h2>扫码打开单据</h2><span>① 扫码打开　② 核对实物　③ 确认收发</span></div>
        <form @submit.prevent="scan"><label>扫描单据二维码<input ref="scanInput" v-model="scanCode" placeholder="扫码枪扫码后按回车，也可粘贴交接码" autocomplete="off" aria-label="扫描单据二维码" :disabled="locked || dirty" /></label><button class="primary" :disabled="locked || dirty || !scanCode.trim()">打开交接单</button></form><p>扫码仅打开明细。核对数量、仓位并确认本次收发后，才更新库存；同一张单支持分批办理。</p>
      </section>
      <section class="card document-tools">
        <div class="scope-note"><strong>{{ external ? '本制单方单据' : pendingDeliveriesOnly ? '待入库送货单' : '全部制单方单据' }}</strong><span>{{ external ? '仅显示本制单方通过专用入口提交的记录。' : pendingDeliveriesOnly ? '已确认、尚未全部入库的供应商送货单。' : '统一查看各供应商送货单和车间领料单，可按供应商单独筛选。' }}</span></div>
        <form v-if="!pendingDeliveriesOnly" class="document-filters" role="search" aria-label="查询交接单据" @submit.prevent="searchDocuments()">
          <label class="document-search"><span class="sr-only">搜索交接单据</span><input v-model="filters.search" type="search" maxlength="200" aria-label="搜索交接单据" placeholder="搜索单号、制单方、物料或生产单" :disabled="locked || dirty" /></label>
          <label v-if="!external">供应商<select v-model="filters.supplier_id" aria-label="筛选供应商" :disabled="locked || dirty || filters.kind === 'ISSUE'" @change="searchDocuments()"><option value="">全部供应商 / 领用方</option><option v-for="party in suppliers" :key="party.id" :value="party.id">{{ party.code }} · {{ party.name }}</option></select></label>
          <label v-if="!external">用途<select v-model="filters.kind" aria-label="筛选单据用途" :disabled="locked || dirty" @change="filters.kind === 'ISSUE' && (filters.supplier_id = ''); searchDocuments()"><option value="ALL">全部用途</option><option value="DELIVERY">送货单</option><option value="ISSUE">领料单</option></select></label>
          <label>状态<select v-model="filters.status" aria-label="筛选单据状态" :disabled="locked || dirty" @change="searchDocuments()"><option value="ALL">全部状态</option><option value="DRAFT">待核对</option><option value="CONFIRMED">已确认</option><option value="VOID">已作废</option></select></label>
          <button class="primary" :disabled="locked || dirty">查询</button><button type="button" :disabled="locked || dirty" @click="searchDocuments(true)">重置</button>
        </form>
        <RouterLink v-else :to="{ path: route.path, query: { factory: HANDOVER_FACTORY, tab: 'documents' } }">查看全部单据与筛选 →</RouterLink>
      </section>
      <div class="handover-layout">
        <aside class="card document-list">
          <div v-if="tab === 'documents' && canEdit" class="upload-box" @dragover.prevent @drop.prevent="dropped"><strong>{{ external ? '上传自己的原单' : '上传送货单 / 领料单' }}</strong><p>支持拖入 Excel、Word、PDF 或照片<br />每份 ≤ 20 MB，PDF ≤ 20 页</p><input ref="fileInput" type="file" multiple accept=".xls,.xlsx,.docx,.pdf,.png,.jpg,.jpeg,.webp" class="sr-only" @change="picked" /><button :disabled="locked || dirty" @click="fileInput?.click()">选择文件并识别</button></div>
          <div v-if="failedFiles.length" class="handover-message error"><p>{{ failedFiles.length }} 份文件未完成，原文件已保留。</p><button :disabled="locked" @click="upload([...failedFiles])">重试未完成文件</button></div>
          <div class="list-heading"><h2>单据列表 <span class="list-count">{{ total }}</span></h2><button :disabled="locked || dirty" @click="searchDocuments()">刷新</button></div>
          <small class="list-order">最近更新在前 · 已显示 {{ summaries.length }} 张</small>
          <p v-if="!summaries.length && !loading" class="list-empty">{{ hasFilters ? '没有符合条件的单据，请调整筛选或重置。' : pendingDeliveriesOnly ? '当前没有待入库的送货单。' : '暂无单据，上传原单或等待制单方提交。' }}</p>
          <button v-for="row in summaries" :key="row.id" class="document-item" :class="{ selected: selected?.id === row.id }" :aria-pressed="selected?.id === row.id" :disabled="locked || dirty" @click="open(row.id)"><span class="document-title">{{ row.data.source_no || '原单号待补' }}<span class="status-tag" :class="row.status.toLowerCase()">{{ statusLabels[row.status] }}</span></span><span class="document-party">{{ row.data.counterparty || '制单方待核对' }}</span><small>{{ row.data.kind === 'DELIVERY' ? '送货单' : '领料单' }} · {{ row.line_count }} 项 <span>{{ row.data.document_date || '日期待核对' }}</span></small></button>
          <button v-if="moreAvailable" :disabled="locked" @click="loadMore">加载更早单据</button>
        </aside>
        <section class="card document-detail">
          <div v-if="!selected" class="empty"><span class="empty-symbol" aria-hidden="true">{{ tab === 'scan' ? '▦' : '≡' }}</span><h2>{{ tab === 'scan' ? '等待扫描交接二维码' : '选择单据，查看原件与明细' }}</h2><p>{{ tab === 'scan' ? '使用上方扫码框，或从左侧选择单据。' : '从左侧选择已有单据，也可上传原单后开始核对。' }}</p><div class="empty-steps"><span><b>01</b>{{ tab === 'scan' ? '打开交接单' : '上传或选择原单' }}</span><span><b>02</b>{{ tab === 'scan' ? '核对本次数量与仓位' : '核对数量与单位' }}</span><span><b>03</b>{{ tab === 'scan' ? '确认本次实物收发' : '确认并打印二维码' }}</span></div><small>{{ tab === 'scan' ? '未到货或未发出的物料不勾选，剩余数量保留到下次办理。' : '原件与核对明细一起保留；确认单据后，实物收发仍需仓库办理。' }}</small></div>
          <template v-else-if="draft">
            <section class="print-document"><img v-if="qrUrl && selected.status==='CONFIRMED'" :src="qrUrl" alt="交接单二维码" class="print-qr" /><h2>{{ selected.data.kind==='DELIVERY'?'供应商送货交接单':'领料交接单' }}</h2><p>{{ selected.status==='CONFIRMED'?'已确认交接单':'草稿 · 仅供校对' }} · {{ selected.code }}</p><p>{{ selected.data.counterparty }} · 原单号 {{ selected.data.source_no }} · {{ selected.data.document_date }}</p><p>合同 {{ selected.data.contract_no || '未注明' }} · 生产单 {{ selected.data.production_no || '未注明' }} · 货号 {{ selected.data.product_no || '未注明' }}</p><table><thead><tr><th>物料编码</th><th>名称 / 规格 / 颜色</th><th>原单数量</th><th>缸号 / 卷号</th><th>参考单价 / 计价单位 / 币种</th><th>原单依据 / 生产关联</th></tr></thead><tbody><tr v-for="line in selected.data.lines" :key="line.id"><td>{{ line.item_code }}</td><td>{{ line.item_name }}<small>{{ line.specification }} {{ line.color }}</small></td><td>{{ line.quantity }} {{ line.unit }}</td><td>{{ line.lot }} / {{ line.roll_no }}<small>{{ line.roll_quantities }}</small></td><td>{{ line.unit_price || '未记录' }} / {{ line.price_unit || '未注明' }} / {{ line.currency || '未注明' }}</td><td>{{ line.price_note }}<small>{{ line.production_no }} {{ line.note }}</small></td></tr></tbody></table><p>数量以仓库实际点收 / 实发记录为准。参考单价是原单依据，付款金额需另行核对。</p></section>
            <div class="detail-heading"><div><p class="eyebrow">{{ statusLabels[selected.status] }} · {{ progressLabels[selected.processing_status] }}</p><h2>{{ selected.data.source_no || selected.file_name }}</h2><p>{{ selected.file_name }} · {{ selected.data.counterparty || '制单方待补' }}</p></div><button @click="preview('source')">查看原件</button></div>
            <iframe v-if="sourceUrl && selected.file_name.toLowerCase().endsWith('.pdf')" :src="sourceUrl" title="单据原件" class="source-preview" />
            <img v-else-if="sourceUrl && /\.(png|jpe?g|webp)$/i.test(selected.file_name)" :src="sourceUrl" alt="单据原件" class="source-preview" />
            <a v-else-if="sourceUrl" :href="sourceUrl" :download="selected.file_name">下载原始文档核对</a>
            <section v-if="selected.status === 'DRAFT'" class="draft-review" aria-label="确认前待补信息">
              <strong>{{ reviewIssues.length ? `确认打印前，还需补全 ${reviewIssues.length} 处信息` : '资料已齐全，可核对后确认打印' }}</strong>
              <ul v-if="reviewIssues.length"><li v-for="issue in reviewIssues" :key="issue.label">{{ issue.label }}</li></ul>
              <p>{{ external ? '不清楚的信息可留空，点击下方“保存，交仓库补全”。仓库可查看原件并继续补录。' : '可先保存待核对单据，补齐后再确认。保存和确认单据均不会直接入库。' }}</p>
            </section>
            <details v-if="selected.warnings.length" class="review-warning recognition-notes"><summary>原单识别提示 · {{ selected.warnings.length }} 项</summary><p>识别提示供对照原件参考，不影响保存。确认打印前请核对数量和单位。</p><ul><li v-for="text in selected.warnings" :key="text">{{ text }}</li></ul></details>
            <fieldset class="fields document-fields" :class="{ compact: compactSupplierForm }" :disabled="selected.status !== 'DRAFT' || !canEdit || locked"><label>单据用途<select v-model="draft.kind" :disabled="external || Boolean(selected.issuer_id)"><option value="DELIVERY">送货单</option><option value="ISSUE">领料申请 / 发料依据</option></select></label><label>原单号<input v-model="draft.source_no" maxlength="128" aria-label="原单号" :aria-invalid="selected.status === 'DRAFT' && invalidFields.has('原单号')" /></label><label>单据日期<input v-model="draft.document_date" type="date" aria-label="单据日期" :aria-invalid="selected.status === 'DRAFT' && invalidFields.has('单据日期')" /></label><label v-if="!external && !selected.issuer_id && draft.kind==='DELIVERY'">供应商基础资料<select v-model="draft.supplier_id" @change="chooseSupplier" aria-label="制单供应商" :aria-invalid="selected.status === 'DRAFT' && invalidFields.has('制单供应商')"><option value="">请选择已启用供应商</option><option v-for="party in activeSuppliers" :key="party.id" :value="party.id">{{ party.code }} · {{ party.name }}</option></select></label><label>供应商 / 领用方<input v-model="draft.counterparty" :readonly="external || Boolean(selected.issuer_id) || draft.kind==='DELIVERY'" maxlength="255" aria-label="制单方" :aria-invalid="selected.status === 'DRAFT' && invalidFields.has('制单方')" /></label><label class="optional-field">合同号<input v-model="draft.contract_no" maxlength="128" /></label><label class="optional-field">放产 / 生产单号<input v-model="draft.production_no" maxlength="128" /></label><label class="optional-field">货号<input v-model="draft.product_no" maxlength="128" /></label><label class="optional-field">说明<input v-model="draft.note" maxlength="1000" /></label></fieldset>
            <div class="line-heading"><h3 id="handover-lines-title">物料明细</h3><div class="actions"><button v-if="external" :aria-expanded="showOptional" @click="showOptional = !showOptional">{{ showOptional ? '收起选填信息' : '展开选填信息' }}</button><button v-if="selected.status === 'DRAFT'" :disabled="!canEdit || locked || draft.lines.length >= 200" @click="addLine">添加明细</button></div></div>
            <p v-if="external && selected.status === 'DRAFT'" class="line-help">按原单核对名称、数量和单位。物料编码不清楚可留空，由仓库补全；规格、缸号和价格等可展开选填。</p>
            <div class="table-scroll lines-scroll" role="region" aria-labelledby="handover-lines-title" tabindex="0"><table class="lines" :class="{ compact: compactSupplierForm }"><thead><tr><th>物料编码 / 名称</th><th>规格 / 颜色</th><th>单据数量 / 单位</th><th>类别</th><th>单价依据（选填）</th><th>缸号 / 卷号</th><th>关联 / 说明</th><th>进度 / 操作</th></tr></thead><tbody><tr v-for="(line, index) in draft.lines" :key="line.id"><td><input v-model="line.item_code" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" :aria-label="`第${index+1}行物料编码`" :aria-invalid="selected.status === 'DRAFT' && invalidFields.has(`第${index+1}行物料编码`)" placeholder="物料编码" /><input v-model="line.item_name" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" :aria-label="`第${index+1}行物料名称`" :aria-invalid="selected.status === 'DRAFT' && invalidFields.has(`第${index+1}行物料名称`)" placeholder="物料名称" /><small class="line-source">{{ line.source_line || `补录第 ${index + 1} 行` }}</small></td><td><input v-model="line.specification" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="规格" /><input v-model="line.color" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="颜色" /></td><td><input v-model="line.quantity" inputmode="decimal" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" :aria-label="`第${index+1}行单据数量`" :aria-invalid="selected.status === 'DRAFT' && invalidFields.has(`第${index+1}行单据数量`)" /><input v-model="line.unit" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" :aria-label="`第${index+1}行单位`" :aria-invalid="selected.status === 'DRAFT' && invalidFields.has(`第${index+1}行单位`)" placeholder="单位" /></td><td><select v-model="line.material_category" :disabled="selected.status !== 'DRAFT' || !canEdit || locked"><option value="FABRIC">布料</option><option value="ACCESSORY">辅料</option><option value="THREAD">线</option></select></td><td><input v-model="line.unit_price" inputmode="decimal" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" :aria-label="`第${index+1}行参考单价`" :aria-invalid="selected.status === 'DRAFT' && invalidFields.has(`第${index+1}行参考单价`)" placeholder="单价，空白为未记录" /><input v-model="line.price_unit" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="计价单位" /><select v-model="line.currency" :disabled="selected.status !== 'DRAFT' || !canEdit || locked"><option value="">币种未注明</option><option value="CNY">CNY 人民币</option><option value="HKD">HKD 港币</option><option value="USD">USD 美元</option><option value="EUR">EUR 欧元</option></select><input v-model="line.price_note" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="报价 / 含税口径等原单依据" /></td><td><input v-model="line.lot" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="缸号" /><input v-model="line.roll_no" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="卷号" /><small v-if="line.roll_quantities">逐卷：{{ line.roll_quantities }}</small></td><td><input v-model="line.production_no" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="放产 / 生产单号" /><input v-model="line.note" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="说明" /></td><td><template v-if="selected.status === 'CONFIRMED'"><p>已{{ selected.data.kind === 'DELIVERY' ? '收' : '发' }} {{ selected.progress[line.id]?.processed }} {{ line.unit }}</p><small>未完成 {{ selected.progress[line.id]?.remaining }} {{ line.unit }}</small></template><button v-else-if="selected.status === 'DRAFT'" :disabled="!canEdit || locked" @click="draft.lines.splice(index, 1)">移除此行</button></td></tr></tbody></table></div>
            <footer v-if="selected.status === 'DRAFT'" class="actions document-confirmation">
              <button :class="{ primary: external && reviewIssues.length > 0 }" :disabled="!canEdit || locked || (!external && !dirty)" @click="save">{{ external ? '保存，交仓库补全' : '保存核对内容' }}</button>
              <label>原单二维码位置<select v-model="printCorner" :disabled="locked" aria-label="原单二维码位置"><option value="right">右上角</option><option value="left">左上角</option></select></label>
              <button class="primary" :disabled="!canEdit || locked || reviewIssues.length > 0" aria-describedby="confirmation-help" @click="confirm">确认并打印原单</button>
              <p id="confirmation-help" class="confirmation-help">{{ reviewIssues.length ? '上方已列出待补项。可先保存，补齐后再确认打印。' : '点击“确认并打印原单”表示已对照原件核对明细、数量和单位；确认后明细将锁定。' }}</p>
            </footer>
            <section v-if="selected.status === 'CONFIRMED'" class="code-card"><div><h3>交接二维码</h3><p>原单纸面保留供应商信息与物料表，二维码放在新增顶部空白区域，不盖住原内容。可重复打印、分批使用；每次扫码仍需核对本次实物。</p><code>{{ selected.code }}</code><div class="actions"><button @click="preview('qr')">显示二维码</button><label>原单二维码位置<select v-model="printCorner" :disabled="locked" aria-label="原单二维码位置"><option value="right">右上角</option><option value="left">左上角</option></select></label><button :disabled="locked" @click="printConfirmed">原单加码打印</button><button :disabled="locked" @click="print">打印统一明细（备用）</button><a v-if="qrUrl" :href="qrUrl" :download="selected.id + '.svg'">下载二维码</a></div></div><img v-if="qrUrl" :src="qrUrl" alt="交接二维码" class="qr-image" /></section>
            <section v-if="selected.status === 'CONFIRMED' && !external && workspace?.can_operate" class="posting-card">
              <div class="line-heading"><h3>本次实际{{ selected.data.kind === 'DELIVERY' ? '收料入库' : '发料出库' }}</h3><label>实际日期<input v-model="businessDate" type="date" :disabled="locked" /></label></div>
              <p>未到 / 未发的明细不勾选；同一行可以分批办理，数量与单位不会自动换算。送货单实收关联采购待收明细后，库存与采购欠货同步更新，同一批货无需再次手工登记。</p>
              <template v-if="selected.data.kind === 'DELIVERY'">
                <p v-if="purchaseLoading" role="status">正在读取采购待收明细与最新实收进度…</p>
                <p v-if="purchaseError" class="review-warning error" role="alert">{{ purchaseError }}</p>
                <p v-if="workspace.can_read_purchase === false" class="review-warning">本账号没有采购来源查询权限；有采购来源的送货单需要取得布料仓查询及收料权限后关联办理。</p>
                <button :disabled="locked" @click="open(selected.id)">刷新采购与库存进度</button>
              </template>
              <fieldset :disabled="locked">
                <div v-for="line in selected.data.lines" :key="line.id" class="posting-row">
                  <label class="check-label"><input v-model="posting[line.id]!.selected" type="checkbox" :disabled="Number(selected.progress[line.id]?.remaining) <= 0" />{{ line.item_name }} · {{ line.item_code }}</label>
                  <label>本次数量<input v-model="posting[line.id]!.quantity" inputmode="decimal" :aria-label="`本次${line.item_code}数量`" /><small>{{ line.unit }} · 单据尚余 {{ selected.progress[line.id]?.remaining }}</small></label>
                  <template v-if="selected.data.kind === 'DELIVERY'">
                    <label v-if="purchaseSources?.lines[line.id]?.length">对应采购待收明细
                      <select v-model="posting[line.id]!.purchase_source_id" :aria-label="`${line.id}采购待收明细`">
                        <option value="">请选择对应采购单</option>
                        <option v-for="source in purchaseSources.lines[line.id]" :key="source.id" :value="source.id" :disabled="!source.can_receive">{{ source.order_no }} · {{ source.production_no || source.plan_no || '生产单未注明' }} · 尚欠 {{ source.remaining ?? '待核对' }} {{ source.unit }} · {{ source.id.slice(-8) }}{{ source.can_receive ? '' : '（须核对或授权）' }}</option>
                      </select>
                      <small v-if="purchaseChoice(line)">本系统已收 {{ purchaseChoice(line)!.received }}，采购尚欠 {{ purchaseChoice(line)!.remaining ?? '待核对' }} {{ line.unit }}；请核对采购单归属。</small>
                    </label>
                    <p v-else-if="purchaseReady && workspace.can_read_purchase !== false" class="review-warning">未匹配到本物料、单位和供应商的采购来源。本次可记录实际库存，采购欠货暂不能同步扣减，请先核对是否缺少采购资料。</p>
                    <label v-if="purchaseOverage(line)">超收说明<input v-model="posting[line.id]!.difference_reason" :aria-label="`${line.id}超收说明`" maxlength="1000" /></label>
                    <label>入库仓位<WarehouseLocationPicker v-model="posting[line.id]!.location_id" :locations="workspace.inventory.locations ?? []" :category="line.material_category" :disabled="locked" :label="`${line.item_code}入库仓位`" /></label>
                    <label>本次缸号<input v-model="posting[line.id]!.lot" /></label><label>卷号<input v-model="posting[line.id]!.roll_no" /></label>
                  </template>
                  <label v-else>实际出库批次<select v-model="posting[line.id]!.batch_id"><option value="">请选择批次与仓位</option><option v-for="batch in batches(line)" :key="batch.id" :value="batch.id">{{ batch.location }} · {{ batch.lot || '无缸号' }} / {{ batch.roll_no || '无卷号' }} · 可发 {{ batch.available_quantity }} {{ batch.unit }}</option></select></label>
                </div>
              </fieldset>
              <button class="primary" :disabled="locked || (selected.data.kind === 'DELIVERY' && !purchaseReady)" @click="post">确认本次实物收发</button>
            </section>
            <details v-if="selected.movements.length" class="history"><summary>本单实际收发记录 · {{ selected.movements.length }} 笔</summary><p v-for="movement in selected.movements" :key="movement.operation_id">{{ movement.business_date }} · {{ movement.line_id }} · {{ movement.quantity }} · {{ movement.reversed ? '已冲销' : '已入库存流水' }} · {{ movement.operation_id }}</p></details>
            <details v-if="selected.raw_text" class="history"><summary>查看识别原文与字段出处</summary><pre>{{ selected.raw_text }}</pre><pre>{{ JSON.stringify(selected.evidence, null, 2) }}</pre></details>
            <div v-if="selected.status !== 'VOID' && canEdit" class="actions"><button :disabled="locked || selected.movements.length > 0" @click="showVoid = !showVoid">作废未执行单据</button><form v-if="showVoid" @submit.prevent="voidDocument"><label>作废原因<input v-model="voidReason" required maxlength="1000" /></label><button :disabled="locked || !voidReason.trim()">确认作废</button></form></div>
          </template>
        </section>
      </div>
    </template>
  </main>
</template>

<style scoped>
.handover{min-height:100vh;background:#f4f6f5;color:#233a35;padding:28px;font:14px/1.6 sans-serif}.handover-header,.detail-heading,.list-heading,.line-heading{display:flex;align-items:center;justify-content:space-between;gap:20px}.handover-header{margin-bottom:22px}h1{font-size:28px;font-weight:650}h2{font-size:19px;font-weight:650}h3{font-size:16px;font-weight:650}.eyebrow{font-size:12px;letter-spacing:1.5px;color:#467468}p,small{color:#667a73}small{display:block;font-size:12px}a{color:#0e7867}button{border:1px solid #cadbd5;border-radius:7px;background:white;padding:8px 14px;color:#264d42;cursor:pointer;white-space:nowrap}button:disabled{opacity:.45;cursor:not-allowed}.primary,.handover-tabs .active{background:#126d5b;color:white;border-color:#126d5b}.handover-tabs,.actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:16px 0}.handover-layout{display:grid;grid-template-columns:280px minmax(0,1fr);gap:18px}.card{background:white;border:1px solid #dce5e1;border-radius:12px;padding:20px;min-width:0}.document-list{align-self:start}.upload-box{border:1px dashed #84b4a2;border-radius:9px;padding:22px 14px;text-align:center;background:#f4faf7;margin-bottom:22px}.upload-box p{margin:8px 0 14px}.document-item{display:flex;flex-direction:column;text-align:left;width:100%;margin:9px 0;padding:12px;white-space:normal}.document-item.selected{border-color:#278772;background:#f0faf5}.document-item span{font-weight:600}.fields{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:16px;border:0;padding:0;margin:20px 0}label{display:flex;flex-direction:column;gap:5px;color:#53665e}input,select{border:1px solid #cfdbd6;border-radius:6px;background:#fff;padding:8px;min-width:0;font:inherit;color:#233a35;max-width:100%}input:focus,select:focus{outline:2px solid #a6d4c3}input:disabled,select:disabled{background:#f8faf9;color:#566a60}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;text-align:left}th{padding:11px;background:#f4f8f5;font-size:12px;white-space:nowrap}td{padding:11px;border-bottom:1px solid #e8eee9;vertical-align:top}.lines input{display:block;width:155px;margin:5px 0}.lines td:nth-child(3) input{width:105px}.review-warning,.handover-message{padding:13px 16px;border-radius:8px;background:#f1f5f3;margin:14px 0}.review-warning,.warning{background:#fff7e8;color:#835f24}.review-warning li{margin:5px 0}.review-warning ul{padding-left:20px}.error{background:#fff0ec;color:#a2392d}.success{background:#eaf7ee;color:#287050}.source-preview{display:block;max-width:100%;width:100%;max-height:580px;border:1px solid #e5e9e6;border-radius:8px;margin:14px 0}iframe.source-preview{height:520px}.code-card{display:flex;align-items:center;justify-content:space-between;padding:20px;background:#f4faf6;margin:20px 0;border-radius:10px;gap:20px}.code-card code{display:block;overflow-wrap:anywhere;font-size:12px}.qr-image{width:160px;height:160px}.posting-card{border-top:1px solid #dce6df;padding-top:20px}.posting-card>p{margin:10px 0}.posting-card fieldset{border:0;padding:0}.posting-row{display:flex;align-items:start;gap:16px;flex-wrap:wrap;padding:16px 0;border-top:1px solid #e8eee9}.posting-row label:first-child{flex:1;min-width:200px}.posting-row input{max-width:160px}.posting-row select{max-width:400px}.check-label{flex-direction:row;align-items:center}.check-label input{width:auto}.history{padding:12px 0;border-top:1px solid #e6eee8}.history pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:320px;overflow:auto;padding:14px;background:#f6f8f6;font-size:12px}.empty{padding:90px 20px;text-align:center}.scan-card{margin-bottom:18px}.scan-card form{display:flex;align-items:end;gap:16px}.scan-card label{flex:1}.link-result{padding:16px;background:#ecf8f0}.link-result input{width:100%}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}@media(max-width:1100px){.fields{grid-template-columns:repeat(2,minmax(120px,1fr))}.handover-layout{grid-template-columns:240px minmax(0,1fr)}}@media(max-width:720px){.handover{padding:14px}.handover-layout{grid-template-columns:1fr}.handover-header{align-items:start}.handover-header a{font-size:12px}h1{font-size:22px}.document-list{max-height:430px;overflow:auto}.fields{grid-template-columns:1fr 1fr}.card{padding:15px}.code-card{flex-direction:column;align-items:start}.scan-card form{flex-direction:column;align-items:stretch}.posting-row{flex-direction:column}.posting-row label{width:100%}.posting-row input,.posting-row select{max-width:100%}}@media print{.handover{background:white;padding:0}.handover-header,.handover-tabs,.document-list,.scan-card,.handover-message,.actions,.posting-card,.history,.review-warning,.source-preview{display:none!important}.handover-layout{display:block}.document-detail{border:0;padding:0}.detail-heading button,.line-heading button{display:none}.fields{grid-template-columns:repeat(4,1fr)}input,select{border:0;padding:0;appearance:none}th,td{padding:5px}.lines input{width:auto}.qr-image{width:190px;height:190px}.code-card{break-inside:avoid;background:white}.lines{font-size:10px}.lines th:last-child,.lines td:last-child{display:none}}
</style>
<style scoped>
.handover{background:#f1f5f9;color:#0f172a;padding:20px;line-height:1.5}
.handover-header{justify-content:flex-start;gap:18px;margin-bottom:18px}
.handover-header h1{font-size:24px;line-height:1.4}
.handover-header p{margin:2px 0;font-size:13px;color:#64748b}
.handover-header .eyebrow{color:#0f766e;font-size:12px;letter-spacing:.5px}
.handover-back{display:inline-flex;align-items:center;gap:8px;flex-shrink:0;border:1px solid #cbd5e1;background:white;border-radius:8px;padding:10px 14px;color:#334155;text-decoration:none}
.handover-back:hover{border-color:#0f766e;color:#0f766e}
.scope-badge{margin-left:auto;border:1px solid #99f6e4;border-radius:20px;background:#f0fdfa;padding:6px 12px;color:#0f766e;font-size:12px;max-width:30%;overflow-wrap:anywhere}
.handover-tabs{gap:8px;margin:0 0 16px;padding:9px 12px;background:white;border:1px solid #e2e8f0;border-radius:10px}
.handover-tabs button{border-color:transparent;padding:9px 16px}
.handover-tabs button:not(.active):hover{background:#f1f5f9}
.primary,.handover-tabs .active{background:#0f766e;border-color:#0f766e}
.card{border-color:#e2e8f0;box-shadow:0 1px 2px #0f172a04}
.handover-layout{grid-template-columns:320px minmax(0,1fr);gap:16px}
.document-list{padding:16px}
.document-detail{min-height:390px}
.document-tools{margin-bottom:16px;padding:16px 18px}
.scope-note{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;margin-bottom:12px}
.scope-note strong{font-size:15px}
.scope-note span{font-size:12px;color:#64748b}
.document-filters{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.document-filters label{flex-direction:row;align-items:center;gap:8px;white-space:nowrap;font-size:12px;color:#475569}
.document-filters .document-search{flex:1;min-width:240px}
.document-search input{width:100%;background:#f8fafc}
.document-filters select{max-width:230px}
.document-filters input,.document-filters select{font-size:13px;padding:8px 10px;border-color:#e2e8f0;border-radius:7px}
.document-filters button{padding:8px 13px;font-size:13px}
.upload-box{padding:16px 12px;margin-bottom:18px;background:#f0fdfa;border-color:#99d5ce}
.upload-box p{font-size:12px;color:#64748b;margin:7px 0 12px}
.upload-box button{color:#0f766e;border-color:#99d5ce;font-weight:600}
.list-heading{gap:10px}
.list-heading h2{font-size:16px}
.list-heading button{font-size:12px;padding:5px 10px}
.list-count{font-size:12px;font-weight:500;border-radius:5px;background:#f1f5f9;color:#64748b;padding:2px 6px;margin-left:4px}
.list-order{margin:7px 0 10px;color:#94a3b8}
.list-empty{padding:24px 8px;text-align:center;font-size:13px}
.document-item{gap:7px;margin:10px 0;padding:13px;border-color:#e2e8f0;color:#334155}
.document-item:hover{border-color:#5bb8ab}
.document-item.selected{background:#f0fdfa;border-color:#0f766e;box-shadow:inset 3px 0 #0f766e}
.document-title{display:flex;align-items:start;justify-content:space-between;gap:8px;width:100%;overflow-wrap:anywhere;color:#0f172a}
.document-item .document-party{font-size:13px;font-weight:400;color:#475569}
.document-item small{display:flex;justify-content:space-between;gap:10px;width:100%;font-size:12px;color:#64748b}
.document-item small span{font-weight:400}
.document-item .status-tag{font-size:11px;font-weight:500;white-space:nowrap;border-radius:4px;padding:2px 6px;flex-shrink:0}
.status-tag.draft{background:#fff7ed;color:#b45309}
.status-tag.confirmed{background:#ccfbf1;color:#0f766e}
.status-tag.void{background:#f1f5f9;color:#64748b}
.empty{padding:36px 14px;max-width:680px;margin:0 auto}
.empty-symbol{display:flex;align-items:center;justify-content:center;width:54px;height:54px;margin:0 auto 18px;border-radius:14px;background:#f0fdfa;color:#0f766e;font-size:32px}
.empty h2{font-size:19px}
.empty p{margin:10px 0;color:#64748b}
.empty-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:26px 0 20px;text-align:left}
.empty-steps span{padding:15px 12px;border:1px solid #e2e8f0;border-radius:9px;font-size:13px;background:#f8fafc}
.empty-steps b{display:block;font-size:12px;color:#0f766e;margin-bottom:8px}
.empty small{color:#94a3b8}
.scan-card{padding:18px 20px;border-color:#99d5ce;background:linear-gradient(110deg,#f0fdfa,white 65%)}
.scan-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:15px}
.scan-heading h2{font-size:17px}
.scan-heading span{font-size:12px;color:#0f766e}
.scan-card label{font-size:12px;color:#64748b}
.scan-card input{font-size:16px;padding:12px;background:white}
.scan-card button{padding:13px 20px}
.scan-card p{font-size:12px;margin-top:10px;color:#64748b}
@media screen {
  .document-list{padding:20px}
  .detail-heading{align-items:flex-start}
  .detail-heading>div{min-width:0;overflow-wrap:anywhere}
  .detail-heading>button{flex-shrink:0}
  .document-fields{grid-template-columns:repeat(4,minmax(0,1fr));align-items:start}
  .document-fields label{min-width:0;gap:6px;font-size:13px}
  .document-fields input,.document-fields select{width:100%;height:38px;box-sizing:border-box;font-size:14px}
  .lines-scroll{margin-top:12px;border:1px solid #e2e8f0;border-radius:8px}
  .lines-scroll:focus-visible{outline:2px solid #99d5ce;outline-offset:2px}
  .lines{table-layout:fixed;min-width:1160px}
  .lines th,.lines td{padding:12px;vertical-align:top}
  .lines th:nth-child(1){width:20%}
  .lines th:nth-child(2),.lines th:nth-child(6){width:12%}
  .lines th:nth-child(3),.lines th:nth-child(8){width:10%}
  .lines th:nth-child(4){width:8%}
  .lines th:nth-child(5),.lines th:nth-child(7){width:14%}
  .lines input,.lines select{display:block;width:100%;height:38px;box-sizing:border-box;margin:0;font-size:13px}
  .lines td:nth-child(3) input{width:100%}
  .lines td>*+*{margin-top:8px}
  .lines .line-source{font-size:11px;color:#94a3b8;overflow-wrap:anywhere}
  .lines button,.detail-heading>button,.line-heading>button,.document-confirmation button{min-height:38px;font-size:13px}
  .document-confirmation{align-items:flex-end;gap:12px}
  .draft-review{margin:16px 0;padding:14px 16px;border:1px solid #cbd5e1;border-radius:8px;background:#f8fafc;font-size:13px}
  .draft-review strong{color:#334155}.draft-review ul{margin:8px 0;max-height:180px;overflow:auto;padding-left:20px;color:#9a3412}
  .draft-review p,.recognition-notes p,.line-help,.confirmation-help{font-size:13px;line-height:1.6;color:#64748b}
  .recognition-notes{background:#f8fafc;color:#64748b}.recognition-notes summary{cursor:pointer}
  .document-detail [aria-invalid="true"]{border-color:#f59e0b;background:#fffbeb}
  .document-fields.compact .optional-field,.lines.compact :is(th,td):nth-child(2),.lines.compact :is(th,td):nth-child(5),.lines.compact :is(th,td):nth-child(6),.lines.compact :is(th,td):nth-child(7){display:none}
  .lines.compact{min-width:600px}.lines.compact th:nth-child(1){width:35%}.lines.compact th:nth-child(3){width:25%}.lines.compact th:nth-child(4){width:20%}.lines.compact th:nth-child(8){width:20%}
  .confirmation-help{flex-basis:100%;margin:0}
}
@media(max-width:1100px){.handover-layout{grid-template-columns:290px minmax(0,1fr)}.document-filters .document-search{flex-basis:100%}.document-filters select{max-width:220px}}
@media screen and (max-width:1100px){.document-fields{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media screen and (max-width:720px){.document-list{padding:15px}.document-confirmation .check-label{flex-basis:100%}}
@media screen and (max-width:480px){.document-fields{grid-template-columns:1fr}.detail-heading{flex-wrap:wrap;gap:12px}}
@media(max-width:720px){.handover{padding:12px}.handover-header{flex-wrap:wrap;gap:12px}.handover-header h1{font-size:21px}.scope-badge{margin-left:0;max-width:100%}.handover-back{padding:8px 10px}.handover-layout{grid-template-columns:1fr}.document-filters{gap:12px}.document-filters label{flex:1}.document-filters select{flex:1;max-width:100%;width:100px}.document-list{max-height:430px}.empty-steps{grid-template-columns:1fr;gap:8px}.empty-steps span{display:flex;align-items:center;gap:12px;padding:12px}.empty-steps b{margin:0}.scan-heading{align-items:start;flex-direction:column}.document-detail{min-height:320px}}
@media print{.document-tools,.scope-badge{display:none!important}.handover{padding:0;background:white}.handover-layout{display:block}.document-detail{min-height:0}}
</style>
<style scoped>
.print-document{display:none}
@page material-handover{size:A4 landscape;margin:12mm}
@media print{.handover{page:material-handover}.print-document{display:block;font-size:10px;overflow-wrap:anywhere}.print-document h2{font-size:20px}.print-document p{color:#222}.print-qr{width:140px;height:140px;float:right;margin:0 0 12px 16px}.print-document table{table-layout:fixed;width:100%;clear:both}.print-document th,.print-document td{padding:6px;white-space:normal}.print-document small{color:#333}.print-document tr{break-inside:avoid}.document-detail>.fields,.lines,.detail-heading,.line-heading,.code-card{display:none!important}}
</style>

<style scoped>
@media print{.handover.original-print-active{page:auto;margin:0!important;padding:0!important;background:white!important}.handover.original-print-active>:not(.original-print-preview){display:none!important}}
</style>
