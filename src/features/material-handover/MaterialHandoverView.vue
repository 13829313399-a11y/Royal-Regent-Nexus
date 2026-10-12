<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import MaterialHandoverMonthly from './MaterialHandoverMonthly.vue'
const HandoverOriginalPrint = defineAsyncComponent(() => import('./HandoverOriginalPrint.vue').then(module => module.default))
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import axios from 'axios'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'
import { handoverApi, HANDOVER_FACTORY, type HandoverAction, type HandoverData, type HandoverDocument, type HandoverIssuer, type HandoverLine, type HandoverPosting, type HandoverSave, type HandoverSummary, type HandoverWorkspace, type HandoverLinkInput, type HandoverLinkAction } from '@/api/materialHandover'

const props = defineProps<{ external?: boolean }>()
const route = useRoute(), auth = useAuthStore()
const key = computed(() => props.external ? new URLSearchParams(route.hash.replace(/^#/, '')).get('key') || '' : '')
const api = computed(() => handoverApi(key.value))
const tab = ref<'documents' | 'scan' | 'issuers' | 'master' | 'monthly'>('documents')
const workspace = ref<HandoverWorkspace | null>(null), issuer = ref<HandoverIssuer | null>(null)
const summaries = ref<HandoverSummary[]>([]), issuers = ref<HandoverIssuer[]>([])
const moreAvailable = ref(false)
const selected = ref<HandoverDocument | null>(null), draft = ref<HandoverData | null>(null)
const error = ref(''), notice = ref(''), busy = ref(false), loading = ref(false), acknowledge = ref(false)
const sourceUrl = ref(''), qrUrl = ref(''), scanCode = ref(''), fileInput = ref<HTMLInputElement | null>(null)
const printBlob = shallowRef<Blob>(), printUrl = ref(''), printCorner = ref<'left'|'right'>('right')
const printPreparing = ref(false), printRendering = ref(false), printReady = ref(false), printWanted = ref(false), printToken = ref('')
const printMode = ref<'original'|'summary'>('original')
let printSequence = 0
const posting = ref<Record<string, { selected: boolean; quantity: string; batch_id: string; location_id: string; lot: string; roll_no: string }>>({})
const businessDate = ref(new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date()))
const issuerName = ref(''), issuerSupplier = ref(''), issuerKind = ref<HandoverIssuer['kind']>('SUPPLIER'), issuerDays = ref(365), newLink = ref('')
const bindSupplier = ref<Record<string,string>>({})
type Management = { kind: 'create' | 'renew' | 'bind' | 'revoke'; id: string; body: HandoverLinkInput | HandoverLinkAction }
const managementPending = ref<Management | null>(null)
const statusLabels = { DRAFT: '待核对', CONFIRMED: '已确认', VOID: '已作废' }
const progressLabels = { PENDING: '未收发', PARTIAL: '部分完成', COMPLETE: '全部完成' }
const dirty = computed(() => Boolean(selected.value?.status === 'DRAFT' && draft.value && JSON.stringify(draft.value) !== JSON.stringify(selected.value.data)))
const canEdit = computed(() => Boolean(props.external ? issuer.value : workspace.value?.can_operate))
const locked = computed(() => busy.value || loading.value || printPreparing.value || printRendering.value || Boolean(pending.value) || Boolean(managementPending.value))
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
function clear() { generation++; workspace.value = null; issuer.value = null; summaries.value = []; moreAvailable.value = false; selected.value = null; draft.value = null; posting.value = {}; issuers.value = []; pending.value = null; managementPending.value = null; bindSupplier.value = {}; failedFiles.value = []; newLink.value = ''; releaseUrls(); error.value = ''; notice.value = ''; busy.value = false; loading.value = false }
function showError(e: unknown) { if (axios.isAxiosError(e) && [401, 403].includes(e.response?.status || 0)) clear(); error.value = getApiErrorMessage(e) }
function scopeValid() { return props.external ? Boolean(key.value) : route.query.factory === HANDOVER_FACTORY }
async function reloadList() { const epoch = generation, client = api.value; const result = await client.list(); if (epoch === generation) { summaries.value = result.items; moreAvailable.value = result.items.length === result.limit } }
async function loadMore() { if (locked.value) return; const epoch = generation; loading.value = true; try { const result = await api.value.list(summaries.value.length); if (epoch === generation) { summaries.value.push(...result.items.filter(row => !summaries.value.some(old => old.id === row.id))); moreAvailable.value = result.items.length === result.limit } } catch (e) { if (epoch === generation) showError(e) } finally { if (epoch === generation) loading.value = false } }
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
    if (workspace.value?.can_manage) { const result = await client.issuers(); if (epoch === generation) issuers.value = result }
  } catch (e) { if (epoch === generation) showError(e) }
  finally { if (epoch === generation) loading.value = false }
}
watch(() => [props.external, key.value, route.query.factory, auth.currentUser?.id, auth.authorizationVersion], initialize, { immediate: true })
function accept(row: HandoverDocument) {
  selected.value = row; draft.value = clone(row.data); acknowledge.value = false
  posting.value = Object.fromEntries(row.data.lines.map(line => [line.id, { selected: false, quantity: row.progress[line.id]?.remaining || line.quantity, batch_id: '', location_id: '', lot: line.lot, roll_no: line.roll_no }]))
}
async function open(id: string, force = false) {
  if (locked.value || (dirty.value && !force)) { error.value = dirty.value ? '请先保存当前核对内容，再切换单据。' : '请先核对未确认的提交结果。'; return }
  const epoch = generation, client = api.value; loading.value = true; error.value = ''
  try { const row = await client.detail(id); if (epoch !== generation) return; releaseUrls(); accept(row) }
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
    pending.value = null; accept(result); notice.value = frozen.kind === 'post' ? '本次实际收发已保存，库存和剩余数量已更新。' : '单据已保存。'
    if (frozen.print_after) { try { await printConfirmed() } catch (e) { if (epoch === generation) error.value = `单据已确认保存；原单加码准备失败，可重试：${getApiErrorMessage(e)}` } }
    // Refresh failures must never change a completed write into a failed write.
    try { await reloadList(); if (!props.external) { const inventory = await client.workspace(); if (epoch === generation) workspace.value = inventory } }
    catch (e) { if (epoch === generation) error.value = `操作已保存；刷新失败，请重新打开单据核对：${getApiErrorMessage(e)}` }
  } catch (e) { if (epoch === generation) { if (!unsure(e)) pending.value = null; showError(e) } }
  finally { if (epoch === generation) busy.value = false }
}
function save() { if (selected.value && draft.value) void mutate({ kind: 'save', id: selected.value.id, body: { request_id: uuid(), expected_revision: selected.value.revision, data: clone(draft.value) } }) }
function confirm() { if (!selected.value || !draft.value) return; void mutate({ kind: 'confirm', id: selected.value.id, print_after: true, body: { request_id: uuid(), expected_revision: selected.value.revision, acknowledge_warnings: acknowledge.value, reason: '', data: clone(draft.value) } }) }
const voidReason = ref(''), showVoid = ref(false)
function voidDocument() { if (!selected.value) return; void mutate({ kind: 'void', id: selected.value.id, body: { request_id: uuid(), expected_revision: selected.value.revision, acknowledge_warnings: false, reason: voidReason.value } }); showVoid.value = false }
async function scan() {
  if (locked.value || dirty.value) return
  const epoch = generation; loading.value = true; error.value = ''
  try { const row = await api.value.scan(scanCode.value.trim()); if (epoch !== generation) return; releaseUrls(); accept(row); tab.value = 'scan'; const latest = await api.value.workspace(); if (epoch === generation) workspace.value = latest }
  catch (e) { if (epoch === generation) showError(e) }
  finally { if (epoch === generation) loading.value = false }
}
function post() {
  if (!selected.value || !workspace.value) return
  const lines = Object.entries(posting.value).filter(([, row]) => row.selected).map(([line_id, row]) => ({ line_id, quantity: row.quantity, batch_id: row.batch_id, location_id: row.location_id, lot: row.lot, roll_no: row.roll_no }))
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
async function refreshMasters() { const epoch=generation;loading.value=true;try{const data=await api.value.workspace();if(epoch===generation)workspace.value=data}catch(e){if(epoch===generation)showError(e)}finally{if(epoch===generation)loading.value=false} }
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
onBeforeUnmount(() => { generation++; releaseUrls(); window.removeEventListener('authorization-context-changed', refreshAuthorization); window.removeEventListener('beforeunload', preventUnload) })
</script>

<template>
  <main class="handover" :class="{ 'original-print-active': printMode==='original' && printReady }">
    <header class="handover-header">
      <div><p class="eyebrow">{{ external ? '专用制单入口' : '华康C · 布料仓' }}</p><h1>制单与扫码交接</h1><p>{{ external ? `${issuer?.name || '制单方'} · 上传原单，核对明细后生成交接二维码` : '统一整理送货与领料单据，按实际数量分批收发' }}</p></div>
      <RouterLink v-if="!external" to="/modules/pmc-warehouse/fabric-warehouse/inventory?factory=huakang-c">查看库存台账</RouterLink>
    </header>
    <nav class="handover-tabs"><button :class="{ active: tab === 'documents' }" @click="tab = 'documents'">{{ external ? '上传与打印' : '单据制单' }}</button><button v-if="!external" :class="{ active: tab === 'scan' }" @click="tab = 'scan'">扫码收发</button><button v-if="canMonthly" :class="{ active: tab === 'monthly' }" @click="tab = 'monthly'">本供应商数量记录</button><button v-if="!external" :class="{ active: tab === 'master' }" @click="tab = 'master'">基础资料</button><button v-if="!external && workspace?.can_manage" :class="{ active: tab === 'issuers' }" @click="tab = 'issuers'">制单方与链接</button><RouterLink v-if="!external" to="/modules/pmc-warehouse/fabric-warehouse/closing?factory=huakang-c&view=monthly">到仓库月结对账</RouterLink></nav>
    <p v-if="error" class="handover-message error" role="alert">{{ error }}</p><p v-if="notice" class="handover-message success" role="status">{{ notice }}</p>
    <p v-if="loading || busy" class="handover-message" role="status">{{ busy ? '正在处理，请稍候…' : '正在加载…' }}</p>
    <aside v-if="pending && !busy" class="handover-message warning"><p>提交结果尚未确认，已保留原提交内容。可重试原提交；请勿另建一笔重复收发。</p><button @click="mutate(pending)">重试原提交</button></aside>
    <aside v-if="managementPending && !busy" class="handover-message warning"><p>链接操作结果待确认，已保留原请求。</p><button @click="manage(managementPending)">重试原链接操作</button></aside>
    <p v-if="printPreparing" class="handover-message" role="status">正在按原单版式准备加码打印，请稍候…</p>
    <div v-if="printUrl" class="actions"><button :disabled="!printReady || locked" @click="reprintPrepared">打印已准备原单</button><a :href="printUrl" :download="`${selected?.data.source_no || '交接单'}-原单加码.pdf`">下载加码原单 PDF</a></div>
    <HandoverOriginalPrint v-if="printBlob" :file="printBlob" :token="printToken" @ready="originalReady" @failed="originalFailed" />
    <MaterialHandoverMonthly v-if="tab === 'monthly' && canMonthly" :client="api" :external="external" :suppliers="suppliers" />
    <section v-else-if="tab === 'master' && !external" class="card"><h2>共用仓库基础资料</h2><p>供应商使用固定编号，物料使用仓库编码与单位。每家供应商只需维护一次资料，上传送货单时自动带入身份。保存资料后刷新这里，再发放入口链接。</p><div class="actions"><RouterLink to="/modules/pmc-warehouse/fabric-warehouse/master?factory=huakang-c&view=partners">维护供应商资料</RouterLink><RouterLink to="/modules/pmc-warehouse/fabric-warehouse/master?factory=huakang-c&view=items">维护物料资料</RouterLink><RouterLink to="/modules/pmc-warehouse/fabric-warehouse/master?factory=huakang-c&view=units">维护单位</RouterLink><RouterLink to="/modules/pmc-warehouse/fabric-warehouse/master?factory=huakang-c&view=locations">维护仓位</RouterLink><button :disabled="locked" @click="refreshMasters">刷新基础资料</button></div><div class="table-scroll"><table><thead><tr><th>供应商编号</th><th>供应商名称</th><th>联系人 / 电话</th><th>状态</th></tr></thead><tbody><tr v-for="party in suppliers" :key="party.id"><td>{{ party.code }}</td><td>{{ party.name }}</td><td>{{ party.data.contact }} / {{ party.data.phone }}</td><td>{{ party.status==='ACTIVE'?'启用':party.status==='DRAFT'?'待完善':'停用' }}</td></tr></tbody></table></div><p v-if="!suppliers.length">请先维护并启用供应商，再发放供应商专用链接。</p></section>
    <section v-else-if="tab === 'issuers' && !external && workspace?.can_manage" class="card">
      <h2>发放专用制单链接</h2><p>每个链接只能查看自己的单据。确认库存仍由仓库人员完成，链接可以随时停用。</p>
      <form class="fields" @submit.prevent="createIssuer"><label>用途<select v-model="issuerKind" :disabled="locked"><option value="SUPPLIER">供应商送货</option><option value="REQUESTOR">裁床 / 车间领料</option></select></label><label v-if="issuerKind==='SUPPLIER'">供应商基础资料<select v-model="issuerSupplier" required :disabled="locked" aria-label="入口供应商"><option value="">请选择已启用供应商</option><option v-for="party in activeSuppliers" :key="party.id" :value="party.id">{{ party.code }} · {{ party.name }}</option></select></label><label v-else>领用方名称<input v-model="issuerName" required maxlength="255" :disabled="locked" /></label><label>有效天数<input v-model.number="issuerDays" type="number" min="1" max="365" :disabled="locked" /></label><button :disabled="locked">生成专用链接</button></form>
      <label v-if="newLink" class="link-result">请保存并发给对应制单方<input :value="newLink" readonly aria-label="专用制单链接" /></label>
      <p>更新链接会让旧密钥失效，原单据和月度记录仍归同一供应商。旧入口必须先关联基础资料，不能凭名称自动合并。</p><div class="table-scroll"><table><thead><tr><th>制单方 / 编号</th><th>用途</th><th>有效期</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="value in issuers" :key="value.id"><td>{{ value.name }}<small>{{ value.supplier_code || (value.kind==='SUPPLIER'?'基础资料待关联':'领用方') }}</small></td><td>{{ value.kind === 'SUPPLIER' ? '送货' : '领料' }}</td><td>{{ value.expires_at.slice(0, 10) }}</td><td>{{ value.active ? '可用' : '已停用' }}</td><td><template v-if="value.kind==='SUPPLIER' && !value.supplier_id"><select v-model="bindSupplier[value.id]" :disabled="locked" :aria-label="`${value.name}关联供应商`"><option value="">选择同名基础资料</option><option v-for="party in activeSuppliers.filter(p=>p.name===value.name)" :key="party.id" :value="party.id">{{ party.code }} · {{ party.name }}</option></select><button :disabled="locked || !bindSupplier[value.id]" @click="linkAction(value,'bind')">关联原入口</button></template><button v-else :disabled="locked" @click="linkAction(value,'renew')">续期并更新链接</button><button v-if="value.active" :disabled="locked" @click="linkAction(value,'revoke')">停用链接</button></td></tr></tbody></table></div>
    </section>
    <template v-else>
      <section v-if="tab === 'scan' && !external" class="card scan-card"><form @submit.prevent="scan"><label>扫描单据二维码<input v-model="scanCode" placeholder="将光标放在这里，扫码后按回车" autocomplete="off" aria-label="扫描单据二维码" :disabled="locked" /></label><button :disabled="locked || loading || !scanCode.trim()">打开交接单</button></form><p>扫描只打开单据；勾选实际收发的物料并确认后，才会更新库存。</p></section>
      <div class="handover-layout">
        <aside class="card document-list">
          <div v-if="tab === 'documents'" class="upload-box" @dragover.prevent @drop.prevent="dropped"><strong>拖入自己的原单</strong><p>Excel、Word DOCX、PDF 或照片<br />每份不超过 20 MB，PDF 最多 20 页</p><input ref="fileInput" type="file" multiple accept=".xls,.xlsx,.docx,.pdf,.png,.jpg,.jpeg,.webp" class="sr-only" @change="picked" /><button :disabled="!canEdit || locked || loading" @click="fileInput?.click()">选择文件并识别</button></div>
          <div v-if="failedFiles.length" class="handover-message error"><p>{{ failedFiles.length }} 份文件未完成，原文件已保留。</p><button :disabled="locked" @click="upload([...failedFiles])">重试未完成文件</button></div>
          <div class="list-heading"><h2>最近单据</h2><button :disabled="locked || dirty" @click="initialize">刷新</button></div>
          <p v-if="!summaries.length && !loading">尚无单据，上传原单后开始核对。</p>
          <button v-for="row in summaries" :key="row.id" class="document-item" :class="{ selected: selected?.id === row.id }" :disabled="locked" @click="open(row.id)"><span>{{ row.data.source_no || '原单号待补' }}<small>{{ statusLabels[row.status] }} · {{ row.data.kind === 'DELIVERY' ? '送货' : '领料' }} · {{ row.line_count }} 项</small></span><small>{{ row.data.counterparty || '制单方待核对' }}</small></button>
          <button v-if="moreAvailable" :disabled="locked" @click="loadMore">加载更早单据</button>
        </aside>
        <section class="card document-detail">
          <div v-if="!selected" class="empty"><h2>{{ tab === 'scan' ? '扫描后打开待收发明细' : '原单与统一明细保留在一起' }}</h2><p>数量、单位和手写修改需要核对；不同供应商可以使用不同版式。</p></div>
          <template v-else-if="draft">
            <section class="print-document"><img v-if="qrUrl && selected.status==='CONFIRMED'" :src="qrUrl" alt="交接单二维码" class="print-qr" /><h2>{{ selected.data.kind==='DELIVERY'?'供应商送货交接单':'领料交接单' }}</h2><p>{{ selected.status==='CONFIRMED'?'已确认交接单':'草稿 · 仅供校对' }} · {{ selected.code }}</p><p>{{ selected.data.counterparty }} · 原单号 {{ selected.data.source_no }} · {{ selected.data.document_date }}</p><p>合同 {{ selected.data.contract_no || '未注明' }} · 生产单 {{ selected.data.production_no || '未注明' }} · 货号 {{ selected.data.product_no || '未注明' }}</p><table><thead><tr><th>物料编码</th><th>名称 / 规格 / 颜色</th><th>原单数量</th><th>缸号 / 卷号</th><th>参考单价 / 计价单位 / 币种</th><th>原单依据 / 生产关联</th></tr></thead><tbody><tr v-for="line in selected.data.lines" :key="line.id"><td>{{ line.item_code }}</td><td>{{ line.item_name }}<small>{{ line.specification }} {{ line.color }}</small></td><td>{{ line.quantity }} {{ line.unit }}</td><td>{{ line.lot }} / {{ line.roll_no }}<small>{{ line.roll_quantities }}</small></td><td>{{ line.unit_price || '未记录' }} / {{ line.price_unit || '未注明' }} / {{ line.currency || '未注明' }}</td><td>{{ line.price_note }}<small>{{ line.production_no }} {{ line.note }}</small></td></tr></tbody></table><p>数量以仓库实际点收 / 实发记录为准。参考单价是原单依据，付款金额需另行核对。</p></section>
            <div class="detail-heading"><div><p class="eyebrow">{{ statusLabels[selected.status] }} · {{ progressLabels[selected.processing_status] }}</p><h2>{{ selected.data.source_no || selected.file_name }}</h2><p>{{ selected.file_name }} · {{ selected.data.counterparty || '制单方待补' }}</p></div><button @click="preview('source')">查看原件</button></div>
            <iframe v-if="sourceUrl && selected.file_name.toLowerCase().endsWith('.pdf')" :src="sourceUrl" title="单据原件" class="source-preview" />
            <img v-else-if="sourceUrl && /\.(png|jpe?g|webp)$/i.test(selected.file_name)" :src="sourceUrl" alt="单据原件" class="source-preview" />
            <a v-else-if="sourceUrl" :href="sourceUrl" :download="selected.file_name">下载原始文档核对</a>
            <details v-if="selected.warnings.length" class="review-warning" open><summary>请核对 {{ selected.warnings.length }} 项识别提示</summary><ul><li v-for="text in selected.warnings" :key="text">{{ text }}</li></ul></details>
            <fieldset class="fields" :disabled="selected.status !== 'DRAFT' || !canEdit || locked"><label>单据用途<select v-model="draft.kind" :disabled="external"><option value="DELIVERY">送货单</option><option value="ISSUE">领料申请 / 发料依据</option></select></label><label>原单号<input v-model="draft.source_no" maxlength="128" aria-label="原单号" /></label><label>单据日期<input v-model="draft.document_date" type="date" aria-label="单据日期" /></label><label v-if="!external && draft.kind==='DELIVERY'">供应商基础资料<select v-model="draft.supplier_id" @change="chooseSupplier" aria-label="制单供应商"><option value="">请选择已启用供应商</option><option v-for="party in activeSuppliers" :key="party.id" :value="party.id">{{ party.code }} · {{ party.name }}</option></select></label><label>供应商 / 领用方<input v-model="draft.counterparty" :readonly="external || draft.kind==='DELIVERY'" maxlength="255" aria-label="制单方" /></label><label>合同号<input v-model="draft.contract_no" maxlength="128" /></label><label>放产 / 生产单号<input v-model="draft.production_no" maxlength="128" /></label><label>货号<input v-model="draft.product_no" maxlength="128" /></label><label>说明<input v-model="draft.note" maxlength="1000" /></label></fieldset>
            <div class="line-heading"><h3>统一物料明细</h3><button v-if="selected.status === 'DRAFT'" :disabled="!canEdit || locked || draft.lines.length >= 200" @click="addLine">添加明细</button></div>
            <div class="table-scroll"><table class="lines"><thead><tr><th>物料编码 / 名称</th><th>规格 / 颜色</th><th>单据数量 / 单位</th><th>类别</th><th>单价依据（选填）</th><th>缸号 / 卷号</th><th>关联 / 说明</th><th>进度 / 操作</th></tr></thead><tbody><tr v-for="(line, index) in draft.lines" :key="line.id"><td><small>{{ line.source_line || `补录第 ${index + 1} 行` }}</small><input v-model="line.item_code" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" :aria-label="`第${index+1}行物料编码`" placeholder="物料编码" /><input v-model="line.item_name" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" :aria-label="`第${index+1}行物料名称`" placeholder="物料名称" /></td><td><input v-model="line.specification" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="规格" /><input v-model="line.color" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="颜色" /></td><td><input v-model="line.quantity" inputmode="decimal" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" :aria-label="`第${index+1}行单据数量`" /><input v-model="line.unit" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" :aria-label="`第${index+1}行单位`" placeholder="单位" /></td><td><select v-model="line.material_category" :disabled="selected.status !== 'DRAFT' || !canEdit || locked"><option value="FABRIC">布料</option><option value="ACCESSORY">辅料</option><option value="THREAD">线</option></select></td><td><input v-model="line.unit_price" inputmode="decimal" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" :aria-label="`第${index+1}行参考单价`" placeholder="单价，空白为未记录" /><input v-model="line.price_unit" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="计价单位" /><select v-model="line.currency" :disabled="selected.status !== 'DRAFT' || !canEdit || locked"><option value="">币种未注明</option><option value="CNY">CNY 人民币</option><option value="HKD">HKD 港币</option><option value="USD">USD 美元</option><option value="EUR">EUR 欧元</option></select><input v-model="line.price_note" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="报价 / 含税口径等原单依据" /></td><td><input v-model="line.lot" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="缸号" /><input v-model="line.roll_no" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="卷号" /><small v-if="line.roll_quantities">逐卷：{{ line.roll_quantities }}</small></td><td><input v-model="line.production_no" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="放产 / 生产单号" /><input v-model="line.note" :disabled="selected.status !== 'DRAFT' || !canEdit || locked" placeholder="说明" /></td><td><template v-if="selected.status === 'CONFIRMED'"><p>已{{ selected.data.kind === 'DELIVERY' ? '收' : '发' }} {{ selected.progress[line.id]?.processed }} {{ line.unit }}</p><small>未完成 {{ selected.progress[line.id]?.remaining }} {{ line.unit }}</small></template><button v-else-if="selected.status === 'DRAFT'" :disabled="!canEdit || locked" @click="draft.lines.splice(index, 1)">移除此行</button></td></tr></tbody></table></div>
            <footer v-if="selected.status === 'DRAFT'" class="actions"><label>原单二维码位置<select v-model="printCorner" :disabled="locked" aria-label="原单二维码位置"><option value="right">右上角</option><option value="left">左上角</option></select></label><label v-if="selected.warnings.length" class="check-label"><input v-model="acknowledge" type="checkbox" :disabled="locked" />已对照原件核对上述提示、数量和单位</label><button :disabled="!canEdit || locked || !dirty" @click="save">保存核对内容</button><button class="primary" :disabled="!canEdit || locked || !draft.lines.length || (selected.warnings.length > 0 && !acknowledge)" @click="confirm">确认并打印原单</button></footer>
            <section v-if="selected.status === 'CONFIRMED'" class="code-card"><div><h3>交接二维码</h3><p>原单纸面保留供应商信息与物料表，二维码放在新增顶部空白区域，不盖住原内容。可重复打印、分批使用；每次扫码仍需核对本次实物。</p><code>{{ selected.code }}</code><div class="actions"><button @click="preview('qr')">显示二维码</button><label>原单二维码位置<select v-model="printCorner" :disabled="locked" aria-label="原单二维码位置"><option value="right">右上角</option><option value="left">左上角</option></select></label><button :disabled="locked" @click="printConfirmed">原单加码打印</button><button :disabled="locked" @click="print">打印统一明细（备用）</button><a v-if="qrUrl" :href="qrUrl" :download="selected.id + '.svg'">下载二维码</a></div></div><img v-if="qrUrl" :src="qrUrl" alt="交接二维码" class="qr-image" /></section>
            <section v-if="selected.status === 'CONFIRMED' && !external && workspace?.can_operate" class="posting-card"><div class="line-heading"><h3>本次实际{{ selected.data.kind === 'DELIVERY' ? '收料入库' : '发料出库' }}</h3><label>实际日期<input v-model="businessDate" type="date" :disabled="locked" /></label></div><p>未到 / 未发的明细不勾选；同一行可以分批办理，数量与单位不会自动换算。扫码实收记入库存，采购来源追货进度仍在原收料页面管理。</p><fieldset :disabled="locked"><div v-for="line in selected.data.lines" :key="line.id" class="posting-row"><label class="check-label"><input v-model="posting[line.id]!.selected" type="checkbox" :disabled="Number(selected.progress[line.id]?.remaining) <= 0" />{{ line.item_name }} · {{ line.item_code }}</label><label>本次数量<input v-model="posting[line.id]!.quantity" inputmode="decimal" :aria-label="`本次${line.item_code}数量`" /><small>{{ line.unit }} · 尚余 {{ selected.progress[line.id]?.remaining }}</small></label><template v-if="selected.data.kind === 'DELIVERY'"><label>入库仓位<select v-model="posting[line.id]!.location_id"><option value="">请选择</option><option v-for="place in workspace.inventory.locations?.filter(p => p.status === 'ACTIVE')" :key="place.id" :value="place.id">{{ place.label }}</option></select></label><label>本次缸号<input v-model="posting[line.id]!.lot" /></label><label>卷号<input v-model="posting[line.id]!.roll_no" /></label></template><label v-else>实际出库批次<select v-model="posting[line.id]!.batch_id"><option value="">请选择批次与仓位</option><option v-for="batch in batches(line)" :key="batch.id" :value="batch.id">{{ batch.location }} · {{ batch.lot || '无缸号' }} / {{ batch.roll_no || '无卷号' }} · 可发 {{ batch.available_quantity }} {{ batch.unit }}</option></select></label></div></fieldset><button class="primary" :disabled="locked" @click="post">确认本次实物收发</button></section>
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
.print-document{display:none}
@page material-handover{size:A4 landscape;margin:12mm}
@media print{.handover{page:material-handover}.print-document{display:block;font-size:10px;overflow-wrap:anywhere}.print-document h2{font-size:20px}.print-document p{color:#222}.print-qr{width:140px;height:140px;float:right;margin:0 0 12px 16px}.print-document table{table-layout:fixed;width:100%;clear:both}.print-document th,.print-document td{padding:6px;white-space:normal}.print-document small{color:#333}.print-document tr{break-inside:avoid}.document-detail>.fields,.lines,.detail-heading,.line-heading,.code-card{display:none!important}}
</style>

<style scoped>
@media print{.handover.original-print-active{page:auto;margin:0!important;padding:0!important;background:white!important}.handover.original-print-active>:not(.original-print-preview){display:none!important}}
</style>
