<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/common/PageHeader.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { quantityText } from './api'
import { purchaseApi as api, emptyPurchase, purchaseStatus, type PurchaseAccess, type PurchaseDocument, type PurchaseSource, type PreparationChecks } from './purchaseApi'

const route = useRoute(), auth = useAuthStore()
const access = ref<PurchaseAccess | null>(null), sources = ref<PurchaseSource[]>([]), documents = ref<PurchaseDocument[]>([])
const selected = ref<PurchaseDocument | null>(null), editing = ref(false), data = ref(emptyPurchase()), reason = ref('核对采购准备依据')
const proposed = ref<Record<string, number>>({}), histories = ref<PurchaseDocument[]>([])
const error = ref(''), notice = ref(''), busy = ref(false), loading = ref(false), dirty = ref(false), changeDirty = ref(false)
const pending = ref<{ path: string; body: unknown } | null>(null)
const checks = ref<PreparationChecks | null>(null), checking = ref(false)
let checksSequence = 0
function clearChecks() { checksSequence++; checks.value = null; checking.value = false }
let epoch = 0, historySequence = 0, replacing = false
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T
const ready = computed(() => route.query.factory === 'huakang-c' && access.value?.enabled && access.value.schema_ready)
const locked = computed(() => loading.value || busy.value || !!pending.value)
const draft = computed(() => !selected.value || selected.value.status === 'DRAFT')
const writable = computed(() => ready.value && access.value?.can_write && draft.value)
const basis = computed(() => selected.value?.source || sources.value.find(s => s.id === data.value.demand_id && s.version === data.value.demand_version))
const group = (key: string) => basis.value?.groups.find(g => g.source_key === key)
const differenceLabels: Record<string, string> = { ADDED: '新增', REMOVED: '移除', QUANTITY: '用量变化', PROCESS: '工序变化', DESCRIPTION: '名称变化' }
const differenceLabel = (changes: string[]) => changes.map(c => differenceLabels[c] || c).join('、')
const successor = computed(() => selected.value && documents.value.find(d => d.replacement_of?.id === selected.value!.id))
async function createReplacement() {
  const comparison = checks.value?.source_comparison
  if (!ready.value || !access.value?.can_write || locked.value || dirty.value || changeDirty.value || !reason.value.trim()
      || selected.value?.status !== 'CANCELLED_UNRELEASED' || successor.value || comparison?.status !== 'COMPARED' || !comparison.target_version) return
  pending.value = { path: `/documents/${selected.value.id}/replacement`, body: { ...envelope(), demand_version: comparison.target_version } }
  clearChecks()
  await retry()
}
function clear() {
  clearChecks()
  access.value = null; sources.value = []; documents.value = []; selected.value = null; editing.value = false; histories.value = []; historySequence++
  replacing = true; data.value = emptyPurchase(); proposed.value = {}; reason.value = '核对采购准备依据'; replacing = false
  dirty.value = false; changeDirty.value = false; pending.value = null; busy.value = false; loading.value = false; error.value = ''; notice.value = ''
}
function failure(e: unknown) {
  const cause = e as { response?: { status?: number; data?: { detail?: unknown } }; message?: string }
  if ([401, 403].includes(cause.response?.status || 0)) { epoch++; clear() }
  error.value = typeof cause.response?.data?.detail === 'string' ? cause.response.data.detail : cause.response?.data?.detail ? '请核对数量、日期和商务字段格式。' : cause.message || '操作失败，请重试。'
}
function discard() { return !locked.value && (!(dirty.value || changeDirty.value) || window.confirm('有未保存的采购内容，是否放弃并继续？')) }
function adopt(row?: PurchaseDocument) {
  clearChecks()
  selected.value = row || null; replacing = true
  data.value = row ? clone(row.data) : emptyPurchase()
  proposed.value = Object.fromEntries((row?.data.lines || []).map(l => [l.source_key, l.quantity || 0]))
  replacing = false; dirty.value = false; changeDirty.value = false; histories.value = []; historySequence++; editing.value = true
}
function open(row?: PurchaseDocument) { if (discard()) { adopt(row); notice.value = ''; error.value = '' } }
async function load() {
  if (!discard()) return
  clearChecks()
  if (route.query.factory !== 'huakang-c') { clear(); return }
  const token = ++epoch; loading.value = true; error.value = ''; selected.value = null; editing.value = false; documents.value = []; sources.value = []; histories.value = []
  dirty.value = false; changeDirty.value = false; historySequence++
  try {
    const a = await api.access(); if (token !== epoch) return
    access.value = a
    if (a.enabled && a.schema_ready) { const w = await api.workspace(); if (token !== epoch) return; sources.value = w.sources; documents.value = w.documents }
  } catch (e) { if (token === epoch) failure(e) }
  finally { if (token === epoch) loading.value = false }
}
function chooseSource(event: Event) {
  const control = event.target as HTMLSelectElement, source = sources.value.find(s => `${s.id}:${s.version}` === control.value)
  if (!source || (dirty.value && !window.confirm('更换需求将清空采购草稿输入，是否继续？'))) { control.value = data.value.demand_id ? `${data.value.demand_id}:${data.value.demand_version}` : ''; return }
  data.value = { ...emptyPurchase(), demand_id: source.id, demand_version: source.version }
}
function toggle(key: string, event: Event) {
  if ((event.target as HTMLInputElement).checked) data.value.lines.push({ source_key: key, quantity: null, purchase_unit: '', unit_price: null })
  else data.value.lines = data.value.lines.filter(l => l.source_key !== key)
}
function envelope() { return { factory_id: 'huakang-c', operation_id: crypto.randomUUID(), expected_version: selected.value?.version || 0, reason: reason.value } }
async function save() {
  if (!writable.value || locked.value || !basis.value || !reason.value.trim()) return
  clearChecks()
  const fields = clone(data.value)
  fields.tax_rate = fields.tax_rate === '' ? null : fields.tax_rate; fields.delivery_date = fields.delivery_date || null
  fields.lines = fields.lines.map(l => ({ ...l, quantity: String(l.quantity ?? '').trim() === '' ? null : Number(l.quantity), unit_price: l.unit_price === '' ? null : l.unit_price }))
  pending.value = { path: selected.value ? `/documents/${selected.value.id}` : '/documents', body: { ...envelope(), data: fields } }
  await retry()
}
async function action(name: string) {
  if (!selected.value || locked.value || dirty.value || (name !== 'QUANTITY' && changeDirty.value) || !reason.value.trim()) return
  const write = ['submit', 'QUANTITY', 'CANCEL'].includes(name)
  if (write ? !access.value?.can_write : !access.value?.can_approve) return
  clearChecks()
  let path = `/documents/${selected.value.id}/actions/${name}`, body: unknown = envelope()
  if (name === 'QUANTITY' || name === 'CANCEL') {
    const quantities = name === 'CANCEL' ? {} : Object.fromEntries(selected.value.data.lines.filter(l => proposed.value[l.source_key] !== l.quantity).map(l => [l.source_key, Number(proposed.value[l.source_key])]))
    path = `/documents/${selected.value.id}/change`; body = { ...envelope(), kind: name, quantities }
  }
  pending.value = { path, body }; await retry()
}
async function retry() {
  const original = pending.value; if (!original || busy.value) return
  const token = epoch; busy.value = true; error.value = ''
  try {
    const saved = await api.command(original.path, original.body); if (token !== epoch) return
    pending.value = null; editing.value = false; selected.value = null; documents.value = []; histories.value = []; historySequence++; dirty.value = false; changeDirty.value = false
    notice.value = `已保存：${purchaseStatus(saved.status)}。正式下发仍未开放。`
    const w = await api.workspace(); if (token !== epoch) return
    sources.value = w.sources; documents.value = w.documents
    const fresh = w.documents.find(d => d.id === saved.id && d.version >= saved.version)
    if (fresh) adopt(fresh)
  } catch (e) {
    if (token !== epoch) return
    const status = (e as { response?: { status?: number } }).response?.status
    if (status && status < 500) pending.value = null
    failure(e)
  } finally { if (token === epoch) busy.value = false }
}
async function history() {
  if (!selected.value) return
  const token = epoch, sequence = ++historySequence
  try { const h = await api.history(selected.value.id); if (token === epoch && sequence === historySequence) histories.value = h.items }
  catch (e) { if (token === epoch && sequence === historySequence) failure(e) }
}
async function checkPreparation() {
  if (!selected.value || locked.value || dirty.value || changeDirty.value) return
  const token = epoch, sequence = ++checksSequence, id = selected.value.id, version = selected.value.version
  checking.value = true; checks.value = null; error.value = ''
  try {
    const report = await api.checks(id, version)
    if (token === epoch && sequence === checksSequence && selected.value?.id === id && selected.value.version === version) checks.value = report
  } catch (e) { if (token === epoch && sequence === checksSequence) failure(e) }
  finally { if (token === epoch && sequence === checksSequence) checking.value = false }
}
watch(data, () => { if (!replacing) { dirty.value = true; clearChecks() } }, { deep: true, flush: 'sync' })
watch(proposed, () => { if (!replacing) { changeDirty.value = true; clearChecks() } }, { deep: true, flush: 'sync' })
watch(() => [route.query.factory, auth.sessionVersion, auth.authorizationVersion], () => { epoch++; clear(); if (route.query.factory === 'huakang-c') void load() }, { immediate: true })
function beforeUnload(e: BeforeUnloadEvent) { if (dirty.value || changeDirty.value || pending.value) { e.preventDefault(); e.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
onBeforeRouteLeave(discard); onBeforeRouteUpdate(discard)
onBeforeUnmount(() => { epoch++; window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <main class="material-purchasing space-y-5">
    <PageHeader title="采购制单与审核" description="准备采购内容、负责人内部审核和取消改量申请；正式下发尚未开放。"><template #actions><Button variant="outline" :disabled="locked" @click="load">刷新准备单</Button></template></PageHeader>
    <p v-if="route.query.factory !== 'huakang-c'">请在华康 C 打开采购准备流程。</p>
    <p v-if="loading" role="status">正在读取采购准备资料…</p>
    <p v-if="error" role="alert" class="rounded-md bg-red-50 p-3 text-red-800">{{ error }}</p>
    <p v-if="notice" role="status" class="text-teal-800">{{ notice }}</p>
    <div v-if="pending && !busy"><p>结果尚未确认，输入已锁定，请核对原请求。</p><Button @click="retry">核对并重试原请求</Button></div>
    <SectionPanel v-if="access && !ready" title="采购准备流程尚未开放" subtitle="需完成部署及独立授权。" />
    <template v-if="ready">
      <SectionPanel title="采购准备单" subtitle="内部已审也不代表已发送供应商，不计入有效在途。"><template #action><Button :disabled="locked || !access?.can_write" @click="open()">新建准备单</Button></template>
        <p v-if="!documents.length">暂无采购准备单。</p>
        <div v-else class="overflow-x-auto"><table><thead><tr><th>准备单／货号</th><th>供应商参考</th><th>状态</th><th>版本</th><th>操作</th></tr></thead><tbody><tr v-for="d in documents" :key="d.id"><td>{{ d.id.slice(0, 8) }} ／ {{ d.source.item_no }}</td><td>{{ d.data.supplier_reference || '待填' }}</td><td>{{ purchaseStatus(d.status) }}</td><td>{{ d.version }}</td><td><Button size="sm" variant="outline" :disabled="locked" @click="open(d)">查看准备单</Button></td></tr></tbody></table></div>
      </SectionPanel>
      <SectionPanel v-if="editing" title="采购内容与来源核对">
        <p v-if="selected?.replacement_of" class="mb-3 text-sm">关联原准备单：{{ selected.replacement_of.id }} · v{{ selected.replacement_of.version }} ／ 原需求 v{{ selected.replacement_of.demand_version }}。原单已内部取消，新单须独立提交审核。</p>
        <div v-if="successor" class="mb-3"><p>原单已建立关联新单：{{ successor.id }} · {{ purchaseStatus(successor.status) }}</p><Button variant="outline" :disabled="locked" @click="open(successor)">查看关联新单</Button></div>
        <p class="mb-3 text-sm text-amber-800">资料未齐，正式下发未开放。毛需求尚未扣库存／在途；拟订量需人工填写，不代表核准采购量。供应商、单位换算及单价税额口径仍待核实。</p>
        <form @submit.prevent="save"><fieldset :disabled="locked || !writable">
          <label>业务已自审需求<select :value="data.demand_id ? `${data.demand_id}:${data.demand_version}` : ''" :disabled="!!selected" @change="chooseSource"><option value="">请选择固定需求版本</option><option v-if="selected" :value="`${data.demand_id}:${data.demand_version}`">{{ selected.source.item_no }} · 需求 v{{ data.demand_version }}</option><template v-else><option v-for="s in sources" :key="s.id" :value="`${s.id}:${s.version}`">{{ s.item_no }} ／ {{ s.owner_name }} · v{{ s.version }}</option></template></select></label>
          <p v-if="!sources.length && !selected" class="my-2">暂无业务已自审需求。</p>
          <div class="my-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <label>供应商参考<input v-model="data.supplier_reference" maxlength="255" /></label><label>币种<input v-model="data.currency" maxlength="3" placeholder="CNY / HKD" /></label>
            <label>税率（%）<input v-model="data.tax_rate" inputmode="decimal" /></label><label>交货日期<input v-model="data.delivery_date" type="date" /></label>
            <label>交货地点<input v-model="data.delivery_location" maxlength="255" /></label><label>付款条款<input v-model="data.payment_terms" maxlength="255" /></label>
          </div>
          <div v-if="basis" class="overflow-x-auto"><table><caption>固定来源毛需求：不同属性分别保留</caption><thead><tr><th>选择采购</th><th>物料</th><th>本次属性</th><th>工序</th><th>毛需求</th></tr></thead><tbody><tr v-for="g in basis.groups" :key="g.source_key"><td><input type="checkbox" :aria-label="`选择 ${g.code} ${g.attribute}`" :checked="data.lines.some(l => l.source_key === g.source_key)" :disabled="!g.purchasable" @change="toggle(g.source_key, $event)" /></td><td>{{ g.code }} {{ g.name }}</td><td>{{ g.attribute }}</td><td>{{ g.processes.join('、') }}</td><td>{{ quantityText(g.gross) }} {{ g.unit }}</td></tr></tbody></table></div>
          <div v-if="data.lines.length" class="my-4 overflow-x-auto"><table><caption>拟订采购明细</caption><thead><tr><th>物料／属性</th><th>拟订整数数量</th><th>采购单位</th><th>单价（口径待核实）</th></tr></thead><tbody><tr v-for="l in data.lines" :key="l.source_key"><td>{{ group(l.source_key)?.code }} ／ {{ group(l.source_key)?.attribute }}</td><td><input v-model.number="l.quantity" type="number" min="1" step="1" :aria-label="`${group(l.source_key)?.code} ${group(l.source_key)?.attribute} 拟订量`" /></td><td><input v-model="l.purchase_unit" maxlength="255" aria-label="采购单位" /></td><td><input v-model="l.unit_price" inputmode="decimal" aria-label="单价" /></td></tr></tbody></table></div>
          <Button type="submit" :disabled="!basis || !reason.trim()">保存采购草稿</Button>
        </fieldset></form>
        <label class="my-3">操作说明<input v-model="reason" maxlength="500" :disabled="locked" /></label>
        <p v-if="dirty" class="text-sm text-amber-800">请先保存采购内容，再提交或审核。</p>
        <div v-if="selected" class="my-3 flex flex-wrap gap-2">
          <Button v-if="selected.status === 'DRAFT' && access?.can_write" :disabled="locked || dirty || !reason.trim()" @click="action('submit')">提交负责人审核</Button>
          <template v-if="selected.status === 'PENDING_APPROVAL' && access?.can_approve"><Button :disabled="locked || dirty || !reason.trim()" @click="action('approve')">内部审核通过</Button><Button variant="outline" :disabled="locked || dirty || !reason.trim()" @click="action('reject')">驳回制单</Button></template>
          <Button v-if="access?.can_write && ['DRAFT', 'PENDING_APPROVAL', 'APPROVED_UNRELEASED'].includes(selected.status)" variant="outline" :disabled="locked || dirty || changeDirty || !reason.trim()" @click="action('CANCEL')">申请取消整单</Button>
          <Button variant="ghost" :disabled="locked" @click="history">查看历史</Button>
          <Button variant="outline" :disabled="locked || dirty || changeDirty || checking" @click="checkPreparation">{{ checking ? '正在核对…' : '核对来源与重复准备' }}</Button>
        </div>
        <p v-if="selected && ['DRAFT', 'PENDING_APPROVAL'].includes(selected.status)" class="text-sm">取消须负责人批准；申请期间暂停编辑和原单审核，驳回后恢复申请前状态。</p>
        <p v-if="selected?.approved_by" class="text-sm">内部审核：{{ selected.approved_by.name }} · {{ selected.approved_by.at }}。未下发供应商。</p>
        <div v-if="selected?.status === 'APPROVED_UNRELEASED' && access?.can_write" class="mt-4 space-y-3">
          <h3 class="font-medium">申请改量</h3><p class="text-sm">负责人批准前保持原量；本期仅处理未下发准备单。</p>
          <div class="overflow-x-auto"><table><thead><tr><th>物料／属性</th><th>原拟订量</th><th>申请新量</th></tr></thead><tbody><tr v-for="l in selected.data.lines" :key="l.source_key"><td>{{ group(l.source_key)?.code }} ／ {{ group(l.source_key)?.attribute }}</td><td>{{ l.quantity }} {{ l.purchase_unit }}</td><td><input v-model.number="proposed[l.source_key]" type="number" min="1" step="1" aria-label="申请新量" :disabled="locked" /></td></tr></tbody></table></div>
          <div class="flex gap-2"><Button :disabled="locked || !changeDirty || !reason.trim()" @click="action('QUANTITY')">提交改量申请</Button></div>
        </div>
        <div v-if="selected?.pending_change" class="mt-4 space-y-2"><h3 class="font-medium">待审核申请：{{ selected.pending_change.kind === 'CANCEL' ? '取消整单' : '改量' }}</h3><p>申请前状态：{{ purchaseStatus(selected.pending_change.before_status || 'APPROVED_UNRELEASED') }}；驳回后恢复此状态。</p><p>{{ selected.pending_change.requested_by.name }}：{{ selected.pending_change.reason }}</p><ul v-if="selected.pending_change.kind === 'QUANTITY'"><li v-for="(qty, key) in selected.pending_change.quantities" :key="key">{{ group(key)?.code }} ／ {{ group(key)?.attribute }}：{{ selected.pending_change.before[key] }} → {{ qty }}</li></ul><div v-if="access?.can_approve" class="flex gap-2"><Button :disabled="locked || !reason.trim()" @click="action('approve-change')">批准变更</Button><Button variant="outline" :disabled="locked || !reason.trim()" @click="action('reject-change')">驳回变更</Button></div></div>
      </SectionPanel>
      <SectionPanel v-if="checks" title="来源与重复准备核对">
        <p>本单 v{{ checks.document_version }} ／ 绑定需求 v{{ checks.bound_demand_version }} · 核对时间 {{ checks.checked_at }}</p>
        <p class="my-3" :class="checks.source_current ? 'text-teal-800' : 'text-amber-800'">{{ checks.source_current ? '本单绑定的需求、订单及 BOM 依据当前有效。' : `本单来源需重新核对：${checks.source_issue}` }}</p>
        <p class="mb-3 text-sm text-slate-600">以下仅为同一需求的准备记录，按需求版本、物料属性、采购单位和状态分开。多单可能为合理拆单，请核对是否重复；不代表已采购、库存占用或可下发数量。其他需求版本需单独核对来源。</p>
        <p v-if="!checks.groups.length">暂无未取消的采购准备明细。</p>
        <div v-else class="overflow-x-auto"><table><thead><tr><th>需求版本</th><th>物料／属性</th><th>原单位 → 采购单位</th><th>状态</th><th>本状态拟订量</th><th>多单提示</th><th>组成及待批申请</th></tr></thead><tbody>
          <tr v-for="(g, index) in checks.groups" :key="index"><td>{{ g.demand_version }}</td><td>{{ g.code }} {{ g.name }} · 物料 v{{ g.material_version }} ／ {{ g.attribute }}</td><td>{{ g.source_unit }} → {{ g.purchase_unit || '未核对' }}</td><td>{{ purchaseStatus(g.status) }}<span v-if="g.before_status">（申请前：{{ purchaseStatus(g.before_status) }}）</span></td><td>{{ g.complete_quantity ?? '不完整／待核对' }}<span v-if="g.missing_quantity_count">（{{ g.missing_quantity_count }} 条未填数量）</span></td><td>{{ g.possible_duplicate ? `该版本同属性物料见于 ${g.related_document_count} 张准备单，请核对` : '单张准备单' }}</td><td><ul><li v-for="d in g.documents" :key="d.id">{{ d.id.slice(0, 8) }} · v{{ d.version }} ／ {{ d.supplier_reference || '供应商待填' }}：{{ d.quantity ?? '待填' }} {{ g.purchase_unit }}<span v-if="d.pending_kind === 'CANCEL'"> · 待批取消，当前量尚未移除</span><span v-if="d.proposed_quantity !== null"> · 申请改为 {{ d.proposed_quantity }}（未计入）</span></li></ul></td></tr>
        </tbody></table></div>
        <p class="mt-3 text-sm">已排除 {{ checks.cancelled_document_count }} 张已取消准备单。正式下发仍未开放；本次核对不替代提交时的服务器复核。</p>
        <div v-if="checks.source_comparison" class="mt-5 space-y-3">
          <h3 class="font-medium">与当前已自审需求比较</h3>
          <p v-if="checks.source_comparison.status === 'UNAVAILABLE'" class="text-amber-800">{{ checks.source_comparison.issue }}</p>
          <template v-else>
            <p>原依据 v{{ checks.bound_demand_version }} → 当前已自审 v{{ checks.source_comparison.target_version }}；{{ checks.source_comparison.unchanged_count }} 组用料汇总未变化。</p>
            <p class="text-sm text-slate-600">比较整份需求的毛用量。属性、单位或物料版本变化分别列为移除／新增，不自动认定替代关系；差额不是补购量，不修改本单。工序列比较参与工序，不表示完整工艺路径比较。</p>
            <p v-if="!checks.source_comparison.rows.length">分组汇总用量及参与工序无变化；各工序分配见下方。</p>
            <div v-else class="overflow-x-auto"><table><caption>需求用料差异（含损耗，未扣库存／在途）</caption><thead><tr><th>变化</th><th>物料／属性／单位</th><th>原依据</th><th>当前依据</th><th>毛需求差额</th></tr></thead><tbody>
              <tr v-for="r in checks.source_comparison.rows" :key="r.source_key">
                <td>{{ differenceLabel(r.changes) }}</td>
                <td>{{ (r.after || r.before)?.code }} {{ (r.after || r.before)?.name }} · v{{ (r.after || r.before)?.material_version }} ／ {{ (r.after || r.before)?.attribute }} ／ {{ (r.after || r.before)?.unit }}</td>
                <td><template v-if="r.before">基础用量 {{ quantityText(r.before.base) }}<br />损耗 {{ quantityText(r.before.loss) }}<br />毛需求 {{ quantityText(r.before.gross) }}<br />工序 {{ r.before.processes.join('、') }}</template><template v-else>原无此组</template></td>
                <td><template v-if="r.after">基础用量 {{ quantityText(r.after.base) }}<br />损耗 {{ quantityText(r.after.loss) }}<br />毛需求 {{ quantityText(r.after.gross) }}<br />工序 {{ r.after.processes.join('、') }}</template><template v-else>当前无此组</template></td>
                <td>{{ quantityText(r.delta.gross) }}<details v-if="r.delta.gross.approximate"><summary>查看精确差额</summary>{{ r.delta.gross.numerator }} / {{ r.delta.gross.denominator }}</details></td>
              </tr>
            </tbody></table></div>
            <h3 class="font-medium">分工序用量差异</h3>
            <p class="text-sm text-slate-600">按工序、物料版本、属性和单位分别核对；总量不变也可能有工序用量变化。以下仍为未扣库存／在途的需求，不代表补购数量。</p>
            <p v-if="!checks.source_comparison.process_comparison?.available" class="text-amber-800">{{ checks.source_comparison.process_comparison?.issue || '缺少分工序比较结果，请刷新核对。' }}</p>
            <template v-else>
              <p>{{ checks.source_comparison.process_comparison.unchanged_count }} 组工序用料未变化。</p>
              <p v-if="!checks.source_comparison.process_comparison.rows.length">各工序用量无变化。</p>
              <div v-else class="overflow-x-auto"><table><caption>各工序基础用量、损耗及毛需求</caption><thead><tr><th>工序／变化</th><th>物料／属性／单位</th><th>原依据</th><th>当前依据</th><th>毛需求差额</th></tr></thead><tbody>
                <tr v-for="r in checks.source_comparison.process_comparison.rows" :key="`${r.process}:${r.source_key}`">
                  <td>{{ r.process }} ／ {{ differenceLabel(r.changes) }}</td>
                  <td>{{ (r.after || r.before)?.code }} {{ (r.after || r.before)?.name }} · v{{ (r.after || r.before)?.material_version }} ／ {{ (r.after || r.before)?.attribute }} ／ {{ (r.after || r.before)?.unit }}</td>
                  <td><template v-if="r.before">基础用量 {{ quantityText(r.before.base) }}<br />损耗 {{ quantityText(r.before.loss) }}<br />毛需求 {{ quantityText(r.before.gross) }}</template><template v-else>原工序无此组</template></td>
                  <td><template v-if="r.after">基础用量 {{ quantityText(r.after.base) }}<br />损耗 {{ quantityText(r.after.loss) }}<br />毛需求 {{ quantityText(r.after.gross) }}</template><template v-else>当前工序无此组</template></td>
                  <td>{{ quantityText(r.delta.gross) }}<details v-if="r.delta.gross.approximate"><summary>查看精确差额</summary>{{ r.delta.gross.numerator }} / {{ r.delta.gross.denominator }}</details></td>
                </tr>
              </tbody></table></div>
            </template>
            <ul v-if="checks.source_comparison.dates.length"><li v-for="d in checks.source_comparison.dates" :key="d.process">{{ d.process }} 物料期：{{ d.before || '原未设置' }} → {{ d.after || '当前未设置' }}</li></ul>
            <p v-else>工序物料期无变化。</p>
            <div v-if="selected?.status === 'CANCELLED_UNRELEASED' && access?.can_write && checks.source_comparison.status === 'COMPARED' && !successor" class="space-y-2">
              <p class="text-sm">原单已内部取消。可按当前已自审需求建立关联草稿；物料、数量、单位、单价和商务字段需重新选择填写。</p>
              <Button :disabled="locked || dirty || changeDirty || !reason.trim()" @click="createReplacement">按新需求建立关联草稿</Button>
            </div>
          </template>
        </div>
      </SectionPanel>
      <SectionPanel v-if="histories.length" title="采购准备历史"><details v-for="h in histories" :key="h.version" class="border-b py-3"><summary>v{{ h.version }} · {{ purchaseStatus(h.status) }} · {{ h.occurred_at }}</summary><p>{{ h.reason }} ／ {{ h.data.supplier_reference }}</p><ul><li v-for="l in h.data.lines" :key="l.source_key">{{ h.source.groups.find(g => g.source_key === l.source_key)?.code }} ／ {{ h.source.groups.find(g => g.source_key === l.source_key)?.attribute }}：{{ l.quantity ?? '待填' }} {{ l.purchase_unit }} · 单价 {{ l.unit_price ?? '待填' }}</li></ul><p>币种 {{ h.data.currency || '待填' }} · 税率 {{ h.data.tax_rate ?? '待填' }}% · 交期 {{ h.data.delivery_date || '待填' }} · {{ h.data.delivery_location }} · {{ h.data.payment_terms }}</p>
        <div v-if="h.pending_change"><p>申请前状态：{{ purchaseStatus(h.pending_change.before_status || 'APPROVED_UNRELEASED') }}</p><p>当时申请：{{ h.pending_change.kind === 'CANCEL' ? '取消整单' : '改量' }} · {{ h.pending_change.requested_by.name }} · {{ h.pending_change.reason }}</p><ul v-if="h.pending_change.kind === 'QUANTITY'"><li v-for="(qty, key) in h.pending_change.quantities" :key="key">{{ h.source.groups.find(g => g.source_key === key)?.code }} ／ {{ h.source.groups.find(g => g.source_key === key)?.attribute }}：{{ h.pending_change.before[key] }} → {{ qty }}</li></ul></div>
        <div v-if="h.last_change"><p>申请前状态：{{ purchaseStatus(h.last_change.before_status || 'APPROVED_UNRELEASED') }}</p><p>变更决定：{{ h.last_change.decision === 'approve-change' ? '批准' : '驳回' }}{{ h.last_change.kind === 'CANCEL' ? '取消整单' : '改量' }} · {{ h.last_change.decided_by?.name }} · {{ h.last_change.decision_reason }}</p><ul v-if="h.last_change.kind === 'QUANTITY'"><li v-for="(qty, key) in h.last_change.quantities" :key="key">{{ h.source.groups.find(g => g.source_key === key)?.code }} ／ {{ h.source.groups.find(g => g.source_key === key)?.attribute }}：{{ h.last_change.before[key] }} → {{ qty }}</li></ul></div></details></SectionPanel>
    </template>
  </main>
</template>

<style scoped>
.material-purchasing label { display: flex; flex-direction: column; gap: .35rem; font-size: .875rem; }
.material-purchasing input:not([type=checkbox]), .material-purchasing select { width: 100%; min-width: 0; border: 1px solid var(--color-slate-300); border-radius: var(--radius-md); padding: .5rem .65rem; background: white; }
.material-purchasing table { width: 100%; min-width: 640px; border-collapse: collapse; font-size: .875rem; }
.material-purchasing th, .material-purchasing td { padding: .65rem; border-bottom: 1px solid var(--color-slate-200); text-align: center; }
.material-purchasing th { background: var(--color-slate-50); }
.material-purchasing caption { text-align: left; font-weight: 600; padding: .6rem 0; }
</style>
