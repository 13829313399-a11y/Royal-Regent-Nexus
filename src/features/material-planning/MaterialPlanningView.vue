<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/common/PageHeader.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import TrialResults from './TrialResults.vue'
import { trialApi as api, blankTrial, defaultAttributes, defaultLossExemptions, statusText, type Access, type FrozenBom, type TrialDraft, type TrialInput, type TrialResult, type OrderBasis } from './api'

const auth = useAuthStore(), route = useRoute()
const access = ref<Access | null>(null), boms = ref<FrozenBom[]>([]), drafts = ref<TrialDraft[]>([])
const selected = ref<TrialDraft | null>(null), editing = ref(false), inputs = ref(blankTrial()), reason = ref('业务用量试算')
const result = ref<TrialResult | null>(null), histories = ref<TrialDraft[]>([]), dirty = ref(false)
const loading = ref(false), busy = ref(false), previewBusy = ref(false), error = ref(''), notice = ref('')
const pending = ref<{ path: string; body: unknown } | null>(null)
const orderQuery = ref(''), orderRows = ref<OrderBasis[]>([]), orderBasis = ref<OrderBasis | null>(null)
const orderBusy = ref(false), orderSearched = ref(false), moreOrders = ref(false)
const workflowReason = ref('核对需求及工序物料期')
let orderSequence = 0
let epoch = 0, loadSequence = 0, previewSequence = 0, historySequence = 0, replacing = false
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T
const ready = computed(() => route.query.factory === 'huakang-c' && access.value?.enabled && access.value.schema_ready)
const locked = computed(() => loading.value || busy.value || !!pending.value)
const isDraft = computed(() => !selected.value || selected.value.status === 'DRAFT_DATA_PENDING')
const writable = computed(() => ready.value && access.value?.can_write && isDraft.value)
const currentBom = computed(() => boms.value.find(b => b.id === inputs.value.bom_id && b.version === inputs.value.bom_version))
const displayBom = computed(() => currentBom.value || (selected.value?.bom.id === inputs.value.bom_id && selected.value.bom.version === inputs.value.bom_version ? selected.value.bom : null))
const engineeringAttributes = computed(() => displayBom.value ? defaultAttributes(displayBom.value) : {})
const stale = computed(() => !!inputs.value.bom_id && !currentBom.value)
const bomKey = computed(() => inputs.value.bom_id ? `${inputs.value.bom_id}:${inputs.value.bom_version}` : '')

function replaceInputs(value: TrialInput) {
  replacing = true; inputs.value = clone(value); replacing = false
  dirty.value = false; result.value = null; previewSequence++; previewBusy.value = false; historySequence++; histories.value = []
  orderSequence++; orderRows.value = []; orderBasis.value = null; orderQuery.value = ''; orderBusy.value = false; orderSearched.value = false; moreOrders.value = false
}
function clear() {
  access.value = null; boms.value = []; drafts.value = []; selected.value = null; editing.value = false
  replaceInputs(blankTrial()); pending.value = null; busy.value = false; loading.value = false; notice.value = ''; error.value = ''
  replacing = true; reason.value = '业务用量试算'; replacing = false
}
function failure(cause: unknown) {
  const e = cause as { response?: { status?: number; data?: { detail?: unknown } }; message?: string }
  if ([401, 403].includes(e.response?.status || 0)) { epoch++; clear() }
  error.value = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : e.response?.data?.detail ? '请核对必填项、数量和损耗率。' : e.message || '读取失败，请重试。'
}
async function load() {
  if (route.query.factory !== 'huakang-c') { clear(); return }
  const token = epoch, request = ++loadSequence
  loading.value = true; error.value = ''
  try {
    const a = await api.access(); if (token !== epoch || request !== loadSequence) return
    if (access.value?.can_read_orders && !a.can_read_orders) {
      selected.value = null; editing.value = false; replaceInputs(blankTrial())
      drafts.value = drafts.value.filter(d => !d.inputs.order)
    }
    access.value = a
    if (a.enabled && a.schema_ready) {
      const w = await api.workspace(); if (token !== epoch || request !== loadSequence) return
      boms.value = w.boms; drafts.value = w.drafts
      if (selected.value && !dirty.value) {
        const fresh = w.drafts.find(d => d.id === selected.value?.id)
        if (fresh && fresh.version > selected.value.version) { selected.value = fresh; replaceInputs(draftInputs(fresh)); result.value = fresh.result; orderBasis.value = fresh.result.order_basis || null }
      }
    } else { boms.value = []; drafts.value = []; selected.value = null; editing.value = false; replaceInputs(blankTrial()) }
  } catch (e) { if (token === epoch && request === loadSequence) failure(e) }
  finally { if (token === epoch && request === loadSequence) loading.value = false }
}
function discard() { return !locked.value && (!dirty.value || window.confirm('有未保存的试算内容，是否放弃并继续？')) }
function draftInputs(draft: TrialDraft): TrialInput {
  return { ...draft.inputs, material_attributes: { ...defaultAttributes(draft.bom), ...draft.inputs.material_attributes }, loss_exemptions: { ...Object.fromEntries(draft.bom.data.nodes.filter(n => n.parent).map(n => [n.key, n.exempt_loss])), ...draft.inputs.loss_exemptions } }
}
function open(draft?: TrialDraft) {
  if (draft?.inputs.order && !access.value?.can_read_orders) { error.value = '查看关联草稿需要客户订单查看权限。'; return }
  if (!discard()) return
  selected.value = draft || null; replaceInputs(draft ? draftInputs(draft) : blankTrial())
  replacing = true; reason.value = draft?.reason || '业务用量试算'; replacing = false
  result.value = draft?.result || null; editing.value = true; notice.value = ''; error.value = ''
  orderBasis.value = draft?.result.order_basis || null
}
async function searchOrders() {
  if (locked.value || !writable.value || !access.value?.can_read_orders || !access.value.order_schema_ready) return
  const token = epoch, request = ++orderSequence, query = orderQuery.value
  orderBusy.value = true; orderRows.value = []; orderSearched.value = false; error.value = ''
  try {
    const found = await api.orders(query)
    if (token !== epoch || request !== orderSequence || query !== orderQuery.value) return
    orderRows.value = found.items; moreOrders.value = found.has_more; orderSearched.value = true
  } catch (e) { if (token === epoch && request === orderSequence) failure(e) }
  finally { if (token === epoch && request === orderSequence) orderBusy.value = false }
}
function chooseOrder(row: OrderBasis | null) {
  inputs.value.order = row ? { line_id: row.line_id, revision: row.revision } : null
  orderBasis.value = row
}
function chooseBom(event: Event) {
  const control = event.target as HTMLSelectElement, b = boms.value.find(b => `${b.id}:${b.version}` === control.value)
  if (!b) { control.value = bomKey.value; return }
  if (bomKey.value && control.value !== bomKey.value && !window.confirm('更换 BOM 将重置免损项及本次物料属性，请重新核对用料。是否继续？')) { control.value = bomKey.value; return }
  inputs.value = { ...inputs.value, bom_id: b.id, bom_version: b.version,
    material_attributes: defaultAttributes(b),
    loss_exemptions: defaultLossExemptions(b) }
}
function payload() { return { factory_id: 'huakang-c', operation_id: crypto.randomUUID(), expected_version: selected.value?.version || 0, reason: reason.value, data: clone(inputs.value) } }
async function preview() {
  if (locked.value || stale.value) return
  const token = epoch, request = ++previewSequence; previewBusy.value = true; error.value = ''
  try { const value = await api.preview(payload()); if (token === epoch && request === previewSequence) result.value = value }
  catch (e) { if (token === epoch && request === previewSequence) failure(e) }
  finally { if (token === epoch && request === previewSequence) previewBusy.value = false }
}
async function save() {
  if (!writable.value || locked.value || stale.value) return
  pending.value = { path: selected.value ? `/drafts/${selected.value.id}` : '/drafts', body: payload() }
  await retry()
}
async function workflow(action: 'submit' | 'self-review' | 'reopen') {
  if (!selected.value || locked.value || dirty.value || !workflowReason.value.trim()) return
  const permitted = action === 'self-review' ? access.value?.can_self_review : access.value?.can_submit
  if (!permitted) return
  pending.value = { path: `/drafts/${selected.value.id}/${action}`, body: { factory_id: 'huakang-c', operation_id: crypto.randomUUID(), expected_version: selected.value.version, reason: workflowReason.value } }
  await retry()
}
async function retry() {
  const request = pending.value; if (!request || busy.value) return
  const token = epoch; busy.value = true; error.value = ''
  try {
    const saved = await api.save(request.path, request.body); if (token !== epoch) return
    pending.value = null; selected.value = saved; replaceInputs(draftInputs(saved)); result.value = saved.result
    orderBasis.value = saved.result.order_basis || null
    notice.value = `${statusText(saved.status)}：已保存，仍待资料核实。`; await load()
  } catch (e) {
    if (token !== epoch) return
    const status = (e as { response?: { status?: number } }).response?.status
    if (status && status < 500) pending.value = null
    failure(e)
  } finally { if (token === epoch) busy.value = false }
}
async function history(id: string) {
  const token = epoch, request = ++historySequence; histories.value = []
  try { const h = await api.history(id); if (token === epoch && request === historySequence) histories.value = h.items }
  catch (e) { if (token === epoch && request === historySequence) failure(e) }
}
watch([inputs, reason], () => { if (!replacing) { dirty.value = true; result.value = null; previewSequence++; previewBusy.value = false } }, { deep: true, flush: 'sync' })
watch(orderQuery, () => { orderSequence++; orderRows.value = []; orderSearched.value = false; orderBusy.value = false })
watch(() => [route.query.factory, auth.sessionVersion, auth.authorizationVersion], () => {
  epoch++; clear(); if (route.query.factory === 'huakang-c') void load()
}, { immediate: true })
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value || pending.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
onBeforeRouteLeave(discard); onBeforeRouteUpdate(discard)
onBeforeUnmount(() => { epoch++; window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <main class="material-trial space-y-5">
    <PageHeader title="需求试算草稿" description="按有效工程 BOM 核对用料和损耗，保留每次试算依据。">
      <template #actions><Button variant="outline" :disabled="locked" @click="load">刷新依据与草稿</Button></template>
    </PageHeader>
    <p v-if="route.query.factory !== 'huakang-c'" role="status">请在华康 C 业务部打开需求试算。</p>
    <p v-if="loading" role="status">正在读取试算资料…</p>
    <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-red-800">{{ error }}</p>
    <p v-if="notice" role="status" class="text-teal-800">{{ notice }}</p>
    <SectionPanel v-if="access && !ready" title="需求试算尚未开放" subtitle="请管理员完成部署与启用，现有草稿不会变成采购单。" />
    <div v-if="pending && !busy" class="rounded-lg border p-3"><p>上次保存结果尚未确认，请沿原请求重试。</p><Button @click="retry">核对并重试原请求</Button></div>
    <template v-if="ready">
      <SectionPanel title="我的试算草稿" subtitle="仅显示本人草稿。库存、在途、物料期及订单绑定核实后，再进入后续业务流程。">
        <template #action><Button :disabled="!ready || !access?.can_write || locked" @click="open()">新建试算</Button></template>
        <p v-if="!drafts.length">暂无试算草稿。</p>
        <div v-else class="overflow-x-auto"><table><thead><tr><th>名称／货号</th><th>试算数量</th><th>BOM／草稿版本</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="d in drafts" :key="d.id"><td>{{ d.inputs.title }} ／ {{ d.bom.data.item_no }}</td><td>{{ d.inputs.quantity }} {{ d.result.finished_unit }}</td><td>v{{ d.bom.version }} ／ v{{ d.version }}</td><td>{{ statusText(d.status) }}</td><td><Button size="sm" variant="outline" :disabled="locked" @click="open(d)">查看／编辑</Button><Button size="sm" variant="ghost" :disabled="locked" @click="history(d.id)">历史</Button></td></tr></tbody></table></div>
      </SectionPanel>
      <SectionPanel v-if="editing" title="试算依据、物料属性与免损设置">
        <p v-if="!boms.length" class="mb-3 text-amber-800">暂无当前有效 BOM，请工程先审核。</p>
        <p v-if="stale" role="status" class="mb-3 text-amber-800">此草稿依据已不是当前有效版本。历史结果保留；请刷新并选择当前 BOM，核对物料属性和免损项后再保存。</p>
        <form @submit.prevent="save">
          <fieldset :disabled="locked || !writable">
            <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <label>试算名称<input v-model="inputs.title" required maxlength="128" /></label>
              <label>有效 BOM<select :value="bomKey" required @change="chooseBom"><option value="">请选择工程 BOM</option><option v-if="stale && displayBom" :value="bomKey">{{ displayBom.data.item_no }} · 历史 v{{ displayBom.version }}</option><option v-for="b in boms" :key="`${b.id}:${b.version}`" :value="`${b.id}:${b.version}`">{{ b.data.item_no }} {{ b.data.name }} · v{{ b.version }}</option></select></label>
              <label>试算数量（{{ displayBom?.data.nodes.find(n => !n.parent)?.unit || '成品单位' }}）<input v-model="inputs.quantity" aria-label="试算数量" inputmode="decimal" required /></label>
              <label>统一损耗率（%）<input v-model="inputs.loss_percent" inputmode="decimal" required /></label>
              <label>试算依据<input v-model="inputs.reference" maxlength="500" placeholder="补充说明；订单请在下方选择关联" /></label>
              <label>保存说明<input v-model="reason" required maxlength="500" /></label>
            </div>
            <div class="my-4 space-y-3 rounded-md border border-slate-200 p-3">
              <p class="font-medium">关联客户订单（可选）</p>
              <p class="text-sm text-slate-600">关联后按订单中心的货号、数量及版本核对，试算数量仍由业务填写。保存草稿不会下发订单、占用数量或生成采购单。</p>
              <p v-if="orderBasis">已选：{{ orderBasis.customer_name }} ／ {{ orderBasis.reference_no }} ／ {{ orderBasis.product_no }} · 订单数量 {{ orderBasis.quantity }} · 依据版本 {{ orderBasis.revision }}</p>
              <p v-else-if="inputs.order">已关联订单，依据待重新查询核对。</p>
              <template v-if="access?.can_read_orders && access.order_schema_ready">
                <div class="flex flex-wrap items-end gap-2"><label class="min-w-0 flex-1">查找订单<input v-model="orderQuery" maxlength="255" @keydown.enter.prevent="searchOrders" placeholder="订单号、货号或客户名称" /></label><Button type="button" variant="outline" :disabled="orderBusy" @click="searchOrders">{{ orderBusy ? '正在查询…' : '查询订单' }}</Button><Button v-if="inputs.order" type="button" variant="ghost" @click="chooseOrder(null)">解除关联</Button></div>
                <p v-if="orderSearched && !orderRows.length">未找到可关联的本厂订单。</p>
                <p v-if="orderSearched && moreOrders" class="text-sm">仅显示前 50 条，请补充查询条件。</p>
                <div v-if="orderRows.length" class="overflow-x-auto"><table><thead><tr><th>客户／订单号</th><th>货号</th><th>订单数量</th><th>依据版本</th><th>操作</th></tr></thead><tbody><tr v-for="o in orderRows" :key="o.line_id"><td>{{ o.customer_name }} ／ {{ o.reference_no }}</td><td>{{ o.product_no }}</td><td>{{ o.quantity }}</td><td>{{ o.revision }}</td><td><Button type="button" size="sm" variant="outline" @click="chooseOrder(o)">关联此订单</Button></td></tr></tbody></table></div>
              </template>
              <p v-else class="text-sm text-amber-800">{{ access?.can_read_orders ? '订单数据结构尚未部署，暂不能关联。' : '关联订单需要客户订单查看权限。' }}</p>
            </div>
            <p v-if="displayBom" class="mt-3">货号：{{ displayBom.data.item_no }} · 规格：{{ displayBom.data.specification || '未填写' }}</p>
            <div v-if="displayBom" class="my-4 overflow-x-auto"><table><caption>物料属性与免损项（默认沿用工程设置，逐行确认）</caption><thead><tr><th>工序</th><th>物料</th><th>工程默认属性</th><th>本次物料属性</th><th>工程默认免损</th><th>本次不计损耗</th></tr></thead><tbody><tr v-for="n in displayBom.data.nodes.filter(n => n.parent)" :key="n.key"><td>{{ n.process }}</td><td>{{ n.source_code }} {{ n.source_name }}</td><td>{{ engineeringAttributes[n.key] || '待核对' }}</td><td><select v-if="['自制', '委外'].includes(engineeringAttributes[n.key] || '')" v-model="inputs.material_attributes[n.key]" :aria-label="`${n.source_name || n.source_code} ${n.process} 本次物料属性`"><option value="自制">自制</option><option value="委外">委外</option></select><span v-else>{{ engineeringAttributes[n.key] || '待核对' }}</span></td><td>{{ n.exempt_loss ? '免损' : '计损耗' }}</td><td><input v-model="inputs.loss_exemptions[n.key]" type="checkbox" :disabled="engineeringAttributes[n.key] === '客供'" :aria-label="`${n.source_name || n.source_code} ${n.process} 不计损耗`" /><template v-if="engineeringAttributes[n.key] === '客供'"><small>客供必须计损耗</small><Button v-if="inputs.loss_exemptions[n.key]" type="button" variant="outline" size="sm" :aria-label="`${n.source_name || n.source_code} ${n.process} 改为计损耗`" @click="inputs.loss_exemptions[n.key] = false">改为计损耗</Button></template></td></tr></tbody></table></div>
            <div class="mt-4 flex flex-wrap gap-2"><Button type="button" variant="outline" :disabled="previewBusy || !currentBom" @click="preview">{{ previewBusy ? '正在试算…' : '计算用料' }}</Button><Button type="submit" :disabled="!currentBom">保存试算草稿</Button></div>
          </fieldset>
        </form>
      </SectionPanel>
      <SectionPanel v-if="selected && editing" title="物料期与业务自审">
        <p>{{ statusText(selected.status) }} · 需求版本 {{ selected.version }}</p>
        <p class="my-2 text-sm text-slate-600">自审确认本次用料和工序日期；库存、在途未核实，仍不能正式放单。修改已提交需求须先退回草稿，日期需采购重新确认。</p>
        <ul v-if="Object.keys(selected.process_dates || {}).length" class="my-3"><li v-for="(date, process) in selected.process_dates" :key="process">{{ process }}：{{ date }}</li></ul>
        <p v-else class="my-2">采购尚未填写工序物料期。</p>
        <p v-if="selected.date_actor" class="text-sm">填期：{{ selected.date_actor.name }} · {{ selected.date_actor.at }}</p>
        <p v-if="selected.reviewed_by" class="text-sm">业务自审：{{ selected.reviewed_by.name }} · {{ selected.reviewed_by.at }}</p>
        <label class="my-3">流程说明<input v-model="workflowReason" maxlength="500" :disabled="locked" /></label>
        <p v-if="dirty" class="text-sm text-amber-800">请先保存当前改动，再操作流程。</p>
        <div class="flex flex-wrap gap-2">
          <Button v-if="isDraft && access?.can_submit" :disabled="locked || dirty || !selected.inputs.order || !workflowReason.trim()" @click="workflow('submit')">提交采购填期</Button>
          <Button v-if="selected.status === 'AWAITING_SELF_REVIEW' && access?.can_self_review" :disabled="locked || dirty || !workflowReason.trim()" @click="workflow('self-review')">业务自审确认</Button>
          <Button v-if="!isDraft && access?.can_submit" variant="outline" :disabled="locked || dirty || !workflowReason.trim()" @click="workflow('reopen')">退回草稿修改</Button>
        </div>
      </SectionPanel>
      <SectionPanel v-if="result" title="本次试算结果" subtitle="含损耗毛需求；尚未抵扣库存与在途，不作采购下发依据。"><TrialResults :key="previewSequence" :result="result" /></SectionPanel>
      <SectionPanel v-if="histories.length" title="历史试算依据"><details v-for="h in histories" :key="h.version" class="border-b py-3"><summary>{{ h.inputs.title }} · 草稿 v{{ h.version }} · BOM v{{ h.bom.version }} · {{ h.occurred_at }}</summary><p class="my-2">{{ statusText(h.status) }} · 物料期：{{ Object.entries(h.process_dates || {}).map(([process, date]) => `${process} ${date}`).join("；") || "未填写" }}</p><p v-if="h.reviewed_by">自审：{{ h.reviewed_by.name }} · {{ h.reviewed_by.at }}</p><p class="my-3">{{ h.owner_name }} · {{ h.reason }} · 数量 {{ h.inputs.quantity }} · 损耗 {{ h.inputs.loss_percent }}%</p><TrialResults :result="h.result" /></details></SectionPanel>
    </template>
  </main>
</template>

<style scoped>
.material-trial label { display: flex; flex-direction: column; gap: .35rem; font-size: .875rem; }
.material-trial input:not([type=checkbox]), .material-trial select { width: 100%; min-width: 0; border: 1px solid var(--color-slate-300); border-radius: var(--radius-md); background: white; padding: .5rem .65rem; }
.material-trial table { width: 100%; min-width: 640px; font-size: .875rem; border-collapse: collapse; }
.material-trial caption { text-align: left; font-weight: 600; padding: .6rem 0; }
.material-trial th, .material-trial td { text-align: center; padding: .65rem; border-bottom: 1px solid var(--color-slate-200); }
.material-trial th { background: var(--color-slate-50); }
</style>
