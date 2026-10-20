<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { FocusScope } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { warehouseOperationsApi as api, type FabricIssuePlan, type FabricIssuePlanLine, type WarehouseOperationsWorkspace } from '@/api/warehouseOperations'
import { pendingGroupCommands, type PendingGroupCommand } from './fabricIssueGroupPending'
import { warehouseRequestId } from './requestIdentity'
import { quantityText, receiptQuantity } from './receiptQuantities'
import { remaining } from './operations'

const emit = defineEmits<{ close: []; saved: [] }>()
const auth = useAuthStore()
const data = ref<WarehouseOperationsWorkspace>(), groupId = ref(''), order = ref(''), name = ref(''), selected = ref<string[]>([])
const date = ref(new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date()))
const busy = ref(false), error = ref(''), message = ref(''), plan = ref<FabricIssuePlan>(), lines = ref<FabricIssuePlanLine[]>([])
const acknowledged = ref(false), reason = ref(''), frozen = ref<PendingGroupCommand>(), requestSearch = ref('')
let generation = 0
const groups = computed(() => data.value?.issue_groups ?? [])
const group = computed(() => groups.value.find(g => g.group_id === groupId.value))
const canOperate = computed(() => !!data.value?.permissions.read && !!data.value.permissions.operate)
const owner = computed(() => auth.currentUser?.id ?? '')
const membership = computed(() => new Map(groups.value.flatMap(g => g.request_ids.map(id => [id, g.group_id] as const))))
const requests = computed(() => (data.value?.documents ?? []).filter(r => r.kind === 'REQUEST' && !r.reversed
  && (!membership.value.has(r.id) || membership.value.get(r.id) === groupId.value)
  && (!r.closed || group.value?.request_ids.includes(r.id))
  && (!requestSearch.value || JSON.stringify(r).toLowerCase().includes(requestSearch.value.toLowerCase()))))
const changed = computed(() => !!plan.value || !!order.value || !!name.value || selected.value.length > 0)
function resetPlan() { plan.value = undefined; lines.value = []; acknowledged.value = false }
function chooseGroup() {
  resetPlan(); order.value = group.value?.order_no ?? ''; name.value = group.value?.name ?? ''
  selected.value = [...(group.value?.request_ids ?? [])]; error.value = ''; message.value = ''
}
function selectRequest(id: string, checked: boolean) {
  selected.value = checked ? [...selected.value, id] : selected.value.filter(v => v !== id)
}
watch(date, resetPlan)
async function load() {
  const ticket = ++generation
  busy.value = true
  try { const result = await api.workspace('fabric'); if (ticket === generation) data.value = result }
  catch(e) { if (ticket === generation) { data.value = undefined; error.value = getApiErrorMessage(e) } }
  finally { if (ticket === generation) busy.value = false }
  return ticket === generation
}
watch(() => [owner.value, auth.authorizationVersion], () => {
  generation++; busy.value = false; data.value = undefined; resetPlan(); selected.value = []; groupId.value = ''; order.value = ''; name.value = ''
  requestSearch.value = ''; reason.value = ''; error.value = ''; message.value = ''
  frozen.value = pendingGroupCommands.get(owner.value)
  if (owner.value) void load()
}, { immediate: true })
function canLeave() {
  if (busy.value || frozen.value) { error.value = '保存结果待确认，请用原内容重试，避免重复发料。'; return false }
  return !changed.value || window.confirm('确定关闭配套发料？未确认的方案不会扣库存。')
}
function close() { if (canLeave()) emit('close') }
onBeforeRouteLeave(canLeave); onBeforeRouteUpdate(canLeave)
function unload(event: BeforeUnloadEvent) { if (changed.value || busy.value || frozen.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', unload)
onBeforeUnmount(() => { generation++; window.removeEventListener('beforeunload', unload) })

async function command(command: PendingGroupCommand) {
  if (busy.value || !owner.value || !canOperate.value) return
  const user = owner.value, ticket = generation
  busy.value = true; error.value = ''; pendingGroupCommands.set(user, command)
  try {
    if (command.kind === 'group') {
      const saved = await api.saveIssueGroup(command.body)
      pendingGroupCommands.delete(user)
      if (ticket !== generation) return
      frozen.value = undefined
      if (!await load()) return
      groupId.value = saved.group_id; chooseGroup(); message.value = '关联已保存，可生成发料方案。'
    } else {
      await api.issueGroup(command.body)
      pendingGroupCommands.delete(user)
      if (ticket !== generation) return
      frozen.value = undefined; resetPlan(); if (!await load()) return
      message.value = '配套发料已登记，各领料单进度已更新。'; emit('saved')
    }
  } catch(e) {
    const status = (e as { response?: { status?: number } }).response?.status
    const uncertain = !status || status === 408 || status >= 500 || !!frozen.value
    if (!uncertain) pendingGroupCommands.delete(user)
    if (ticket !== generation) return
    if (uncertain) { frozen.value = command; error.value = '保存结果待确认，原请求已保留，请用原内容重试。' }
    else { error.value = getApiErrorMessage(e); if (status === 409) { resetPlan(); await load() } }
  } finally { if (ticket === generation) busy.value = false }
}
async function saveGroup() {
  if (selected.value.length < 2) { error.value = '请至少关联两张领料单。'; return }
  if (!data.value) return
  await command({ kind: 'group', body: { factory_id: 'huakang-c', request_id: warehouseRequestId(), expected_revision: data.value.revision,
    group_id: groupId.value, order_no: order.value, name: name.value, request_ids: [...selected.value] } })
}
async function recover() {
  if (!frozen.value || busy.value || !data.value?.permissions.read) return
  const ticket = generation, user = owner.value, original = frozen.value
  busy.value = true; error.value = ''
  try {
    const result = await api.recoverIssueGroup(original)
    pendingGroupCommands.delete(user)
    if (ticket !== generation) return
    frozen.value = undefined; resetPlan()
    if (!await load()) return
    message.value = result.state === 'committed' ? '原请求已成功，记录已刷新。' : '原未执行请求已停止，请重新生成方案后确认。'
    emit('saved')
  } catch(e) { if (ticket === generation) error.value = getApiErrorMessage(e) }
  finally { if (ticket === generation) busy.value = false }
}
async function generate() {
  if (!groupId.value || busy.value || frozen.value) return
  const ticket = generation
  busy.value = true; error.value = ''; resetPlan()
  try {
    const result = await api.previewIssueGroup(groupId.value, date.value)
    if (ticket === generation) { plan.value = result; lines.value = result.items.map(row => ({ ...row })) }
  } catch(e) { if (ticket === generation) error.value = getApiErrorMessage(e) }
  finally { if (ticket === generation) busy.value = false }
}
function candidates(id: string) {
  const request = plan.value?.demands.find(d => d.request.id === id)?.request.data
  return plan.value?.candidates.filter(b => request && b.item_code === request.item_code && b.item_name === request.item_name
    && b.unit === request.unit && b.process_state === request.process_state && b.material_category === request.material_category) ?? []
}
function assigned(id: string) { return lines.value.filter(l => l.original_id === id).reduce((sum, l) => sum + (receiptQuantity(l.quantity) ?? 0n), 0n) }
function shortage(id: string, need: string) { const value = (receiptQuantity(need) ?? 0n) - assigned(id); return value > 0 ? quantityText(value) : '0' }
function addLine(id: string) { lines.value.push({ original_id: id, batch_id: '', quantity: '' }); acknowledged.value = false }
async function issue() {
  if (!plan.value || !acknowledged.value) return
  const pairs = new Set<string>(), batches = new Map<string, bigint>()
  for (const row of lines.value) {
    const value = receiptQuantity(row.quantity), key = `${row.original_id}:${row.batch_id}`
    if (!row.batch_id || value === undefined || value <= 0n || pairs.has(key)) { error.value = '请填写有效批次和正数数量，同一领料单的同批次请合并。'; return }
    pairs.add(key); batches.set(row.batch_id, (batches.get(row.batch_id) ?? 0n) + value)
  }
  if (!lines.value.length || plan.value.demands.some(d => assigned(d.request.id) > (receiptQuantity(d.remaining) ?? 0n))
    || [...batches].some(([id, q]) => q > (receiptQuantity(plan.value!.candidates.find(b => b.id === id)?.quantity ?? '') ?? 0n))) {
    error.value = '发料须有明细，且累计不能超过领料单待发量或批次库存。'; return
  }
  await command({ kind: 'issue', body: { factory_id: 'huakang-c', group_id: groupId.value, request_id: warehouseRequestId(),
    expected_revision: plan.value.revision, token: plan.value.token, business_date: date.value, confirmed: true,
    reason: reason.value, items: lines.value.map(row => ({ ...row })) } })
}
</script>

<template>
  <Teleport to="body"><div class="kit-overlay fabric-touch-overlay"><FocusScope as-child loop trapped><section class="kit-dialog fabric-touch-dialog" role="dialog" aria-modal="true" aria-label="同订单配套发料" @keydown.esc.prevent="close">
    <header><div><h2>同订单配套发料</h2><p>关联多张领料单，统一选缸；逐单核对后一起发料。</p></div><Button variant="outline" :disabled="busy || !!frozen" @click="close">关闭</Button></header>
    <main>
      <p v-if="error" role="alert" class="kit-error">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
      <div v-if="frozen" class="kit-pending"><p>原{{ frozen.kind === 'group' ? '配套关联' : '配套发料' }}请求结果待确认，不能另开新单。</p><Button :disabled="busy || !canOperate" @click="command(frozen)">用原内容重试</Button><Button class="ml-3" variant="outline" :disabled="busy || !data?.permissions.read" @click="recover">核对结果／停止未执行请求</Button></div>
      <fieldset :disabled="busy || !!frozen || !canOperate">
        <label>配套组<select v-model="groupId" aria-label="选择配套组" @change="chooseGroup"><option value="">新建配套组</option><option v-for="g in groups" :key="g.group_id" :value="g.group_id">{{ g.order_no }} · {{ g.name }} · {{ g.request_ids.length }} 张领料单</option></select></label>
        <form class="kit-group" @submit.prevent="saveGroup">
          <div class="kit-fields"><label>订单 / 放产单号<input v-model.trim="order" aria-label="配套订单号" required maxlength="128" :disabled="!!group" /></label><label>配套组名称<input v-model.trim="name" aria-label="配套组名称" required maxlength="128" placeholder="如：衣身与捆条" :disabled="!!group" /></label></div>
          <p>已有订单编号必须一致；未填编号的领料单由本次明确关联。已关联单据保留，可继续追加。</p>
          <details :open="!group"><summary>关联领料单 · 已选 {{ selected.length }} 张</summary><input v-model.trim="requestSearch" type="search" aria-label="查找配套领料单" placeholder="查单号、物料、部件或领用方" />
            <div class="kit-requests"><label v-for="r in requests" :key="r.id" class="kit-check"><input type="checkbox" :checked="selected.includes(r.id)" :disabled="group?.request_ids.includes(r.id)" :aria-label="`关联领料单 ${r.id}`" @change="selectRequest(r.id, ($event.target as HTMLInputElement).checked)" /><span><strong>{{ r.data.source_no }} / {{ r.data.source_line }}</strong> · {{ r.data.counterparty }} · {{ r.data.purpose || '未填部件 / 用途' }}<small>{{ r.data.item_code }} {{ r.data.item_name }} · 待发 {{ remaining(r.data.quantity, r.issued_quantity) }} {{ r.data.unit }} · {{ r.data.production_no || '未填订单号' }}</small></span></label></div>
          </details><Button type="submit" variant="outline" :disabled="selected.length < 2 || selected.length > 100">{{ group ? '保存追加关联' : '保存配套组' }}</Button>
        </form>
        <div v-if="group" class="kit-generate"><label>发料日期<input v-model="date" type="date" aria-label="配套发料日期" /></label><Button @click="generate">生成推荐方案</Button></div>
      </fieldset>
      <section v-if="plan" class="kit-plan"><h3>{{ plan.group.order_no }} · {{ plan.group.name }}</h3><p>优先沿用本组已发缸号；尚未发料时优先可满足整组的缸，均不足则先选可供量最大的缸。同缸内按原入库日期发旧料；不足自动补其他缸，各部件按待发量比例分摊。方案不占库存。</p>
        <fieldset :disabled="busy || !!frozen || !canOperate" @input="acknowledged = false" @change="acknowledged = false">
          <article v-for="d in plan.demands" :key="d.request.id" class="kit-demand"><div class="kit-demand-title"><div><strong>{{ d.request.data.source_no }} / {{ d.request.data.source_line }} · {{ d.request.data.counterparty }}</strong><small>{{ d.request.data.purpose || '未填部件 / 用途' }} · {{ d.request.data.item_code }} {{ d.request.data.item_name }}</small></div><span>待发 {{ d.remaining }} · 本次 {{ quantityText(assigned(d.request.id)) }} · 尚缺 {{ shortage(d.request.id, d.remaining) }} {{ d.request.data.unit }}</span></div>
            <div v-for="(line, index) in lines" :key="index"><div v-if="line.original_id === d.request.id" class="kit-line"><label>批次 / 缸号 / 卷号 / 仓位<select v-model="line.batch_id" :aria-label="`配套批次 ${index + 1}`"><option value="">选择同物料批次</option><option v-for="b in candidates(line.original_id)" :key="b.id" :value="b.id">{{ b.lot || '缸号未知' }} · 卷 {{ b.roll_no || '—' }} · {{ b.location }} · {{ b.counterparty || '来源未知' }} · {{ b.received_on }} · 余 {{ b.quantity }} {{ b.unit }}</option></select></label><label>实发数量<input v-model.trim="line.quantity" inputmode="decimal" :aria-label="`配套数量 ${index + 1}`" /></label><Button variant="ghost" @click="lines.splice(index, 1); acknowledged = false">移除</Button></div></div>
            <Button variant="outline" size="sm" :disabled="lines.length >= 500 || !candidates(d.request.id).length" @click="addLine(d.request.id)">添加批次</Button>
          </article><p v-if="!plan.demands.length">组内领料单已发完或已关闭。</p>
          <label>备注（选填）<textarea v-model.trim="reason" rows="2" maxlength="1000" /></label>
        </fieldset>

      </section>
    </main>
    <footer v-if="plan" class="kit-submit">
        <label class="kit-check"><input v-model="acknowledged" type="checkbox" :disabled="busy || !!frozen || !canOperate" aria-label="确认配套发料方案" />已核对各部件、领用方、缸号及实发数量，按本方案发料；不足部分保留待发。</label>
        <Button :disabled="busy || !!frozen || !canOperate || !acknowledged || !lines.length" @click="issue">确认配套发料</Button>
    </footer>
  </section></FocusScope></div></Teleport>
</template>

<style scoped>
.kit-submit{padding:16px 24px;border-top:1px solid var(--border)}
.kit-overlay{position:fixed;inset:0;z-index:90;display:grid;place-items:center;padding:20px;background:#0f172a80}.kit-dialog{width:min(1120px,100%);max-height:94dvh;overflow:auto;background:var(--card);color:var(--foreground);border-radius:12px}header{display:flex;justify-content:space-between;align-items:center;padding:20px 24px;border-bottom:1px solid var(--border)}h2{font-size:20px;font-weight:600}h3{font-weight:600}main{padding:24px}fieldset{border:0;padding:0;min-width:0}label{display:flex;flex-direction:column;gap:6px;font-size:13px}input,select,textarea{min-width:0;padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--card);font:inherit}p,small{font-size:12px;color:var(--muted-foreground);line-height:1.7}p{margin:8px 0}small{display:block}.kit-fields{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0}.kit-group{padding-bottom:20px;border-bottom:1px solid var(--border)}summary{cursor:pointer;font-size:13px;margin:12px 0}.kit-check{flex-direction:row;align-items:flex-start;gap:10px;margin:12px 0}.kit-check input{margin-top:4px}.kit-requests{max-height:240px;overflow:auto}.kit-generate{display:flex;gap:16px;align-items:end;margin:20px 0}.kit-plan{margin-top:20px}.kit-demand{padding:16px;margin:16px 0;border:1px solid var(--border);border-radius:8px}.kit-demand-title{display:flex;justify-content:space-between;gap:16px;font-size:13px}.kit-line{display:grid;grid-template-columns:minmax(220px,1fr) 140px auto;gap:12px;align-items:end;margin:12px 0}.kit-error{color:#b91c1c}.kit-pending{padding:16px;background:var(--muted)}@media(max-width:700px){.kit-overlay{padding:8px}header,main{padding:16px}.kit-fields,.kit-line{grid-template-columns:1fr}.kit-demand-title{display:block}}
</style>
